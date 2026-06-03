import os
import django
import sys
from decimal import Decimal
import time

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.inventory.models import Warehouse, Item, ItemCategory, UnitOfMeasure, ItemLedger, StockMovement
from apps.purchases.models import Supplier, PurchaseInvoice, PurchaseInvoiceLine, PurchaseReturn, PurchaseReturnLine
from apps.purchases.services import PurchaseService, SupplierService
from apps.core.models import Account, FiscalYear
from django.contrib.auth.models import User
from django.utils import timezone

def run_test():
    print("==================================================")
    print("     STARTING MULTI-UNIT VALUATION VALIDATION     ")
    print("==================================================")
    
    # 1. Setup User
    user, _ = User.objects.get_or_create(username='admin')

    # 2. Setup Fiscal Year
    today = timezone.now().date()
    active_fys = FiscalYear.objects.filter(start_date__lte=today, end_date__gte=today, is_closed=False)
    if not active_fys.exists():
        fy = FiscalYear.objects.create(
            name="2026_TEST_VAL",
            start_date=today.replace(month=1, day=1),
            end_date=today.replace(month=12, day=31),
            is_closed=False
        )
    elif active_fys.count() > 1:
        first_fy = active_fys.first()
        FiscalYear.objects.filter(start_date__lte=today, end_date__gte=today, is_closed=False).exclude(id=first_fy.id).update(is_closed=True)
        fy = first_fy
    else:
        fy = active_fys.first()

    # 3. Setup Accounts
    inv_parent, _ = Account.objects.get_or_create(code='12', defaults={'name': 'Inventory Accounts', 'account_type': 'asset', 'is_leaf': False})
    acc_main, _ = Account.objects.get_or_create(code='1201', defaults={'name': 'Main Inventory Account', 'account_type': 'asset', 'parent': inv_parent})
    acc_cogs, _ = Account.objects.get_or_create(code='511', defaults={'name': 'Cost of Goods Sold', 'account_type': 'expense'})
    acc_sales, _ = Account.objects.get_or_create(code='411', defaults={'name': 'Sales Revenue', 'account_type': 'revenue'})
    
    # 4. Setup UOMs (Piece and Box of 12)
    uom_pcs, _ = UnitOfMeasure.objects.get_or_create(code='PCS_T', defaults={'name': 'Piece'})
    uom_box, _ = UnitOfMeasure.objects.get_or_create(code='BOX_T', defaults={'name': 'Box of 12'})

    # 5. Setup Category & Item
    cat, _ = ItemCategory.objects.get_or_create(code='CAT_T', defaults={'name': 'Category T'})
    
    # Item: 1 Box = 12 Pieces
    item, _ = Item.objects.get_or_create(
        code='ITEM_VAL_TEST',
        defaults={
            'name': 'Boxed Item Test',
            'category': cat,
            'base_unit': uom_pcs,
            'purchase_unit': uom_box,
            'purchase_conversion_factor': Decimal('12.0000'),
            'inventory_account': acc_main,
            'cogs_account': acc_cogs,
            'sales_account': acc_sales
        }
    )
    
    # Ensure conversion factor is updated in case it already existed
    item.purchase_conversion_factor = Decimal('12.0000')
    item.purchase_unit = uom_box
    item.save()

    # 6. Setup Supplier
    supplier = SupplierService.create_supplier({
        'code': f'SUP-V-{int(time.time())}',
        'name': 'Valuation Supplier Co',
        'phone': '987654321'
    })

    wh_main, _ = Warehouse.objects.get_or_create(code='WH-MAIN-V', defaults={'name': 'Valuation Warehouse', 'gl_account': acc_main})

    # Clear pre-existing ledger and stock movements for this item to ensure clean test
    ItemLedger.objects.filter(item=item).delete()
    StockMovement.objects.filter(item=item).delete()

    print("\n--- STEP 1: Post Purchase Invoice of 10 Boxes @ $120.00/Box ---")
    print("(Expected: 120 Pieces in stock, WAC = $10.00/Piece, Total Value = $1,200.00)")
    
    invoice = PurchaseInvoice.objects.create(
        number=f"PINV-V-{int(time.time())}",
        supplier_invoice_number='SUP-VAL-001',
        date=timezone.now().date(),
        due_date=timezone.now().date(),
        supplier=supplier,
        subtotal=Decimal('1200.00'),
        total=Decimal('1200.00'),
        created_by=user,
        status='draft'
    )
    PurchaseInvoiceLine.objects.create(
        invoice=invoice,
        item=item,
        warehouse=wh_main,
        unit=uom_box,
        quantity=Decimal('10'),
        base_quantity=Decimal('120'),  # 10 Boxes * 12
        unit_cost=Decimal('120.00'),
        total=Decimal('1200.00')
    )

    PurchaseService.post_invoice(invoice, user)
    print("Purchase Invoice posted successfully.")

    # Check stock ledger
    ledger = ItemLedger.objects.get(item=item, warehouse=wh_main)
    print(f"Stock Qty: {ledger.quantity_on_hand} Pieces (Expected: 120)")
    print(f"Stock Value: {ledger.total_value} (Expected: 1200.00)")
    
    # Calculate WAC
    wac = ledger.total_value / ledger.quantity_on_hand if ledger.quantity_on_hand > 0 else 0
    print(f"Calculated WAC: {wac} (Expected: 10.00)")
    
    assert ledger.quantity_on_hand == Decimal('120.0000'), "FAIL: Quantity on hand is not 120"
    assert ledger.total_value == Decimal('1200.00'), "FAIL: Total stock value is not 1200"
    assert wac == Decimal('10.00'), "FAIL: WAC is not 10.00"
    print("[SUCCESS] Purchase Invoice posted with correct base unit valuation!")

    print("\n--- STEP 2: Post Purchase Return of 1 Box @ $120.00/Box ---")
    print("(Expected: stock reductions to 108 Pieces, WAC remains $10.00/Piece, Total Value = $1,080.00)")
    
    p_return = PurchaseReturn.objects.create(
        number=f"PRET-V-{int(time.time())}",
        date=timezone.now().date(),
        supplier=supplier,
        subtotal=Decimal('120.00'),
        total=Decimal('120.00'),
        created_by=user,
        status='draft'
    )
    PurchaseReturnLine.objects.create(
        purchase_return=p_return,
        item=item,
        warehouse=wh_main,
        unit=uom_box,
        quantity=Decimal('1'),
        base_quantity=Decimal('12'),  # 1 Box * 12
        unit_cost=Decimal('120.00'),
        total=Decimal('120.00')
    )

    PurchaseService.post_return(p_return, user)
    print("Purchase Return posted successfully.")

    ledger.refresh_from_db()
    print(f"Stock Qty: {ledger.quantity_on_hand} Pieces (Expected: 108)")
    print(f"Stock Value: {ledger.total_value} (Expected: 1080.00)")
    
    wac = ledger.total_value / ledger.quantity_on_hand if ledger.quantity_on_hand > 0 else 0
    print(f"Calculated WAC: {wac} (Expected: 10.00)")

    # Verify last stock movement unit cost
    last_movement = StockMovement.objects.filter(item=item, movement_type=StockMovement.MovementType.PURCHASE_RETURN).order_by('-id').first()
    print(f"Last Movement Qty: {last_movement.quantity} (Expected: -12)")
    print(f"Last Movement Unit Cost: {last_movement.unit_cost} (Expected: 10.00)")
    print(f"Last Movement Total Cost: {last_movement.total_cost} (Expected: -120.00)")

    assert ledger.quantity_on_hand == Decimal('108.0000'), "FAIL: Quantity on hand is not 108"
    assert ledger.total_value == Decimal('1080.00'), "FAIL: Total stock value is not 1080"
    assert wac == Decimal('10.00'), "FAIL: WAC is not 10.00"
    assert last_movement.unit_cost == Decimal('10.00'), "FAIL: Movement unit cost is not 10.00"
    assert last_movement.total_cost == Decimal('-120.00'), "FAIL: Movement total cost is not -120.00"
    print("[SUCCESS] Purchase Return posted with correct base unit cost conversion!")

    print("\n--- STEP 3: Reversing the Purchase Invoice ---")
    print("(Simulating reversal of another clean 2-Box Invoice to keep stock above zero)")
    
    invoice2 = PurchaseInvoice.objects.create(
        number=f"PINV-V2-{int(time.time())}",
        supplier_invoice_number='SUP-VAL-002',
        date=timezone.now().date(),
        due_date=timezone.now().date(),
        supplier=supplier,
        subtotal=Decimal('240.00'),
        total=Decimal('240.00'),
        created_by=user,
        status='draft'
    )
    PurchaseInvoiceLine.objects.create(
        invoice=invoice2,
        item=item,
        warehouse=wh_main,
        unit=uom_box,
        quantity=Decimal('2'),
        base_quantity=Decimal('24'),  # 2 Boxes * 12 = 24
        unit_cost=Decimal('120.00'),
        total=Decimal('240.00')
    )

    PurchaseService.post_invoice(invoice2, user)
    ledger.refresh_from_db()
    print(f"Stock Qty after Invoice 2: {ledger.quantity_on_hand} Pieces (Expected: 132)")
    print(f"Stock Value after Invoice 2: {ledger.total_value} (Expected: 1320.00)")

    invoice2.refresh_from_db()
    PurchaseService.reverse_invoice(invoice2, user)
    print("Purchase Invoice 2 reversed successfully.")

    ledger.refresh_from_db()
    print(f"Stock Qty after Reversal: {ledger.quantity_on_hand} Pieces (Expected: 108)")
    print(f"Stock Value after Reversal: {ledger.total_value} (Expected: 1080.00)")

    last_rev_mov = StockMovement.objects.filter(item=item, object_id=invoice2.id).order_by('-id').first()
    print(f"Reversal Movement Qty: {last_rev_mov.quantity} (Expected: -24)")
    print(f"Reversal Movement Unit Cost: {last_rev_mov.unit_cost} (Expected: 10.00)")
    print(f"Reversal Movement Total Cost: {last_rev_mov.total_cost} (Expected: -240.00)")

    assert ledger.quantity_on_hand == Decimal('108.0000'), "FAIL: Quantity on hand is not 108 after reversal"
    assert ledger.total_value == Decimal('1080.00'), "FAIL: Total stock value is not 1080 after reversal"
    assert last_rev_mov.unit_cost == Decimal('10.00'), "FAIL: Reversal unit cost is not 10.00"
    assert last_rev_mov.total_cost == Decimal('-240.00'), "FAIL: Reversal total cost is not -240.00"
    print("[SUCCESS] Purchase Invoice Reversal successfully converted purchase unit costs to base unit costs!")

    # 7. Cleanup
    print("\n--- Cleaning up test records ---")
    ItemLedger.objects.filter(item=item).delete()
    StockMovement.objects.filter(item=item).delete()
    
    from apps.core.models import JournalEntry, JournalLine
    je_ids = list(JournalLine.objects.filter(account=supplier.account).values_list('entry_id', flat=True))

    invoice.lines.all().delete()
    invoice.delete()
    invoice2.lines.all().delete()
    invoice2.delete()
    p_return.lines.all().delete()
    p_return.delete()

    if je_ids:
        JournalLine.objects.filter(entry_id__in=je_ids).delete()
        JournalEntry.objects.filter(id__in=je_ids).delete()

    supp_acc = supplier.account
    supplier.delete()
    if supp_acc:
        supp_acc.delete()
    print("Cleanup completed successfully.")
    print("==================================================")
    print("       ALL VALUATION VALIDATION TESTS PASSED      ")
    print("==================================================")

if __name__ == "__main__":
    try:
        run_test()
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
