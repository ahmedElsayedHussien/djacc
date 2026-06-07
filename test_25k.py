import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.core.models import JournalLine, JournalEntry, Account
import json

lines = JournalLine.objects.filter(debit__gte=24000).values('entry__number', 'account__name', 'debit', 'credit', 'entry__entry_type', 'entry__date', 'entry__is_posted', 'account_id', 'entry_id')
res = list(lines)
for r in res:
    r['debit'] = str(r['debit'])
    r['credit'] = str(r['credit'])
    r['entry__date'] = str(r['entry__date'])

with open('e:/djacc/25k_test.json', 'w', encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=2)
