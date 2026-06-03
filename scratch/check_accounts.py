import os
import sys
import django

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.core.models import Account

with open('scratch/check_accounts_output.txt', 'w', encoding='utf-8') as f:
    acc = Account.objects.filter(code='35').first()
    if acc:
        acc.is_leaf = True
        acc.save()
        f.write(f"Repaired: {acc.code} - {acc.name} -> is_leaf is now True\n")
    else:
        f.write("Account 35 not found\n")
