import os
import sys
import django
import random
from decimal import Decimal
from datetime import date, timedelta

# Set up Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.core.models import Account, AccountType, FiscalYear
from apps.inventory.models import Item, ItemCategory, UnitOfMeasure, Warehouse
from apps.treasury.models import CashBox
from apps.sales.models import Customer, SalesRepresentative, SalesInvoice, SalesInvoiceLine, SalesTarget
from django.contrib.auth import get_user_model

User = get_user_model()

def seed_data():
    print("Starting data seeding...")
    
    # 1. Get or Create User
    user = User.objects.first()
    if not user:
        user = User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
    
    # 2. Get or Create Fiscal Year
    fy, _ = FiscalYear.objects.get_or_create(
        name="سنة 2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31)
    )

    # 3. Get or Create Basic Accounts if not exists
    # We need: Inventory (Asset), COGS (Expense), Sales (Revenue)
    inv_acc, _ = Account.objects.get_or_create(code='1131', defaults={'name': 'مخزون بضاعة', 'account_type': AccountType.ASSET})
    cogs_acc, _ = Account.objects.get_or_create(code='511', defaults={'name': 'تكلفة البضاعة المباعة', 'account_type': AccountType.EXPENSE})
    sales_acc, _ = Account.objects.get_or_create(code='411', defaults={'name': 'مبيعات بضاعة', 'account_type': AccountType.REVENUE})
    cust_acc, _ = Account.objects.get_or_create(code='1121', defaults={'name': 'عملاء تجاريون', 'account_type': AccountType.ASSET})
    cash_acc, _ = Account.objects.get_or_create(code='1111', defaults={'name': 'الصندوق الرئيسي', 'account_type': AccountType.ASSET})

    # 4. Inventory Setup
    cat, _ = ItemCategory.objects.get_or_create(code='CAT01', defaults={'name': 'إلكترونيات'})
    uom, _ = UnitOfMeasure.objects.get_or_create(code='PCS', defaults={'name': 'قطعة'})
    wh, _ = Warehouse.objects.get_or_create(code='MAIN', defaults={'name': 'المخزن الرئيسي', 'gl_account': inv_acc})

    # 4.5 Treasury Setup
    # Try to find a cashbox with the account, or create a new one
    main_cash = CashBox.objects.filter(account=cash_acc).first()
    if not main_cash:
        main_cash, _ = CashBox.objects.get_or_create(
            code='CASH_TEST',
            defaults={
                'name': 'الخزينة الرئيسية للاختبار',
                'account': cash_acc,
                'responsible_user': user
            }
        )

    # 5. Create Items
    items_data = [
        {'code': 'ITEM001', 'name': 'لاب توب ديل', 'price': 25000},
        {'code': 'ITEM002', 'name': 'شاشة سامسونج 24', 'price': 4500},
        {'code': 'ITEM003', 'name': 'ماوس لاسلكي', 'price': 350},
    ]
    items = []
    for item_info in items_data:
        item, _ = Item.objects.get_or_create(
            code=item_info['code'],
            defaults={
                'name': item_info['name'],
                'category': cat,
                'base_unit': uom,
                'inventory_account': inv_acc,
                'cogs_account': cogs_acc,
                'sales_account': sales_acc
            }
        )
        items.append((item, item_info['price']))

    # 6. Create Sales Reps
    reps_data = [
        {'code': 'REP01', 'name': 'أحمد محمد', 'username': 'rep_ahmed'},
        {'code': 'REP02', 'name': 'سارة أحمد', 'username': 'rep_sara'},
    ]
    reps = []
    for rep_info in reps_data:
        rep_user, _ = User.objects.get_or_create(
            username=rep_info['username'],
            defaults={'email': f"{rep_info['username']}@example.com"}
        )
        rep, _ = SalesRepresentative.objects.get_or_create(
            code=rep_info['code'],
            defaults={
                'name': rep_info['name'],
                'user': rep_user,
                'warehouse': wh,
                'cash_box': main_cash
            }
        )
        reps.append(rep)

    # 7. Create Customers
    customers_data = [
        {'code': 'CUST001', 'name': 'شركة النيل للتجارة', 'acc_code': '1121001'},
        {'code': 'CUST002', 'name': 'مؤسسة الأمل', 'acc_code': '1121002'},
        {'code': 'CUST003', 'name': 'الشركة العالمية', 'acc_code': '1121003'},
    ]
    customers = []
    for cust_info in customers_data:
        # Create unique account for each customer
        a, _ = Account.objects.get_or_create(
            code=cust_info['acc_code'],
            defaults={
                'name': f"حساب {cust_info['name']}",
                'account_type': AccountType.ASSET,
                'parent': cust_acc
            }
        )
        customer, _ = Customer.objects.get_or_create(
            code=cust_info['code'],
            defaults={
                'name': cust_info['name'],
                'account': a
            }
        )
        customers.append(customer)

    # 8. Create Targets for this month
    today = date.today()
    month_start = today.replace(day=1)
    month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    
    for rep in reps:
        SalesTarget.objects.get_or_create(
            sales_rep=rep,
            start_date=month_start,
            end_date=month_end,
            defaults={'target_amount': Decimal('50000')}
        )

    # 9. Create Invoices
    print("Creating invoices...")
    import time
    ts = int(time.time())
    invoice_count = 0
    for i in range(15):
        # Pick random date in last 30 days
        invoice_date = today - timedelta(days=random.randint(0, 30))
        customer = random.choice(customers)
        rep = random.choice(reps)
        
        # Create Invoice
        invoice = SalesInvoice.objects.create(
            number=f"T{ts}{i:03d}",
            date=invoice_date,
            due_date=invoice_date + timedelta(days=30),
            customer=customer,
            sales_rep=rep,
            status=SalesInvoice.Status.POSTED,
            subtotal=0,
            total=0,
            created_by=user
        )
        
        # Add 1-3 lines
        total_invoice = Decimal('0')
        subtotal_invoice = Decimal('0')
        
        for _ in range(random.randint(1, 3)):
            item, base_price = random.choice(items)
            qty = Decimal(random.randint(1, 5))
            price = base_price * Decimal(random.uniform(0.9, 1.1))
            line_subtotal = price * qty
            line_total = line_subtotal * Decimal('1.14') # Including 14% tax roughly
            
            SalesInvoiceLine.objects.create(
                invoice=invoice,
                item=item,
                warehouse=wh,
                quantity=qty,
                unit_price=price,
                total=line_total,
                revenue_account=sales_acc,
                cost_of_goods_account=cogs_acc
            )
            subtotal_invoice += line_subtotal
            total_invoice += line_total
        
        invoice.subtotal = subtotal_invoice
        invoice.tax_amount = total_invoice - subtotal_invoice
        invoice.total = total_invoice
        invoice.save()
        invoice_count += 1

    print(f"Seeding completed! Created {invoice_count} invoices.")

if __name__ == "__main__":
    seed_data()
