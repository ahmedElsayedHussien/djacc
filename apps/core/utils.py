from decimal import Decimal
from datetime import date
from django.db.models import Sum, Q
from threading import local
from .models import Account, JournalLine, JournalEntry

_thread_local = local()

def compute_account_balances(as_of_date=None):
    """
    Compute balances for ALL accounts in 2 SQL queries.
    Returns dict {account_id: Decimal(balance)} with correct parent roll-up.
    """
    all_accounts = Account.objects.all().values(
        'id', 'parent_id', 'account_type', 'initial_balance', 'initial_balance_type', 'is_leaf'
    )

    movements = JournalLine.objects.filter(
        entry__is_posted=True,
        entry__is_reversed=False
    )
    if as_of_date:
        movements = movements.filter(entry__date__lte=as_of_date)
    movements = movements.values('account_id').annotate(
        total_debit=Sum('debit'), total_credit=Sum('credit')
    )
    mov_map = {m['account_id']: {'d': m['total_debit'] or Decimal(0), 'c': m['total_credit'] or Decimal(0)} for m in movements}

    opening_acc_ids = set(JournalLine.objects.filter(
        entry__entry_type=JournalEntry.EntryType.OPENING,
        entry__is_posted=True,
        entry__is_reversed=False
    ).values_list('account_id', flat=True))

    leaf_bals = {}
    acc_dict = {}
    parent_map = {}

    for a in all_accounts:
        acc_dict[a['id']] = a
        pid = a['parent_id']
        if pid:
            parent_map.setdefault(pid, []).append(a['id'])

        if a['is_leaf']:
            debit = mov_map.get(a['id'], {}).get('d', Decimal(0))
            credit = mov_map.get(a['id'], {}).get('c', Decimal(0))

            if a['id'] not in opening_acc_ids:
                if a['initial_balance_type'] == 'debit':
                    debit += a['initial_balance']
                else:
                    credit += a['initial_balance']

            if a['account_type'] in ['asset', 'expense']:
                bal = debit - credit
            else:
                bal = credit - debit
            leaf_bals[a['id']] = bal

    calc_cache = {}
    def roll_up(acc_id):
        if acc_id in calc_cache:
            return calc_cache[acc_id]
        a = acc_dict.get(acc_id)
        if not a:
            return Decimal(0)
        if a['is_leaf']:
            res = leaf_bals.get(acc_id, Decimal(0))
        else:
            res = Decimal(0)
            for cid in parent_map.get(acc_id, []):
                res += roll_up(cid)
        calc_cache[acc_id] = res
        return res

    for a_id in acc_dict:
        roll_up(a_id)

    return calc_cache


def get_account_balance(account, as_of_date=None):
    """
    Returns the balance of an account as of a given date.
    Uses efficient bulk computation — cached per request/thread.
    """
    if as_of_date is None:
        cache_key = '__all_balances__'
    else:
        cache_key = f'__balances_{as_of_date.isoformat()}__'

    cache = getattr(_thread_local, cache_key, None)
    if cache is None:
        cache = compute_account_balances(as_of_date)
        setattr(_thread_local, cache_key, cache)

    return cache.get(account.pk, Decimal(0))


def clear_balance_cache():
    """Call after any journal entry post/reverse to invalidate cached balances."""
    for attr in list(vars(_thread_local)):
        if attr.startswith('__balances_') or attr == '__all_balances__':
            delattr(_thread_local, attr)
