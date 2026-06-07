import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.core.models import JournalLine, Account, JournalEntry
from django.conf import settings
from django.db.models import Sum, Q

cash_parent_code = getattr(settings, 'CASH_PARENT_ACCOUNT', '1111')
bank_parent_code = getattr(settings, 'BANK_PARENT_ACCOUNT', '1112')
ids = set(Account.objects.filter(
    Q(code__startswith=cash_parent_code) | Q(code__startswith=bank_parent_code),
    is_leaf=True
).values_list('id', flat=True))

# Total Liquidity (Dashboard logic)
pre = JournalLine.objects.filter(
    account_id__in=ids,
    entry__is_posted=True,
    entry__is_reversed=False
).aggregate(d=Sum('debit'), c=Sum('credit'))

init = 0
for a in Account.objects.filter(id__in=ids):
    has_open = JournalLine.objects.filter(
        account=a,
        entry__entry_type=JournalEntry.EntryType.OPENING,
        entry__is_posted=True,
        entry__is_reversed=False
    ).exists()
    if not has_open:
        init += a.initial_balance if a.initial_balance_type == 'debit' else -a.initial_balance

total = init + (pre['d'] or 0) - (pre['c'] or 0)
print(f"Total Liquidity (Dashboard): {total}")

# Cash Flow Statement Logic
from_date = '2026-06-01'  # Assume beginning of month
to_date = '2026-06-07'

pre_from = JournalLine.objects.filter(
    account_id__in=ids,
    entry__is_posted=True,
    entry__is_reversed=False,
    entry__date__lt=from_date
).aggregate(d=Sum('debit'), c=Sum('credit'))
cf_opening = init + (pre_from['d'] or 0) - (pre_from['c'] or 0)
print(f"CF Opening: {cf_opening}")

cash_lines = JournalLine.objects.filter(
    account_id__in=ids,
    entry__is_posted=True,
    entry__is_reversed=False,
    entry__date__range=[from_date, to_date],
).exclude(
    entry__entry_type=JournalEntry.EntryType.OPENING
).select_related('entry')

net_change = 0
for line in cash_lines:
    entry = line.entry
    is_inflow = line.debit > 0
    amount = line.debit if is_inflow else line.credit
    
    opposite_lines = entry.lines.exclude(account_id__in=ids)
    if not opposite_lines.exists():
        continue
    
    if is_inflow:
        net_change += amount
    else:
        net_change -= amount

cf_closing = cf_opening + net_change
print(f"CF Closing: {cf_closing}")
print(f"Discrepancy: {total - cf_closing}")

# Analyze what's causing discrepancy
missing_amount = 0
for line in cash_lines:
    entry = line.entry
    is_inflow = line.debit > 0
    amount = line.debit if is_inflow else line.credit
    opposite_lines = entry.lines.exclude(account_id__in=ids)
    if opposite_lines.exists():
        pass
        
