import django
import os
import sys

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
sys.path.append(os.getcwd())
django.setup()

from apps.core.models import Account, AccountType

def fix_and_expand_coa():
    print("Starting COA Updates...")
    
    # 1. Fix 521 (Salaries Expense) Hierarchy
    salaries_parent = Account.objects.filter(code='521').first()
    if salaries_parent:
        salaries_parent.is_leaf = False
        salaries_parent.save()
        print("Updated 521 to non-leaf.")
        
        # Add Basic Salaries
        Account.objects.get_or_create(
            code='5210',
            defaults={
                'name': 'الرواتب والأجور الأساسية',
                'account_type': AccountType.EXPENSE,
                'parent': salaries_parent,
                'is_leaf': True
            }
        )
        
        # Add Employer Insurance Expense
        Account.objects.get_or_create(
            code='5214',
            defaults={
                'name': 'حصة المنشأة في التأمينات الاجتماعية',
                'account_type': AccountType.EXPENSE,
                'parent': salaries_parent,
                'is_leaf': True
            }
        )
        
        # Add EOS Expense
        Account.objects.get_or_create(
            code='5215',
            defaults={
                'name': 'مصروف تعويضات ومكافأة نهاية الخدمة',
                'account_type': AccountType.EXPENSE,
                'parent': salaries_parent,
                'is_leaf': True
            }
        )
        print("Added Salary sub-accounts.")

    # 2. Update Social Insurance Liability
    ins_liab = Account.objects.filter(code='2124').first()
    if ins_liab:
        ins_liab.name = 'الهيئة القومية للتأمينات الاجتماعية'
        ins_liab.initial_balance_type = 'credit'
        ins_liab.save()
        print("Updated 2124 to Authority account.")

    # 3. Add Cash in Transit
    cash_parent = Account.objects.filter(code='111').first()
    if cash_parent:
        Account.objects.get_or_create(
            code='1113',
            defaults={
                'name': 'نقدية بالطريق',
                'account_type': AccountType.ASSET,
                'parent': cash_parent,
                'is_leaf': True
            }
        )
        print("Added Cash in Transit (1113).")

    # 4. Add Purchase Returns
    inv_parent = Account.objects.filter(code='113').first()
    if inv_parent:
        Account.objects.get_or_create(
            code='1132',
            defaults={
                'name': 'مردودات المشتريات',
                'account_type': AccountType.ASSET,
                'parent': inv_parent,
                'is_leaf': True,
                'initial_balance_type': 'credit' # Contra-asset
            }
        )
        print("Added Purchase Returns (1132).")

    # 5. Global hierarchy check: If an account has children, it MUST NOT be is_leaf
    all_parents = Account.objects.filter(children__isnull=False).distinct()
    updated_count = 0
    for p in all_parents:
        if p.is_leaf:
            p.is_leaf = False
            p.save()
            updated_count += 1
            print(f"Fixed hierarchy for {p.code} - {p.name}")
    
    print(f"Finished updates. Fixed {updated_count} hierarchy issues.")

if __name__ == "__main__":
    fix_and_expand_coa()
