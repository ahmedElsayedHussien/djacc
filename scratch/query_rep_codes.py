import os
import sys
import django

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.sales.models import SalesRepresentative

print("--- REPS WITH CODES ---")
for r in SalesRepresentative.objects.all():
    print(f"ID: {r.id} | Name: {r.name} | Code: {r.code} | Account: {r.account.code if r.account else None}")
