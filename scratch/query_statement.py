import os
import sys
import django
from datetime import date

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.reports.services import ReportService

print("--- STATEMENT FOR REP ID 2 (2026-05-01 to 2026-05-18) ---")
result = ReportService.rep_statement(2, date(2026, 5, 1), date(2026, 5, 18))
print(f"Rep: {result['rep'].name} (ID: {result['rep'].id})")
print(f"Opening Balance: {result['opening_balance']}")
print(f"Lines Count: {len(result['lines'])}")
for line in result['lines']:
    print(line)
print(f"Closing Balance: {result['closing_balance']}")
