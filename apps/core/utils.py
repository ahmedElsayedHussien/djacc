from decimal import Decimal
from datetime import date
from django.db.models import Sum
from .models import Account, JournalLine

def get_account_balance(account: Account, as_of_date: date = None) -> Decimal:
    """
    Returns the balance of an account as of a given date.
    For debit-normal accounts (assets, expenses): balance = debit - credit
    For credit-normal accounts (liabilities, equity, revenue): balance = credit - debit
    """
    qs = JournalLine.objects.filter(account=account, entry__is_posted=True)
    if as_of_date:
        qs = qs.filter(entry__date__lte=as_of_date)

    totals = qs.aggregate(total_debit=Sum('debit'), total_credit=Sum('credit'))
    debit = (totals['total_debit'] or Decimal('0'))
    credit = (totals['total_credit'] or Decimal('0'))

    # Add initial balance if no OPENING entry exists
    has_opening = JournalLine.objects.filter(
        account=account,
        entry__entry_type='opening',
        entry__is_posted=True
    ).exists()

    if not has_opening:
        if account.initial_balance_type == 'debit':
            debit += account.initial_balance
        else:
            credit += account.initial_balance

    if account.account_type in ['asset', 'expense']:
        return debit - credit
    else:
        return credit - debit
