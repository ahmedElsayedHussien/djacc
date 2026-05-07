import django
import os
import sys

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
sys.path.append(os.getcwd())
django.setup()

from apps.core.models import Account

def export_coa():
    accounts = Account.objects.all().order_by('code')
    output_path = 'coa_full_list.txt'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("Code | Name | Type | Balance Type\n")
        f.write("-" * 50 + "\n")
        for a in accounts:
            f.write(f"{a.code} | {a.name} | {a.account_type} | {a.initial_balance_type} | {a.is_leaf}\n")
    print(f"Exported to {output_path}")

if __name__ == "__main__":
    export_coa()
