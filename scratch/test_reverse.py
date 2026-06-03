import os
import django
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.append('e:\\djacc')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.core.models import JournalEntry
from apps.core.services import JournalService
from django.contrib.auth import get_user_model
from datetime import date
User = get_user_model()

def test_concurrent_reverse():
    # Get a posted entry
    entry = JournalEntry.objects.filter(is_posted=True, is_reversed=False).first()
    if not entry:
        print('No posted, non-reversed entry found.')
        return
    
    user = User.objects.first()
    
    print(f'Attempting to concurrently reverse entry {entry.number}')
    
    def reverse_task():
        try:
            # Re-fetch to simulate separate request
            e = JournalEntry.objects.get(pk=entry.pk)
            JournalService.reverse_entry(e, date.today(), user)
            print('Success!')
        except Exception as ex:
            print(f'Failed: {ex}')

    with ThreadPoolExecutor(max_workers=5) as executor:
        for _ in range(5):
            executor.submit(reverse_task)

if __name__ == '__main__':
    test_concurrent_reverse()
