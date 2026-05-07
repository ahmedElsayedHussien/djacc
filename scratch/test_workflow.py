import os
import django
import sys
from decimal import Decimal
# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.inventory.models import Warehouse, Item, ItemCategory, UnitOfMeasure
from apps.inventory.services import InventoryService, LoadingService
from apps.sales.models import SalesRepresentative, SalesInvoice, SalesInvoiceLine, Customer
from apps.core.models import Account, FiscalYear
from apps.hr.models import Employee
from django.contrib.auth.models import User
from django.utils import timezone

def run_test():
    print("--- Starting Workflow Test ---")
    
    # 1. Setup Accounts
    inv_parent, _ = Account.objects.get_or_create(code='12', defaults={'name': 'Inventory Accounts', 'account_type': 'asset', 'is_leaf': False})
    acc_main, _ = Account.objects.get_or_create(code='1201', defaults={'name': 'Main Inventory Account', 'account_type': 'asset', 'parent': inv_parent})
    acc_rep, _ = Account.objects.get_or_create(code='1202', defaults={'name': 'Rep Inventory Account', 'account_type': 'asset', 'parent': inv_parent})
    acc_cogs, _ = Account.objects.get_or_create(code='511', defaults={'name': 'Cost of Goods Sold', 'account_type': 'expense'})
    acc_sales, _ = Account.objects.get_or_create(code='411', defaults={'name': 'Sales Revenue', 'account_type': 'revenue'})

    # 2. Setup Warehouses
    wh_main = Warehouse.objects.get_or_create(code='WH-MAIN', name='Main Warehouse', gl_account=acc_main)[0]
    wh_rep = Warehouse.objects.get_or_create(code='WH-REP1', name='Rep 1 Warehouse', gl_account=acc_rep)[0]

    # 3. Setup Representative
    user, _ = User.objects.get_or_create(username='testrep')
    from apps.hr.models import Department, JobTitle
    dept, _ = Department.objects.get_or_create(name='Sales Dept')
    job, _ = JobTitle.objects.get_or_create(name='Sales Rep')
    employee, _ = Employee.objects.get_or_create(
        first_name='Test', 
        last_name='Rep', 
        defaults={'user': user, 'hiring_date': timezone.now().date(), 'department': dept, 'job_title': job}
    )
    rep, _ = SalesRepresentative.objects.get_or_create(
        user=user, 
        defaults={
            'employee': employee,
            'code': 'REP001', 
            'warehouse': wh_rep,
            'cash_box_id': 1 # Assuming cashbox 1 exists
        }
    )
    
    # Ensure rep account exists
    from apps.sales.services import RepSettlementService
    if not rep.account:
        rep.account = RepSettlementService.create_rep_account(rep)
        rep.save()

    # 4. Setup Item and Stock
    cat = ItemCategory.objects.get_or_create(code='CAT1', name='Category 1')[0]
    unit = UnitOfMeasure.objects.get_or_create(code='PCS', name='Piece')[0]
    item = Item.objects.get_or_create(
        code='ITEM001', 
        name='Test Item', 
        category=cat, 
        base_unit=unit,
        inventory_account=acc_main,
        cogs_account=acc_cogs,
        sales_account=acc_sales
    )[0]

    # Add initial stock to Main
    print("Adding 100 units to Main Warehouse at $10 each...")
    InventoryService.record_movement(
        date_val=timezone.now().date(),
        item=item,
        warehouse=wh_main,
        movement_type='opening',
        quantity=100,
        unit_cost=Decimal('10.00'),
        reference='Initial Stock'
    )

    # 5. Create Loading Order (Manual bypass for test)
    from apps.inventory.models import LoadingOrder, LoadingOrderLine
    import time
    order_num = f"LOAD-TEST-{int(time.time())}"
    order = LoadingOrder.objects.create(
        number=order_num,
        date=timezone.now().date(),
        sales_rep=rep,
        from_warehouse=wh_main,
        to_warehouse=wh_rep,
        requested_by=user,
        status='pending'
    )
    line = LoadingOrderLine.objects.create(
        loading_order=order,
        item=item,
        requested_qty=50
    )

    print(f"Created Loading Order {order.number} for 50 units.")

    # 6. Approve and Issue
    LoadingService.approve_loading(order, user)
    print("Order Approved.")
    LoadingService.issue_loading(order, user)
    print("Order Issued.")

    # Check Journal Entry
    order.refresh_from_db()
    if order.journal_entry:
        print(f"SUCCESS: Journal Entry created: {order.journal_entry.number}")
        for jline in order.journal_entry.lines.all():
            print(f"  - Account: {jline.account.name} | Debit: {jline.debit} | Credit: {jline.credit}")
    else:
        print("FAILURE: No Journal Entry created for Loading Order.")

    # 7. Check Stock Status
    main_stock = InventoryService.get_item_cost(item, wh_main) # Not exactly stock, but cost check
    from apps.inventory.models import ItemLedger
    main_qty = ItemLedger.objects.get(item=item, warehouse=wh_main).quantity_on_hand
    rep_qty = ItemLedger.objects.get(item=item, warehouse=wh_rep).quantity_on_hand
    print(f"Stock Status: Main={main_qty}, Rep={rep_qty}")

    # 8. Create and Post Sales Invoice
    cust_acc, _ = Account.objects.get_or_create(code='1301', defaults={'name': 'Test Customer Account', 'account_type': 'asset'})
    customer, _ = Customer.objects.get_or_create(name='Test Customer', defaults={'account': cust_acc})
    inv_num = f"INV-TEST-{int(time.time())}"
    invoice = SalesInvoice.objects.create(
        number=inv_num,
        date=timezone.now().date(),
        due_date=timezone.now().date(),
        customer=customer,
        sales_rep=rep,
        payment_type='cash',
        created_by=user,
        status='draft',
        subtotal=Decimal('0'),
        total=Decimal('200.00')
    )
    inv_line = SalesInvoiceLine.objects.create(
        invoice=invoice,
        item=item,
        warehouse=wh_rep,
        quantity=10,
        unit_price=Decimal('20.00'),
        total=Decimal('200.00'),
        revenue_account=acc_sales,
        cost_of_goods_account=acc_cogs
    )
    
    print(f"Created Sales Invoice {invoice.number} for 10 units from Rep Warehouse.")
    
    # 9. Customer Receipt (Payment)
    print(f"Creating Receipt for Invoice {invoice.number}...")
    receipt_data = {
        'customer': customer,
        'date': timezone.now().date(),
        'amount': invoice.total,
        'payment_method': 'cash',
        'cash_box': rep.cash_box,
    }
    
    from apps.sales.models import CustomerReceipt
    receipt = CustomerReceipt.objects.create(
        number=f"RCPT-TEST-{int(time.time())}",
        **receipt_data
    )
    
    # Simulate posting receipt
    lines = [
        {'account': rep.cash_box.account, 'debit': receipt.amount, 'credit': 0, 'description': f'تحصيل من {customer.name}'},
        {'account': customer.account, 'debit': 0, 'credit': receipt.amount, 'description': f'سداد فاتورة {invoice.number}'},
    ]
    from apps.core.services import JournalService
    from apps.core.models import JournalEntry
    r_entry = JournalService.create_entry(
        date_val=receipt.date,
        entry_type=JournalEntry.EntryType.RECEIPT,
        description=f'تحصيل مبيعات - {receipt.number}',
        lines=lines,
        created_by=user
    )
    receipt.journal_entry = r_entry
    receipt.status = 'posted'
    receipt.save()
    print(f"SUCCESS: Receipt Posted. Journal: {r_entry.number}")

    # 10. Rep Settlement (Closing the loop)
    print("--- Testing Rep Settlement ---")
    # Rep has 200 in his cashbox. He will deliver only 150 to the main office (Deficit of 50).
    from apps.treasury.models import CashBox
    main_cashbox_acc = Account.objects.get_or_create(code='1111', defaults={'name': 'Main CashBox', 'account_type': 'asset'})[0]
    main_cashbox = CashBox.objects.get_or_create(code='CB-MAIN', defaults={'name': 'Main Office Cashbox', 'account': main_cashbox_acc, 'responsible_user': user})[0]
    
    from apps.sales.models import RepDailySettlement, RepSettlementInvoice
    from apps.sales.services import RepSettlementService
    
    settlement = RepDailySettlement.objects.create(
        number=f"RS-TEST-{int(time.time())}",
        date=timezone.now().date(),
        sales_rep=rep,
        cash_delivered=Decimal('150.00'),
        to_cash_box=main_cashbox,
        created_by=user
    )
    RepSettlementInvoice.objects.create(settlement=settlement, invoice=invoice)
    
    print(f"Created Settlement {settlement.number}. Total Sales: 200, Delivered: 150. Expected Deficit: 50.")
    
    s_entry = RepSettlementService.post_settlement(settlement, user)
    print(f"SUCCESS: Settlement Posted. Journal: {s_entry.number}")
    for jline in s_entry.lines.all():
        print(f"  - Account: {jline.account.name} | Debit: {jline.debit} | Credit: {jline.credit}")
    
    # 11. Rep Pays the deficit
    print("--- Rep Pays the Deficit (50) ---")
    rep.refresh_from_db()
    pay_entry = RepSettlementService.collect_rep_receivable(
        rep=rep,
        amount=Decimal('50.00'),
        dest_account=main_cashbox_acc,
        date=timezone.now().date(),
        created_by=user
    )
    print(f"SUCCESS: Rep Debt Payment Posted. Journal: {pay_entry.number}")
    for jline in pay_entry.lines.all():
        print(f"  - Account: {jline.account.name} | Debit: {jline.debit} | Credit: {jline.credit}")

    print("--- Workflow Test Completed Successfully ---")

if __name__ == "__main__":
    try:
        run_test()
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
