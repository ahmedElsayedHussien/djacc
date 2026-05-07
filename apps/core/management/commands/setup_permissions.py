from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

class Command(BaseCommand):
    help = 'Setup default groups and permissions for the ERP system'

    def handle(self, *args, **options):
        # Define Group configurations
        GROUPS_CONFIG = {
            'SuperAdmin': {
                'all': True
            },
            'FinanceManager': {
                'permissions': [
                    ('core', ['account', 'journalentry', 'costcenter', 'taxtype', 'cashbox']),
                    ('treasury', ['cashbox', 'bankaccount', 'banktransaction', 'bankreconciliation', 'cashtransfer']),
                    ('expenses', ['expensecategory', 'expenseclaim']),
                    ('sales', ['customerreceipt']),
                    ('purchases', ['supplierpayment']),
                    ('reports', ['reportdefinition', 'reportexecution']),
                ]
            },
            'Accountant': {
                'permissions': [
                    ('core', ['journalentry', 'account']),
                    ('treasury', ['banktransaction', 'cashtransfer']),
                    ('expenses', ['expenseclaim']),
                    ('sales', ['customerreceipt']),
                    ('purchases', ['supplierpayment']),
                ]
            },
            'SalesManager': {
                'permissions': [
                    ('sales', ['customer', 'salesinvoice', 'salesreturn', 'customerreceipt', 'quotation', 'pricelist', 'salesrepresentative', 'customersector']),
                    ('inventory', ['item', 'warehouse']),
                ]
            },
            'PurchaseManager': {
                'permissions': [
                    ('purchases', ['supplier', 'purchaseinvoice', 'purchasereturn', 'supplierpayment']),
                    ('inventory', ['item', 'warehouse']),
                ]
            },
            'InventoryManager': {
                'permissions': [
                    ('inventory', ['item', 'warehouse', 'unitofmeasure', 'stockmovement', 'itemledger', 'loadingorder', 'transfer']),
                ]
            },
            'HRManager': {
                'permissions': [
                    ('hr', ['employee', 'department', 'position', 'payrollperiod', 'salaryslip', 'leaverequest', 'employeeloan', 'eossettlement', 'attendance', 'holiday', 'contract']),
                ]
            }
        }

        for group_name, config in GROUPS_CONFIG.items():
            group, created = Group.objects.get_or_create(name=group_name)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created group: {group_name}'))
            else:
                self.stdout.write(f'Updating group: {group_name}')

            if config.get('all'):
                permissions = Permission.objects.all()
                group.permissions.set(permissions)
                self.stdout.write(self.style.SUCCESS(f'Assigned all permissions to {group_name}'))
                continue

            group_permissions = []
            for app_label, models in config.get('permissions', []):
                for model_name in models:
                    try:
                        content_type = ContentType.objects.get(app_label=app_label, model=model_name.lower())
                        perms = Permission.objects.filter(content_type=content_type)
                        group_permissions.extend(perms)
                    except ContentType.DoesNotExist:
                        self.stdout.write(self.style.WARNING(f'ContentType not found for {app_label}.{model_name}'))

            group.permissions.set(group_permissions)
            self.stdout.write(self.style.SUCCESS(f'Assigned {len(group_permissions)} permissions to {group_name}'))

        self.stdout.write(self.style.SUCCESS('Permissions setup completed successfully.'))
