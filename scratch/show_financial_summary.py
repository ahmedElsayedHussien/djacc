import os
import django
import sys
from datetime import date
from decimal import Decimal

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.reports.services import ReportService

def show_financial_summary():
    print("--- Financial Reports Summary ---")
    today = date.today()
    start_of_year = date(today.year, 1, 1)

    # 1. Income Statement
    print("\n[ Income Statement (Current Year) ]")
    income_stmt = ReportService.income_statement(start_of_year, today)
    print(f"Total Revenue: {income_stmt['revenue']:,.2f}")
    print(f"Total Expenses: {income_stmt['expenses']:,.2f}")
    print(f"Net Income: {income_stmt['net_income']:,.2f}")

    # 2. Balance Sheet Summary
    print("\n[ Balance Sheet Summary ]")
    bs = ReportService.balance_sheet(today)
    print(f"Total Assets: {bs['total_assets']:,.2f}")
    print(f"Total Liabilities: {bs['total_liabilities']:,.2f}")
    print(f"Total Equity: {bs['total_equity']:,.2f}")
    print(f"Is Balanced? {'YES' if bs['is_balanced'] else 'NO'}")

    # 3. Trial Balance Samples
    print("\n[ Trial Balance Samples (Top 10 Leaf Accounts) ]")
    tb = ReportService.trial_balance(start_of_year, today)
    print(f"{'Account Code':<15} {'Account Name':<30} {'Closing Debit':<15} {'Closing Credit':<15}")
    print("-" * 75)
    for row in tb[:10]:
        print(f"{row['account'].code:<15} {row['account'].name:<30} {row['cl_debit']:<15,.2f} {row['cl_credit']:<15,.2f}")

    print("\n--- Summary Completed ---")

if __name__ == "__main__":
    show_financial_summary()
