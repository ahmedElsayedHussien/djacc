from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.core.models import Account
from apps.sales.models import SalesRepresentative
from apps.inventory.models import Warehouse, ItemCategory, UnitOfMeasure, Item, ItemLedger
from apps.hr.models import Employee

class Command(BaseCommand):
    help = 'Check existing data in the system'

    def handle(self, *args, **options):
        User = get_user_model()

        self.stdout.write('=== USERS ===')
        for u in User.objects.all():
            self.stdout.write(f'  ID={u.id}, username={u.username}, is_superuser={u.is_superuser}')

        self.stdout.write('\n=== ACCOUNTS (First 15) ===')
        for a in Account.objects.all()[:15]:
            self.stdout.write(f'  ID={a.id}, code={a.code}, name={a.name}, type={a.account_type}')
        self.stdout.write(f'\nTotal accounts: {Account.objects.count()}')

        self.stdout.write('\n=== WAREHOUSES ===')
        for w in Warehouse.objects.all():
            self.stdout.write(f'  ID={w.id}, code={w.code}, name={w.name}, is_returns={w.is_returns}')
        self.stdout.write(f'Total: {Warehouse.objects.count()}')

        self.stdout.write('\n=== SALES REPS ===')
        for r in SalesRepresentative.objects.all():
            self.stdout.write(f'  ID={r.id}, name={r.name}')
        self.stdout.write(f'Total: {SalesRepresentative.objects.count()}')

        self.stdout.write('\n=== EMPLOYEES ===')
        for e in Employee.objects.all():
            self.stdout.write(f'  ID={e.id}, name={e.name}')
        self.stdout.write(f'Total: {Employee.objects.count()}')

        self.stdout.write('\n=== ITEM CATEGORIES ===')
        for c in ItemCategory.objects.all():
            self.stdout.write(f'  ID={c.id}, code={c.code}, name={c.name}')
        self.stdout.write(f'Total: {ItemCategory.objects.count()}')

        self.stdout.write('\n=== UNITS OF MEASURE ===')
        for u in UnitOfMeasure.objects.all():
            self.stdout.write(f'  ID={u.id}, code={u.code}, name={u.name}')
        self.stdout.write(f'Total: {UnitOfMeasure.objects.count()}')

        self.stdout.write('\n=== ITEMS ===')
        for i in Item.objects.all():
            self.stdout.write(f'  ID={i.id}, code={i.code}, name={i.name}')
        self.stdout.write(f'Total: {Item.objects.count()}')

        self.stdout.write('\n=== DONE ===')
