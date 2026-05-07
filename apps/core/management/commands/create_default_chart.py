from django.core.management.base import BaseCommand
from apps.core.models import Account, AccountType, TaxType

DEFAULT_ACCOUNTS = [
    # (code, name, account_type, parent_code, is_leaf)
    
    # ── 1. أصول ──
    ('1', 'الأصول', AccountType.ASSET, None, False),
      ('11', 'الأصول المتداولة', AccountType.ASSET, '1', False),
        ('111', 'النقدية والبنوك', AccountType.ASSET, '11', False),
          ('1111', 'خزائن النقدية', AccountType.ASSET, '111', True),
          ('1112', 'البنوك', AccountType.ASSET, '111', True),
          ('1113', 'عهد نقدية / صندوق نثرية', AccountType.ASSET, '111', True), 
        ('112', 'الذمم المدينة', AccountType.ASSET, '11', False),
          ('1121', 'العملاء', AccountType.ASSET, '112', False),
          ('1122', 'ضريبة خصم وتحصيل - مدينة', AccountType.ASSET, '112', True),
        ('113', 'المخزون', AccountType.ASSET, '11', False),
          ('1131', 'مخزون البضاعة', AccountType.ASSET, '113', True),
          ('1132', 'اعتمادات مستندية وبضاعة بالطريق', AccountType.ASSET, '113', True), # (إضافة جديدة)
        ('114', 'سلف وعهد وذمم', AccountType.ASSET, '11', False),
          ('1141', 'ذمم مناديب المبيعات', AccountType.ASSET, '114', False),
          ('1142', 'عهد الموظفين', AccountType.ASSET, '114', False),
          ('1143', 'سلف الموظفين', AccountType.ASSET, '114', False), 
        ('115', 'أوراق قبض', AccountType.ASSET, '11', False),
          ('1151', 'شيكات تحت التحصيل', AccountType.ASSET, '115', True),
        ('116', 'أرصدة مدينة أخرى', AccountType.ASSET, '11', False), 
          ('1161', 'مصروفات مدفوعة مقدماً', AccountType.ASSET, '116', True), 
      ('12', 'الأصول الثابتة', AccountType.ASSET, '1', False),
        ('121', 'الأراضي والمباني', AccountType.ASSET, '12', True),
        ('122', 'الآلات والمعدات', AccountType.ASSET, '12', True),
        ('129', 'مجمع إهلاك الأصول', AccountType.ASSET, '12', True),
      ('13', 'الأصول غير الملموسة', AccountType.ASSET, '1', False), 
        ('131', 'برمجيات وتطبيقات', AccountType.ASSET, '13', True), 

    # ── 2. خصوم ──
    ('2', 'الخصوم', AccountType.LIABILITY, None, False),
      ('21', 'الخصوم المتداولة', AccountType.LIABILITY, '2', False),
        ('211', 'الذمم الدائنة', AccountType.LIABILITY, '21', False),
          ('2111', 'الموردون', AccountType.LIABILITY, '211', False),
        ('212', 'الضرائب المستحقة', AccountType.LIABILITY, '21', False),
          ('2121', 'ضريبة القيمة المضافة', AccountType.LIABILITY, '212', True),
          ('2122', 'ضريبة الدخل المستحقة', AccountType.LIABILITY, '212', True),
          ('2123', 'ضريبة خصم وتحصيل - دائنة', AccountType.LIABILITY, '212', True),
        ('213', 'مصروفات مستحقة', AccountType.LIABILITY, '21', False),
          ('2131', 'عمولات مناديب مستحقة', AccountType.LIABILITY, '213', True),
          ('2132', 'رواتب وأجور مستحقة', AccountType.LIABILITY, '213', True), 
          ('2133', 'تأمينات اجتماعية مستحقة', AccountType.LIABILITY, '213', True), 
        ('214', 'أوراق دفع', AccountType.LIABILITY, '21', False), 
          ('2141', 'شيكات مسحوبة', AccountType.LIABILITY, '214', True), 
        ('215', 'أرصدة دائنة أخرى', AccountType.LIABILITY, '21', False), 
          ('2151', 'إيرادات مقدمة', AccountType.LIABILITY, '215', True), 
        ('216', 'المخصصات المتداولة', AccountType.LIABILITY, '21', False), # (إضافة جديدة)
          ('2161', 'مخصص ديون مشكوك في تحصيلها', AccountType.LIABILITY, '216', True), # (إضافة جديدة)
          ('2162', 'مخصص إجازات مستحقة', AccountType.LIABILITY, '216', True), # (إضافة جديدة)
        ('217', 'حسابات الشركاء', AccountType.LIABILITY, '21', False), # (إضافة جديدة)
          ('2171', 'جاري الشركاء / المالك', AccountType.LIABILITY, '217', True), # (إضافة جديدة)
      ('22', 'الخصوم غير المتداولة', AccountType.LIABILITY, '2', False), 
        ('221', 'قروض وتسهيلات بنكية', AccountType.LIABILITY, '22', True), 
        ('222', 'مخصص مكافأة نهاية الخدمة', AccountType.LIABILITY, '22', True), # (إضافة جديدة)

    # ── 3. حقوق الملكية ──
    ('3', 'حقوق الملكية', AccountType.EQUITY, None, False),
      ('31', 'رأس المال', AccountType.EQUITY, '3', True),
      ('32', 'الاحتياطيات', AccountType.EQUITY, '3', True),
      ('33', 'الأرباح المرحلة', AccountType.EQUITY, '3', True),
      ('34', 'أرباح/خسائر العام', AccountType.EQUITY, '3', True),
      ('35', 'الأرصدة الافتتاحية', AccountType.EQUITY, '3', True),
      ('36', 'المسحوبات الشخصية', AccountType.EQUITY, '3', True), # (إضافة جديدة - لتخفيض حقوق الملكية)

    # ── 4. إيرادات ──
    ('4', 'الإيرادات', AccountType.REVENUE, None, False),
      ('41', 'إيرادات المبيعات', AccountType.REVENUE, '4', False),
        ('411', 'مبيعات البضاعة', AccountType.REVENUE, '41', True),
        ('412', 'إيرادات الخدمات', AccountType.REVENUE, '41', True),
        ('413', 'مردودات ومسموحات المبيعات', AccountType.REVENUE, '41', True),
        ('414', 'خصم مبيعات ممنوح', AccountType.REVENUE, '41', True), 
      ('42', 'إيرادات أخرى', AccountType.REVENUE, '4', False),
        ('421', 'فوائد بنكية دائنة', AccountType.REVENUE, '42', True), 
        ('422', 'خصم مكتسب', AccountType.REVENUE, '42', True), 
        ('423', 'أرباح فروق عملة', AccountType.REVENUE, '42', True), # (إضافة جديدة)
        ('424', 'فروقات تسوية وزيادة المخزون', AccountType.REVENUE, '42', True), # (إضافة جديدة)

    # ── 5. مصروفات ──
    ('5', 'المصروفات', AccountType.EXPENSE, None, False),
      ('51', 'تكلفة البضاعة المباعة', AccountType.EXPENSE, '5', False),
        ('511', 'تكلفة المبيعات', AccountType.EXPENSE, '51', True),
      ('52', 'مصروفات التشغيل', AccountType.EXPENSE, '5', False),
        ('521', 'مصروفات الرواتب', AccountType.EXPENSE, '52', False),
          ('5210', 'الرواتب والأجور الأساسية', AccountType.EXPENSE, '521', True),
          ('5211', 'مصروف بدل السكن', AccountType.EXPENSE, '521', True),
          ('5212', 'مصروف بدل الانتقال', AccountType.EXPENSE, '521', True),
          ('5213', 'مصروف بدلات وإضافات أخرى', AccountType.EXPENSE, '521', True),
          ('5214', 'حصة المنشأة في التأمينات الاجتماعية', AccountType.EXPENSE, '521', True),
          ('5215', 'مصروف تعويضات ومكافأة نهاية الخدمة', AccountType.EXPENSE, '521', True),
        ('522', 'مصروفات الإيجار', AccountType.EXPENSE, '52', True),
        ('523', 'مصروفات المرافق', AccountType.EXPENSE, '52', True), 
        ('524', 'مصروفات إدارية عامة', AccountType.EXPENSE, '52', True), 
        ('525', 'مصروفات عمولات مناديب', AccountType.EXPENSE, '52', True),
        ('526', 'مصروف الإهلاك', AccountType.EXPENSE, '52', True), 
      ('53', 'مصروفات التمويل', AccountType.EXPENSE, '5', False),
        ('531', 'عمولات ومصاريف بنكية', AccountType.EXPENSE, '53', True), 
        ('532', 'فوائد قروض مدينة', AccountType.EXPENSE, '53', True), 
      ('54', 'مصروفات وخسائر أخرى', AccountType.EXPENSE, '5', False), # (إضافة جديدة)
        ('541', 'خسائر فروق عملة', AccountType.EXPENSE, '54', True), # (إضافة جديدة)
        ('542', 'عجز وتوالف المخزون', AccountType.EXPENSE, '54', True), # (إضافة جديدة)
        ('543', 'ديون معدومة', AccountType.EXPENSE, '54', True), # (إضافة جديدة)
]

class Command(BaseCommand):
    help = 'إنشاء شجرة الحسابات الافتراضية للنظام وفقاً للمعايير المحاسبية الاحترافية'

    def handle(self, *args, **options):
        from apps.core.services import AccountService
        
        self.stdout.write('بدء إنشاء شجرة الحسابات...')
        count = AccountService.initialize_default_chart()
        self.stdout.write(self.style.SUCCESS(f'تم إنشاء/تحديث {count} حساب رئيسي وفرعي.'))

        sub_count = AccountService.setup_common_sub_accounts()
        if sub_count > 0:
            self.stdout.write(self.style.SUCCESS(f'تم إضافة {sub_count} حساب فرعي شائع.'))
        
        self.stdout.write(self.style.SUCCESS('تم تجهيز شجرة الحسابات بنجاح وفقاً للمعايير الاحترافية.'))
