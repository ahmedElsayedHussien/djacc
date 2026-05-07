import os
import django
import sys
from decimal import Decimal
import time

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.inventory.models import Warehouse, Item, ItemCategory, UnitOfMeasure
from apps.purchases.models import Supplier, PurchaseInvoice, PurchaseInvoiceLine, SupplierPayment
from apps.purchases.services import PurchaseService, SupplierService
from apps.core.models import Account, FiscalYear
from django.contrib.auth.models import User
from django.utils import timezone
from apps.treasury.models import CashBox

def run_test():
    print("--- Starting Purchase Workflow Test ---")
    user = User.objects.get_or_create(username='admin')[0]
    
    # 1. Setup Accounts
    inv_parent, _ = Account.objects.get_or_create(code='12', defaults={'name': 'Inventory Accounts', 'account_type': 'asset', 'is_leaf': False})
    acc_main = Account.objects.get_or_create(code='1201', defaults={'name': 'Main Inventory Account', 'account_type': 'asset', 'parent': inv_parent})[0]
    
    pay_parent, _ = Account.objects.get_or_create(code='211', defaults={'name': 'Accounts Payable', 'account_type': 'liability', 'is_leaf': False})
    
    # 2. Setup Supplier
    print("Creating Supplier...")
    supplier = SupplierService.create_supplier({
        'code': f'SUP-{int(time.time())}',
        'name': 'Global Trading Co',
        'phone': '123456789'
    })
    print(f"Supplier created with Account: {supplier.account.code}")

    # 3. Setup Warehouse and Item
    wh_main = Warehouse.objects.get_or_create(code='WH-MAIN', defaults={'name': 'Main Warehouse', 'gl_account': acc_main})[0]
    cat = ItemCategory.objects.get_or_create(code='CAT1', name='Category 1')[0]
    unit = UnitOfMeasure.objects.get_or_create(code='PCS', name='Piece')[0]
    acc_cogs, _ = Account.objects.get_or_create(code='511', defaults={'name': 'Cost of Goods Sold', 'account_type': 'expense'})
    acc_sales, _ = Account.objects.get_or_create(code='411', defaults={'name': 'Sales Revenue', 'account_type': 'revenue'})
    item = Item.objects.get_or_create(
        code='ITEM002', 
        defaults={
            'name': 'Raw Material A', 
            'category': cat, 
            'base_unit': unit,
            'inventory_account': acc_main,
            'cogs_account': acc_cogs,
            'sales_account': acc_sales
        }
    )[0]

    # 4. Create Purchase Invoice
    print("Creating Purchase Invoice...")
    inv_num = f"PINV-TEST-{int(time.time())}"
    invoice = PurchaseInvoice.objects.create(
        number=inv_num,
        supplier_invoice_number='SUP-001',
        date=timezone.now().date(),
        due_date=timezone.now().date(),
        supplier=supplier,
        subtotal=Decimal('1000.00'),
        total=Decimal('1000.00'),
        created_by=user,
        status='draft'
    )
    PurchaseInvoiceLine.objects.create(
        invoice=invoice,
        item=item,
        warehouse=wh_main,
        quantity=Decimal('100'),
        unit_cost=Decimal('10.00'),
        total=Decimal('1000.00')
    )

    # 5. Post Invoice
    print("Posting Invoice...")
    entry = PurchaseService.post_invoice(invoice, user)
    print(f"SUCCESS: Purchase Journal Entry: {entry.number}")
    for jline in entry.lines.all():
        print(f"  - Account: {jline.account.name} | Debit: {jline.debit} | Credit: {jline.credit}")

    # Check Stock
    from apps.inventory.models import ItemLedger
    qty = ItemLedger.objects.get(item=item, warehouse=wh_main).quantity_on_hand
    print(f"Current Stock: {qty} (Expected 100)")

    # 6. Supplier Payment
    print("Recording Supplier Payment (500)...")
    cash_acc = Account.objects.get_or_create(code='1111', defaults={'name': 'Main CashBox', 'account_type': 'asset'})[0]
    cash_box = CashBox.objects.get_or_create(code='CB-MAIN', defaults={'name': 'Main Office Cashbox', 'account': cash_acc, 'responsible_user': user})[0]
    
    payment = SupplierPayment.objects.create(
        number=f"PAY-TEST-{int(time.time())}",
        date=timezone.now().date(),
        supplier=supplier,
        amount=Decimal('500.00'),
        payment_method='cash',
        cash_box=cash_box,
        created_by=user
    )
    from apps.purchases.models import PaymentAllocation
    PaymentAllocation.objects.create(payment=payment, invoice=invoice, amount=Decimal('500.00'))
    
    p_entry = PurchaseService.record_payment(payment, user)
    print(f"SUCCESS: Payment Journal Entry: {p_entry.number}")
    for jline in p_entry.lines.all():
        print(f"  - Account: {jline.account.name} | Debit: {jline.debit} | Credit: {jline.credit}")

    invoice.refresh_from_db()
    print(f"Invoice Paid Amount: {invoice.paid_amount} (Expected 500)")

    print("--- Purchase Workflow Test Completed Successfully ---")

if __name__ == "__main__":
    try:
        run_test()
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
