import os
import sys
sys.path.append(os.getcwd())
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.core.models import Account

try:
    test_acc = Account.objects.get(code='11111')
    parent_acc = Account.objects.get(code='1111')
    test_acc.parent = parent_acc
    test_acc.save()
    print("SUCCESS: Account 11111 linked to parent 1111")
except Exception as e:
    print(f"ERROR: {e}")
