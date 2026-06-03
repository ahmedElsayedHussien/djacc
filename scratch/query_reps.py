import os
import sys
import django

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.sales.models import SalesRepresentative
from apps.core.models import JournalLine

print("--- REPRESENTATIVES LIST ---")
for r in SalesRepresentative.objects.all():
    lines_count = JournalLine.objects.filter(account=r.account).count() if r.account else 0
    print(f"ID: {r.id} | Name: {r.name} | Account: {r.account} | Lines Count: {lines_count}")
