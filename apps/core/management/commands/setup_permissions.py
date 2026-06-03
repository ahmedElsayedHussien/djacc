from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

class Command(BaseCommand):
    help = 'Setup default groups with view permissions + extra perms per department'

    def safe_write(self, msg, style_func=None):
        if style_func:
            msg = style_func(msg)
        try:
            self.stdout.write(msg)
        except UnicodeEncodeError:
            try:
                self.stdout.write(msg.encode('ascii', 'replace').decode('ascii'))
            except Exception:
                pass

    def handle(self, *args, **options):
        GROUPS_CONFIG = {
            'سوبر ادمن': {'all': True},
            'مدير حسابات': {'apps': ['core'], 'all_perms': True},
            'حسابات': {'apps': ['core'], 'extra_perms': ['view_customersector', 'view_pricelist']},
            'مدير مبيعات': {'apps': ['sales', 'core'], 'all_perms': True},
            'مبيعات': {'apps': ['sales', 'core'], 'extra_perms': ['add_salesinvoice', 'add_salesreturn', 'add_customerreceipt', 'add_loadingorder', 'view_loadingorder', 'change_loadingorder', 'view_item']},
            'مدير مخازن': {'apps': ['inventory'], 'all_perms': True},
            'مخازن': {'apps': ['inventory']},
            'مدير مشتريات': {'apps': ['purchases'], 'all_perms': True},
            'مشتريات': {'apps': ['purchases']},
            'مدير اداري': {'apps': ['hr'], 'all_perms': True},
            'اداريين': {'apps': ['hr']},
            'مدير it': {'apps': ['core'], 'all_perms': True},
            'it': {'apps': ['core']},
        }

        for group_name, config in GROUPS_CONFIG.items():
            group, created = Group.objects.get_or_create(name=group_name)
            tag = 'Created' if created else 'Updated'

            if isinstance(config, dict) and config.get('all'):
                group.permissions.set(Permission.objects.all())
                self.safe_write(f'{tag} group: {group_name} (all permissions)', self.style.SUCCESS)
                continue

            app_labels = config.get('apps', []) if isinstance(config, dict) else []
            all_perms = config.get('all_perms', False) if isinstance(config, dict) else False
            extra_codenames = config.get('extra_perms', []) if isinstance(config, dict) else []

            perm_ids = set()

            if app_labels:
                base_qs = Permission.objects.filter(content_type__app_label__in=app_labels)
                if all_perms:
                    # المدير: view + add + change + delete
                    ids = base_qs.values_list('id', flat=True)
                else:
                    # الموظف: view فقط
                    ids = base_qs.filter(codename__startswith='view_').values_list('id', flat=True)
                perm_ids.update(ids)

            if extra_codenames:
                extra_ids = Permission.objects.filter(codename__in=extra_codenames).values_list('id', flat=True)
                perm_ids.update(extra_ids)

            # Ensure core.view_account is always assigned to every group by default
            view_account_perm = Permission.objects.filter(codename='view_account', content_type__app_label='core').first()
            if view_account_perm:
                perm_ids.add(view_account_perm.id)

            group.permissions.set(perm_ids)
            total = len(perm_ids)
            self.safe_write(f'{tag} group: {group_name} ({total} permissions)', self.style.SUCCESS)

        self.safe_write('\nPermissions setup completed successfully.', self.style.SUCCESS)
