from django.core.management.base import BaseCommand
from apps.core.models import Account, AccountType, TaxType

DEFAULT_ACCOUNTS = [
    # (code, name, account_type, parent_code, is_leaf)
    # ── أصول ──
    ('1', 'الأصول', AccountType.ASSET, None, False),
      ('11', 'الأصول المتداولة', AccountType.ASSET, '1', False),
        ('111', 'النقدية والبنوك', AccountType.ASSET, '11', False),
          ('1111', 'خزائن النقدية', AccountType.ASSET, '111', False),
          ('1112', 'البنوك', AccountType.ASSET, '111', False),
        ('112', 'الذمم المدينة', AccountType.ASSET, '11', False),
          ('1121', 'العملاء', AccountType.ASSET, '112', False),   # parent for customer sub-accounts
          ('1122', 'ضريبة خصم وتحصيل - مدينة', AccountType.ASSET, '112', True),
        ('113', 'المخزون', AccountType.ASSET, '11', False),
          ('1131', 'مخزون البضاعة', AccountType.ASSET, '113', True),
        ('114', 'سلف وعهد وذمم', AccountType.ASSET, '11', False),
          ('1141', 'ذمم مناديب المبيعات', AccountType.ASSET, '114', False),  # parent for rep sub-accounts
          ('1142', 'عهد الموظفين', AccountType.ASSET, '114', False),  # parent for custody sub-accounts
        ('115', 'أوراق قبض', AccountType.ASSET, '11', False),
          ('1151', 'شيكات تحت التحصيل', AccountType.ASSET, '115', True),
      ('12', 'الأصول الثابتة', AccountType.ASSET, '1', False),
        ('121', 'الأراضي والمباني', AccountType.ASSET, '12', True),
        ('122', 'الآلات والمعدات', AccountType.ASSET, '12', True),
        ('129', 'مجمع إهلاك الأصول', AccountType.ASSET, '12', True),

    # ── خصوم ──
    ('2', 'الخصوم', AccountType.LIABILITY, None, False),
      ('21', 'الخصوم المتداولة', AccountType.LIABILITY, '2', False),
        ('211', 'الذمم الدائنة', AccountType.LIABILITY, '21', False),
          ('2111', 'الموردون', AccountType.LIABILITY, '211', False),  # parent for supplier sub-accounts
        ('212', 'الضرائب المستحقة', AccountType.LIABILITY, '21', False),
          ('2121', 'ضريبة القيمة المضافة', AccountType.LIABILITY, '212', True),
          ('2122', 'ضريبة الدخل المستحقة', AccountType.LIABILITY, '212', True),
          ('2123', 'ضريبة خصم وتحصيل - دائنة', AccountType.LIABILITY, '212', True),
        ('213', 'مصروفات مستحقة', AccountType.LIABILITY, '21', False),
          ('2131', 'عمولات مناديب مستحقة', AccountType.LIABILITY, '213', True),
          ('2132', 'شيكات مسحوبة', AccountType.LIABILITY, '213', True),

    # ── حقوق الملكية ──
    ('3', 'حقوق الملكية', AccountType.EQUITY, None, False),
      ('31', 'رأس المال', AccountType.EQUITY, '3', True),
      ('32', 'الاحتياطيات', AccountType.EQUITY, '3', True),
      ('33', 'الأرباح المرحلة', AccountType.EQUITY, '3', True),
      ('34', 'أرباح/خسائر العام', AccountType.EQUITY, '3', True),
      ('35', 'الأرصدة الافتتاحية', AccountType.EQUITY, '3', True),

    # ── إيرادات ──
    ('4', 'الإيرادات', AccountType.REVENUE, None, False),
      ('41', 'إيرادات المبيعات', AccountType.REVENUE, '4', False),
        ('411', 'مبيعات البضاعة', AccountType.REVENUE, '41', True),
        ('412', 'إيرادات الخدمات', AccountType.REVENUE, '41', True),
        ('4130', 'خصم مبيعات ممنوح', AccountType.REVENUE, '41', True),
        ('413', 'مردودات ومسموحات المبيعات', AccountType.REVENUE, '41', True),
        ('4141', 'فوائد بنكية', AccountType.REVENUE, '41', True),
      ('42', 'إيرادات أخرى', AccountType.REVENUE, '4', True),

    # ── مصروفات ──
    ('5', 'المصروفات', AccountType.EXPENSE, None, False),
      ('51', 'تكلفة البضاعة المباعة', AccountType.EXPENSE, '5', False),
        ('511', 'تكلفة المبيعات', AccountType.EXPENSE, '51', True),
        ('5161', 'عمولات بنكية', AccountType.EXPENSE, '51', True),
      ('52', 'مصروفات التشغيل', AccountType.EXPENSE, '5', False),
        ('521', 'مصروفات الرواتب', AccountType.EXPENSE, '52', True),
        ('522', 'مصروفات الإيجار', AccountType.EXPENSE, '52', True),
        ('523', 'مصروفات المرافق', AccountType.EXPENSE, '52', True),
        ('524', 'مصروفات إدارية عامة', AccountType.EXPENSE, '52', True),
        ('525', 'مصروفات عمولات مناديب', AccountType.EXPENSE, '52', True),
      ('53', 'مصروفات التمويل', AccountType.EXPENSE, '5', True),
]

class Command(BaseCommand):
    help = 'إنشاء شجرة الحسابات الافتراضية للنظام'

    def handle(self, *args, **options):
        accounts_map = {}
        for code, name, acc_type, parent_code, is_leaf in DEFAULT_ACCOUNTS:
            parent = accounts_map.get(parent_code) if parent_code else None
            acc, created = Account.objects.get_or_create(
                code=code,
                defaults={
                    'name': name, 
                    'account_type': acc_type, 
                    'parent': parent, 
                    'is_leaf': is_leaf
                }
            )
            accounts_map[code] = acc
            status = 'تم إنشاء' if created else 'موجود مسبقاً'
            self.stdout.write(f'  [{status}] {code} — {name}')
        
        self.stdout.write(self.style.SUCCESS('تم تجهيز شجرة الحسابات بنجاح.'))

        # Create Tax Types
        taxes = [
            ('ضريبة القيمة المضافة 14%', 'vat', 14.00, '2121'),
            ('ضريبة أ.ت.ص 1% (مبيعات)', 'wht', 1.00, '1122'),
            ('ضريبة أ.ت.ص 1% (مشتريات)', 'wht', 1.00, '2123'),
        ]
        for name, cat, rate, acc_code in taxes:
            acc = Account.objects.get(code=acc_code)
            TaxType.objects.get_or_create(
                name=name,
                defaults={'category': cat, 'rate': rate, 'account': acc}
            )
        self.stdout.write(self.style.SUCCESS('تم إنشاء أنواع الضرائب الافتراضية.'))

        # Create Common Sub-Accounts
        from apps.core.services import AccountService
        count = AccountService.setup_common_sub_accounts()
        if count > 0:
            self.stdout.write(self.style.SUCCESS(f'تم إضافة {count} حساب فرعي شائع.'))
