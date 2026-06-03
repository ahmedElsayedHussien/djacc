import os
import sys
import django

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.core.models import JournalLine

print("--- JOURNALLINES FOR 1141002 ---")
for line in JournalLine.objects.filter(account__code='1141002'):
    print(f"Date: {line.entry.date} | Entry: {line.entry.number} | Posted: {line.entry.is_posted} | Debit: {line.debit} | Credit: {line.credit} | Desc: {line.description}")
