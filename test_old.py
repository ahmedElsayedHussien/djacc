import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.core.models import JournalLine, Account, JournalEntry
from django.conf import settings
from django.db.models import Sum, Q

# Dashboard logic
cash_parent_code = getattr(settings, 'CASH_PARENT_ACCOUNT', '1111')
bank_parent_code = getattr(settings, 'BANK_PARENT_ACCOUNT', '1112')
dashboard_ids = set(Account.objects.filter(
    Q(code__startswith=cash_parent_code) | Q(code__startswith=bank_parent_code),
    is_leaf=True
).values_list('id', flat=True))

dashboard_pre = JournalLine.objects.filter(
    account_id__in=dashboard_ids,
    entry__is_posted=True,
    entry__is_reversed=False
).aggregate(d=Sum('debit'), c=Sum('credit'))

dash_init = 0
for a in Account.objects.filter(id__in=dashboard_ids):
    has_open = JournalLine.objects.filter(
        account=a,
        entry__entry_type=JournalEntry.EntryType.OPENING,
        entry__is_posted=True,
        entry__is_reversed=False
    ).exists()
    if not has_open:
        dash_init += a.initial_balance if a.initial_balance_type == 'debit' else -a.initial_balance

dashboard_total = dash_init + (dashboard_pre['d'] or 0) - (dashboard_pre['c'] or 0)
print(f"Total Liquidity (Dashboard): {dashboard_total}")

# Old CF logic
from apps.treasury.models import CashBox, BankAccount

cash_accounts = set(CashBox.objects.values_list('account_id', flat=True))
bank_accounts = set(BankAccount.objects.values_list('account_id', flat=True))
old_cf_ids = cash_accounts | bank_accounts

pre = JournalLine.objects.filter(
    account_id__in=old_cf_ids,
    entry__is_posted=True,
    entry__is_reversed=False
).aggregate(d=Sum('debit'), c=Sum('credit'))

init = 0
for a in Account.objects.filter(id__in=old_cf_ids):
    has_open = JournalLine.objects.filter(
        account=a,
        entry__entry_type=JournalEntry.EntryType.OPENING,
        entry__is_posted=True,
        entry__is_reversed=False
    ).exists()
    if not has_open:
        init += a.initial_balance if a.initial_balance_type == 'debit' else -a.initial_balance

old_total = init + (pre['d'] or 0) - (pre['c'] or 0)
print(f"Old CF Total (from models): {old_total}")

# Print difference
print(f"Difference: {dashboard_total - old_total}")

# Print difference in accounts
print(f"Dashboard IDs: {dashboard_ids}")
print(f"Old CF IDs: {old_cf_ids}")
print(f"Missing IDs in Old CF: {dashboard_ids - old_cf_ids}")
