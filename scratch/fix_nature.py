import django
import os
import sys

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
sys.path.append(os.getcwd())
django.setup()

from apps.core.models import Account, AccountType
from django.db import transaction

@transaction.atomic
def fix_accounts_nature():
    updated = 0
    accounts = Account.objects.all()
    
    # Exceptions (Contra Accounts)
    contra_credit = ['129', '1132']  # مجمع الإهلاك ومردودات المشتريات
    # Note: 1132 اعتمادات مستندية is normally a debit. Sometimes purchase returns is here, but wait... 
    # Let's check apps/core/services.py to see purchase returns.
    contra_debit = ['413', '414', '36'] # مردودات وخصم المبيعات، والمسحوبات الشخصية

    for a in accounts:
        # Default rules
        expected = 'debit' if a.account_type in [AccountType.ASSET, AccountType.EXPENSE] else 'credit'
        
        # Override for contra accounts
        if any(a.code.startswith(c) for c in contra_credit):
            expected = 'credit'
        elif any(a.code.startswith(c) for c in contra_debit):
            expected = 'debit'
            
        if a.initial_balance_type != expected:
            a.initial_balance_type = expected
            a.save(update_fields=['initial_balance_type'])
            updated += 1
            print(f"Fixed account {a.code} - {a.name} to {expected}")
            
    print(f'Total fixed: {updated} accounts')

if __name__ == '__main__':
    fix_accounts_nature()
