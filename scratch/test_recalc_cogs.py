import os
import django
import sys
from decimal import Decimal

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.inventory.models import Warehouse, Item, ItemCategory, UnitOfMeasure, StockMovement, ItemLedger
from apps.inventory.services import InventoryService
from apps.sales.models import SalesInvoice, SalesInvoiceLine, Customer, SalesReturn, SalesReturnLine
from apps.sales.services import SalesService
from apps.core.models import Account, FiscalYear, CostCenter, JournalEntry, JournalLine
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import transaction

def run_tests():
    print("==================================================")
    print("      STARTING INVENTORY & GL COGS VALIDATION     ")
    print("==================================================")
    
    # 1. Setup global prerequisite objects
    user = User.objects.filter(is_superuser=True).first() or User.objects.first()
    if not user:
        user = User.objects.create_superuser('admin_test', 'admin@test.com', 'admin_test')
        
    # Get or create Fiscal Year
    fy = FiscalYear.objects.filter(is_closed=False).first()
    if not fy:
        fy = FiscalYear.objects.create(
            name="Test Fiscal Year",
            start_date=timezone.now().date().replace(month=1, day=1),
            end_date=timezone.now().date().replace(month=12, day=31)
        )
        
    # Setup accounts
    inv_parent, _ = Account.objects.get_or_create(code='113', defaults={'name': 'Inventory Accounts', 'account_type': 'asset', 'is_leaf': False})
    acc_inv, _ = Account.objects.get_or_create(code='11399', defaults={'name': 'Test Inventory Account', 'account_type': 'asset', 'parent': inv_parent})
    acc_cogs, _ = Account.objects.get_or_create(code='51199', defaults={'name': 'Test Cost of Goods Sold', 'account_type': 'expense'})
    acc_sales, _ = Account.objects.get_or_create(code='41199', defaults={'name': 'Test Sales Revenue', 'account_type': 'revenue'})
    acc_return, _ = Account.objects.get_or_create(code='41299', defaults={'name': 'Test Sales Returns', 'account_type': 'revenue'})
    acc_cust, _ = Account.objects.get_or_create(code='11299', defaults={'name': 'Test Customer AR Account', 'account_type': 'asset'})
    
    # Setup Warehouse
    wh = Warehouse.objects.get_or_create(code='WH-TEST-WAC', defaults={'name': 'WAC Test Warehouse', 'gl_account': acc_inv})[0]
    
    # Setup Cost Center (Project)
    cc = CostCenter.objects.get_or_create(code='CC-TEST-PROJ', defaults={'name': 'Test Project Cost Center', 'is_leaf': True})[0]
    
    # Setup Customer
    customer = Customer.objects.get_or_create(name='Test WAC Customer', defaults={'account': acc_cust, 'code': 'CUS-TEST-WAC'})[0]
    
    # Setup Item
    cat = ItemCategory.objects.get_or_create(code='CAT-WAC', name='WAC Category')[0]
    unit = UnitOfMeasure.objects.get_or_create(code='PCS-WAC', name='Piece WAC')[0]
    item = Item.objects.get_or_create(
        code='ITEM-WAC-TEST', 
        defaults={
            'name': 'WAC Test Item', 
            'category': cat, 
            'base_unit': unit,
            'inventory_account': acc_inv,
            'cogs_account': acc_cogs,
            'sales_account': acc_sales
        }
    )[0]
    
    # Clean any existing ledger and stock movements for clean testing state
    StockMovement.objects.filter(item=item, warehouse=wh).delete()
    ItemLedger.objects.filter(item=item, warehouse=wh).delete()
    
    # -------------------------------------------------------------
    # TEST 1: Sales Return Cost Center Project-Level Mapping
    # -------------------------------------------------------------
    print("\n--- TEST 1: Sales Return Cost Center Return Mapping ---")
    
    # Let's seed initial stock first so sales goes through
    InventoryService.record_movement(
        date_val=timezone.now().date(),
        item=item,
        warehouse=wh,
        movement_type=StockMovement.MovementType.OPENING,
        quantity=Decimal('100.00'),
        unit_cost=Decimal('10.00'),
        reference='Initial Stock Seed'
    )
    
    # Post sales invoice with cost center
    inv = SalesInvoice.objects.create(
        number=f'T-INV-CC-{timezone.now().timestamp()}',
        date=timezone.now().date(),
        due_date=timezone.now().date(),
        customer=customer,
        payment_type='credit',
        created_by=user,
        status='draft',
        subtotal=Decimal('50.00'),
        total=Decimal('50.00'),
        cost_center=cc
    )
    
    inv_line = SalesInvoiceLine.objects.create(
        invoice=inv,
        item=item,
        warehouse=wh,
        quantity=Decimal('5.00'),
        unit_price=Decimal('10.00'),
        total=Decimal('50.00'),
        revenue_account=acc_sales,
        cost_of_goods_account=acc_cogs
    )
    
    # Post Invoice
    SalesService.post_invoice(inv, user)
    print(f"Posted Sales Invoice {inv.number} with Cost Center {cc.name}.")
    
    # Create Sales Return
    sales_return = SalesReturn.objects.create(
        number=f'T-RET-CC-{timezone.now().timestamp()}',
        date=timezone.now().date(),
        invoice=inv,
        customer=customer,
        status='draft',
        subtotal=Decimal('50.00'),
        total=Decimal('50.00'),
        created_by=user,
        payment_type='credit'
    )
    
    ret_line = SalesReturnLine.objects.create(
        sales_return=sales_return,
        item=item,
        warehouse=wh,
        quantity=Decimal('5.00'),
        base_quantity=Decimal('5.00'),
        unit_price=Decimal('10.00'),
        total=Decimal('50.00'),
        cost=Decimal('10.00'),
        return_account=acc_return,
        cogs_account=acc_cogs
    )
    
    # Post Sales Return
    entry = SalesService.post_return(sales_return, user)
    print(f"Posted Sales Return {sales_return.number}. Linked GL Entry: {entry.number}")
    
    # Check all lines in the posted return's journal entry
    jlines = entry.lines.all()
    print(f"Return Journal Entry has {jlines.count()} lines. Checking cost centers:")
    all_matched = True
    for jl in jlines:
        print(f"  - Account: {jl.account.code} | Debit: {jl.debit} | Credit: {jl.credit} | Cost Center: {jl.cost_center}")
        if jl.cost_center != cc:
            all_matched = False
            
    if all_matched:
        print("[SUCCESS] All Return GL lines correctly inherited the original Sales Invoice Cost Center!")
    else:
        print("[FAILURE] Return GL lines failed to inherit the Cost Center correctly.")
        
    # Clean return and invoice for Test 2
    sales_return.delete()
    inv.delete()
    StockMovement.objects.filter(item=item, warehouse=wh).delete()
    ItemLedger.objects.filter(item=item, warehouse=wh).delete()
    
    # -------------------------------------------------------------
    # TEST 2: WAC Recalculation & Cascade Propagation
    # -------------------------------------------------------------
    print("\n--- TEST 2: WAC Recalculation and GL Propagation ---")
    
    # Step A: Seed Purchase Receipt 1 at 10.00
    p1 = InventoryService.record_movement(
        date_val=timezone.now().date(),
        item=item,
        warehouse=wh,
        movement_type=StockMovement.MovementType.PURCHASE_RECEIPT,
        quantity=Decimal('10.00'),
        unit_cost=Decimal('10.00'),
        reference='P1'
    )
    
    # Recalculate to set initial averages
    InventoryService.recalculate_item_ledger(item, wh)
    print(f"Purchase 1: 10 units at 10.00. Current Average Cost: {InventoryService.get_item_cost(item, wh)}")
    
    # Step B: Create and post a sales invoice for 5 units
    inv2 = SalesInvoice.objects.create(
        number=f'T-INV-WAC-{timezone.now().timestamp()}',
        date=timezone.now().date(),
        due_date=timezone.now().date(),
        customer=customer,
        payment_type='credit',
        created_by=user,
        status='draft',
        subtotal=Decimal('150.00'),
        total=Decimal('150.00')
    )
    
    inv_line2 = SalesInvoiceLine.objects.create(
        invoice=inv2,
        item=item,
        warehouse=wh,
        quantity=Decimal('5.00'),
        unit_price=Decimal('30.00'),
        total=Decimal('150.00'),
        revenue_account=acc_sales,
        cost_of_goods_account=acc_cogs
    )
    
    SalesService.post_invoice(inv2, user)
    inv2.refresh_from_db()
    inv_line2.refresh_from_db()
    print(f"Posted Sales Invoice {inv2.number}. Unit Cost at Sale: {inv_line2.cost}")
    
    # Let's inspect the GL entry for the Sales Invoice
    print("Initial Sales Invoice GL lines:")
    for jl in inv2.journal_entry.lines.all():
        print(f"  - Account: {jl.account.name} | Debit: {jl.debit} | Credit: {jl.credit}")
        
    # Step C: Backdate Purchase Receipt 2 at 22.00 BEFORE the sales invoice
    # We simulate this by inserting it into the database with a date (or ID ordering).
    # Since recalculation sorts by 'date' and then 'id', inserting it here will make it sit before or after.
    # To guarantee it sit before the sale, let's look at the dates. Both are timezone.now().date().
    # But since it has a lower ID, or we can make the date of the new purchase a day earlier to simulate backdating!
    yesterday = timezone.now().date() - timezone.timedelta(days=1)
    p2 = InventoryService.record_movement(
        date_val=yesterday,
        item=item,
        warehouse=wh,
        movement_type=StockMovement.MovementType.PURCHASE_RECEIPT,
        quantity=Decimal('10.00'),
        unit_cost=Decimal('22.00'),
        reference='P2 Backdated'
    )
    print(f"Inserted backdated Purchase: 10 units at 22.00 on {yesterday}.")
    
    # Step D: Trigger WAC Recalculation
    print("Triggering WAC Recalculation...")
    InventoryService.recalculate_item_ledger(item, wh)
    
    # Step E: Validate results
    # 1. New expected average cost:
    # (10 * 10.00 + 10 * 22.00) / 20 = (100 + 220) / 20 = 320 / 20 = 16.00.
    # 2. Sales stock movement unit cost should be updated to 16.00, total_cost to -80.00.
    # 3. Sales Invoice Line cost should be updated to 16.00.
    # 4. GL lines for COGS and Inventory should be updated to 80.00.
    
    # Fetch recalculated sales movement
    sale_mov = StockMovement.objects.get(
        item=item, 
        warehouse=wh, 
        movement_type=StockMovement.MovementType.SALES_ISSUE,
        content_type=inv2.journal_entry.content_type, # generic foreign key content type
        object_id=inv2.id
    )
    
    inv_line2.refresh_from_db()
    inv2.journal_entry.refresh_from_db()
    
    print("\nRecalculated State:")
    print(f"  - Sales Stock Movement Unit Cost: {sale_mov.unit_cost} (Expected: 16.00)")
    print(f"  - Sales Stock Movement Total Cost: {sale_mov.total_cost} (Expected: -80.00)")
    print(f"  - Sales Invoice Line cost field: {inv_line2.cost} (Expected: 16.00)")
    
    print("Recalculated Sales Invoice GL lines:")
    cogs_updated = False
    inv_updated = False
    for jl in inv2.journal_entry.lines.all():
        print(f"  - Account: {jl.account.name} | Debit: {jl.debit} | Credit: {jl.credit}")
        if jl.account == acc_cogs and jl.debit == Decimal('80.00'):
            cogs_updated = True
        if jl.account == acc_inv and jl.credit == Decimal('80.00'):
            inv_updated = True
            
    if sale_mov.unit_cost == Decimal('16.00') and inv_line2.cost == Decimal('16.00') and cogs_updated and inv_updated:
        print("\n[SUCCESS] WAC Recalculation, invoice line cost, and GL entries correctly retroactively updated!")
    else:
        print("\n[FAILURE] Cost did not cascade/propagate correctly to all components.")

    # Cleanup database records
    print("\nCleaning up database records...")
    # Delete child entries first
    StockMovement.objects.filter(item=item).delete()
    ItemLedger.objects.filter(item=item).delete()
    
    # Delete all associated journal lines and entries created during test
    from apps.core.models import JournalEntry, JournalLine
    from django.contrib.contenttypes.models import ContentType
    
    invoice_ct = ContentType.objects.get_for_model(SalesInvoice)
    return_ct = ContentType.objects.get_for_model(SalesReturn)
    
    # We delete returns first, then invoices which will cascade delete their lines
    SalesReturn.objects.filter(number__contains='T-RET').delete()
    SalesInvoice.objects.filter(number__contains='T-INV').delete()
    
    # Delete journal entries linked to these models
    JournalEntry.objects.filter(content_type__in=[invoice_ct, return_ct]).delete()
    
    # Now delete parent entities
    wh.delete()
    cc.delete()
    customer.delete()
    item.delete()
    print("Cleanup completed successfully.")

if __name__ == "__main__":
    run_tests()
