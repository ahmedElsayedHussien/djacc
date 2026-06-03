import os
import django
import sys

sys.path.append('e:\\djacc')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.core.models import JournalEntry
from apps.core.services import JournalService
from django.contrib.auth import get_user_model
User = get_user_model()

def test():
    user = User.objects.first()
    # Find a reversal entry (description starts with "عكس قيد")
    reversal_entry = JournalEntry.objects.filter(description__startswith="عكس قيد").first()
    if not reversal_entry:
        print("No reversal entry found in DB to test. Creating one...")
        # Find a normal posted entry that isn't reversed
        normal_entry = JournalEntry.objects.filter(is_posted=True, is_reversed=False).first()
        if not normal_entry:
            print("No posted entry to reverse.")
            return
        
        reversal_entry = JournalService.reverse_entry(normal_entry, normal_entry.date, user)
        print(f"Created reversal entry: {reversal_entry.number}")

    print(f"Testing blocking of reversing a reversal entry: {reversal_entry.number}")
    print(f"is_reversal property value: {reversal_entry.is_reversal}")
    
    try:
        JournalService.reverse_entry(reversal_entry, reversal_entry.date, user)
        print("CRITICAL FAILURE: Reversal of reversal entry succeeded! This shouldn't happen.")
    except ValueError as e:
        print(f"SUCCESS: Prevented reversal entry from being reversed! Error message: {e}")

if __name__ == '__main__':
    test()
