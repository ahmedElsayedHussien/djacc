import os
import django
import sys
from decimal import Decimal
import time

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.expenses.models import Expense, ExpenseCategory, Custody, CustodySettlement
from apps.expenses.services import ExpenseService, CustodyService
from apps.core.models import Account, TaxType
from apps.treasury.models import CashBox
from django.contrib.auth.models import User
from django.utils import timezone

def run_test():
    print("--- Starting Expenses Workflow Test ---")
    user = User.objects.get_or_create(username='admin')[0]
    
    # 1. Setup Accounts
    exp_acc = Account.objects.get_or_create(code='5201', defaults={'name': 'General Expenses', 'account_type': 'expense'})[0]
    cash_acc = Account.objects.get_or_create(code='1111', defaults={'name': 'Main CashBox', 'account_type': 'asset'})[0]
    cash_box = CashBox.objects.get_or_create(code='CB-MAIN', defaults={'name': 'Main Office Cashbox', 'account': cash_acc, 'responsible_user': user})[0]
    
    # 2. Setup Category
    cat = ExpenseCategory.objects.get_or_create(name='Office Supplies', defaults={'account': exp_acc})[0]

    # 3. Direct Cash Expense
    print("Creating Direct Cash Expense...")
    expense = Expense.objects.create(
        number=f"EXP-TEST-{int(time.time())}",
        date=timezone.now().date(),
        category=cat,
        subtotal=Decimal('100.00'),
        total=Decimal('100.00'),
        amount=Decimal('100.00'),
        description='Bought pens and papers',
        payment_method='cash',
        cash_box=cash_box,
        created_by=user,
        status='draft'
    )
    
    # Approve and Post
    expense.status = 'approved'
    expense.save()
    
    entry = ExpenseService.post_expense(expense, user)
    print(f"SUCCESS: Direct Expense Posted. Journal: {entry.number}")
    for jline in entry.lines.all():
        print(f"  - Account: {jline.account.name} | Debit: {jline.debit} | Credit: {jline.credit}")

    # 4. Custody (Advance) Cycle
    print("--- Testing Custody Cycle ---")
    emp_advance_acc = Account.objects.get_or_create(code='1131', defaults={'name': 'Employee Advances', 'account_type': 'asset'})[0]
    custody = Custody.objects.create(
        number=f"CUST-TEST-{int(time.time())}",
        date=timezone.now().date(),
        employee=user,
        amount=Decimal('1000.00'),
        purpose='Travel expenses',
        account=emp_advance_acc,
        cash_box=cash_box
    )
    
    c_entry = CustodyService.issue_custody(custody, user)
    print(f"SUCCESS: Custody Issued. Journal: {c_entry.number}")
    
    # Use part of the custody for an expense
    print("Creating Expense from Custody...")
    exp_from_cust = Expense.objects.create(
        number=f"EXP-CUST-{int(time.time())}",
        date=timezone.now().date(),
        category=cat,
        subtotal=Decimal('300.00'),
        total=Decimal('300.00'),
        amount=Decimal('300.00'),
        description='Hotel stay',
        payment_method='custody',
        custody=custody,
        created_by=user,
        status='draft'
    )
    exp_from_cust.status = 'approved'
    exp_from_cust.save()
    
    ec_entry = ExpenseService.post_expense(exp_from_cust, user)
    print(f"SUCCESS: Custody Expense Posted. Journal: {ec_entry.number}")
    for jline in ec_entry.lines.all():
        print(f"  - Account: {jline.account.name} | Debit: {jline.debit} | Credit: {jline.credit}")

    # Settle remaining custody
    print("Settling Custody (Returning 700)...")
    settlement = CustodySettlement.objects.create(
        custody=custody,
        date=timezone.now().date(),
        returned_amount=Decimal('700.00'),
        cash_box=cash_box,
        notes='Remaining cash returned'
    )
    
    s_entry = CustodyService.settle_custody(settlement, user)
    print(f"SUCCESS: Custody Settled. Journal: {s_entry.number}")
    for jline in s_entry.lines.all():
        print(f"  - Account: {jline.account.name} | Debit: {jline.debit} | Credit: {jline.credit}")

    custody.refresh_from_db()
    print(f"Custody Status: {custody.status}, Settled Amount: {custody.settled_amount}")

    print("--- Expenses Workflow Test Completed Successfully ---")

if __name__ == "__main__":
    try:
        run_test()
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
