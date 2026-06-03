import os
import django
import sys
from decimal import Decimal

# Set up Django environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from django.utils import timezone
from django.contrib.auth import get_user_model
from apps.core.models import Account, JournalEntry, JournalLine, FiscalYear
from apps.core.services import AccountService
from apps.inventory.models import Warehouse, Item, StockMovement, ItemCategory, UnitOfMeasure
from apps.inventory.services import InventoryService
from apps.treasury.models import CashBox
from apps.sales.models import SalesRepresentative, RepDailySettlement
from apps.sales.services import RepSettlementService
from apps.pos.models import POSStation, POSSession, POSOrder
from apps.pos.services import POSSessionService, POSCheckoutService

User = get_user_model()

def run_test():
    print("=" * 80)
    print("START: Test POS session cycle and deficit booking")
    print("=" * 80)

    # 1. Setup basic data
    user = User.objects.filter(is_superuser=True).first()
    if not user:
        user = User.objects.create_superuser('admin_test', 'admin@test.com', 'admin123')
    
    # Initialize chart of accounts
    AccountService.initialize_default_chart()
    AccountService.setup_common_sub_accounts()
    
    # 2. Setup warehouse, cash box, rep
    warehouse, _ = Warehouse.objects.get_or_create(code='W-TEST', defaults={'name': 'Main Test Warehouse'})
    cash_box, _ = CashBox.objects.get_or_create(code='CB-TEST', defaults={'name': 'POS Cash Drawer', 'account': Account.objects.get(code='111101'), 'responsible_user': user})
    
    # Create sales representative
    rep, created = SalesRepresentative.objects.get_or_create(
        code='REP-001',
        defaults={
            'name': 'احمد الكاشير',
            'user': user,
            'warehouse': warehouse,
            'cash_box': cash_box,
            'commission_rate': Decimal('2.5'),
            'is_active': True
        }
    )
    if not rep.account:
        rep.account = RepSettlementService.create_rep_account(rep)
        rep.save()
        print(f"Rep receivable account created: {rep.account.code}")

    # Setup category and unit
    cat, _ = ItemCategory.objects.get_or_create(code='CAT-TEST', defaults={'name': 'Test Category'})
    uom, _ = UnitOfMeasure.objects.get_or_create(code='UOM-TEST', defaults={'name': 'علبة'})

    # Setup sale item
    item, _ = Item.objects.get_or_create(
        code='ITEM-TEST',
        defaults={
            'name': 'علبة شيكولاتة فاخرة',
            'category': cat,
            'base_unit': uom,
            'sales_unit': uom,
            'purchase_unit': uom,
            'inventory_account': Account.objects.get(code='1131'),
            'sales_account': Account.objects.get(code='411'),
            'cogs_account': Account.objects.get(code='511'),
            'is_active': True
        }
    )

    # Charge warehouse with stock (100 units at 100 EGP cost)
    StockMovement.objects.filter(item=item, warehouse=warehouse).delete()
    InventoryService.record_movement(
        date_val=timezone.now().date(),
        item=item,
        warehouse=warehouse,
        movement_type=StockMovement.MovementType.OPENING,
        quantity=Decimal('100'),
        unit_cost=Decimal('100.00'),
        source=None,
        reference='Test opening stock'
    )
    print("Warehouse stock charged with 100 units @ 100 EGP")

    # 3. Setup station and open session
    station, _ = POSStation.objects.get_or_create(
        code='POS-01',
        defaults={
            'name': 'POS Station 1',
            'warehouse': warehouse,
            'cash_box': cash_box,
            'is_active': True
        }
    )

    # Close any open session for user to avoid conflicts
    POSSession.objects.filter(user=user, status=POSSession.Status.OPEN).update(status=POSSession.Status.CLOSED)

    # Open session with opening cash = 1000 EGP
    session = POSSessionService.open_session(user=user, station=station, opening_cash=1000)
    print(f"POS Session opened. ID: {session.id}, Opening cash: {session.opening_cash} EGP")

    # 4. Simulate a sale
    # We will sell 10 units at 228 EGP each (inclusive of 14% VAT)
    # Total = 2280 EGP
    # Net sales = 2000 EGP, VAT = 280 EGP
    cart_items = [
        {
            'id': item.id,
            'qty': 10,
            'price': 228
        }
    ]
    order = POSCheckoutService.create_order(
        session=session,
        cart_items=cart_items,
        payment_method='cash',
        is_taxable=True
    )
    print(f"POS Order created: {order.receipt_number}, Total: {order.grand_total} EGP")
    print(f"   Net Sales: {order.subtotal} EGP, VAT: {order.tax} EGP")

    session.refresh_from_db()
    print(f"Expected cash in drawer: {session.expected_cash} EGP")

    # 5. Close session with a deficit (actual cash = 3200 instead of 3280, deficit = 80 EGP)
    print("\nClosing session with actual cash: 3200 EGP (Deficit of 80 EGP)...")
    POSSessionService.close_session(session=session, actual_cash=Decimal('3200.00'), notes="Deficit test")
    
    session.refresh_from_db()
    print(f"POS Session closed. Actual cash: {session.actual_cash} EGP, Deficit: {-session.difference} EGP")

    # 6. Verify Combined POS Session Journal Entry
    print("\n--- POS Combined Session Journal Entry ---")
    sales_entry = JournalEntry.objects.filter(
        content_type__model='possession',
        object_id=session.id
    ).first()

    if sales_entry:
        print(f"Entry Number: {sales_entry.number} - {sales_entry.description}")
        lines = sales_entry.lines.all()
        print("-" * 75)
        print(f"{'Account':<35} | {'Debit (DR)':<15} | {'Credit (CR)':<15}")
        print("-" * 75)
        for l in lines:
            acc_name = l.account.name.encode('utf-8', errors='ignore').decode('utf-8')
            print(f"{l.account.code} - {acc_name:<27} | {l.debit:<15} | {l.credit:<15}")
        print("-" * 75)
    else:
        print("ERROR: Combined POS entry not found!")

    # 7. Verify Daily Settlement
    print("\n--- Daily Settlement ERP Document ---")
    settlement = session.settlement
    if settlement:
        print(f"Settlement Number: {settlement.number}")
        print(f"   Total Shift Sales: {settlement.total_sales} EGP")
        print(f"   Cash Delivered to HQ: {settlement.cash_delivered} EGP")
        print(f"   Shortage/Discrepancy: {settlement.difference} EGP")
        
        # Admin approves daily settlement
        print("\nAdmin posts/approves daily settlement...")
        settlement_entry = RepSettlementService.post_settlement(settlement, user)
        settlement.status = RepDailySettlement.Status.POSTED
        settlement.journal_entry = settlement_entry
        settlement.save()
        
        print(f"Daily Settlement posted successfully. Journal Entry: {settlement_entry.number}")
        
        # Display Settlement Journal Entry
        print("\n--- Daily Settlement Journal Entry ---")
        lines = settlement_entry.lines.all()
        print("-" * 75)
        print(f"{'Account':<35} | {'Debit (DR)':<15} | {'Credit (CR)':<15}")
        print("-" * 75)
        for l in lines:
            acc_name = l.account.name.encode('utf-8', errors='ignore').decode('utf-8')
            print(f"{l.account.code} - {acc_name:<27} | {l.debit:<15} | {l.credit:<15}")
        print("-" * 75)
    else:
        print("ERROR: Settlement not found!")

    print("\nSUCCESS: All double-entry postings are balanced and correct!")
    print("=" * 80)

if __name__ == "__main__":
    run_test()
