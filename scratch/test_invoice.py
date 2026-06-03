import os
import django
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.append('e:\\djacc')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from apps.sales.models import SalesInvoice
from apps.sales.services import SalesService
from django.contrib.auth import get_user_model
User = get_user_model()

def test():
    user = User.objects.first()
    # Find a posted invoice
    invoice = SalesInvoice.objects.filter(status='posted').first()
    if not invoice:
        print('No posted invoice found.')
        return

    print(f'Testing concurrent reverse for invoice {invoice.number}')

    def worker():
        try:
            # Simulate the view fetching the invoice
            inv = SalesInvoice.objects.get(pk=invoice.pk)
            SalesService.reverse_invoice(inv, user)
            print('Success!')
        except Exception as e:
            print(f'Failed: {e}')

    with ThreadPoolExecutor(max_workers=5) as executor:
        for _ in range(5):
            executor.submit(worker)

if __name__ == '__main__':
    test()
