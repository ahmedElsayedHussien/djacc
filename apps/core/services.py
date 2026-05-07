from datetime import date
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from .models import JournalEntry, JournalLine, FiscalYear, AuditLog
from django.utils import timezone

class JournalService:
    """
    Central service for creating journal entries.
    All apps must use this service — never create JournalEntry directly.
    Wraps everything in atomic transactions.
    """

    @staticmethod
    @transaction.atomic
    def create_entry(
        date_val: date,
        entry_type: str,
        description: str,
        lines: list[dict],
        source_document=None,
        reference: str = '',
        created_by=None,
    ) -> JournalEntry:
        from decimal import Decimal
        # 1. Validate balance before creating anything
        total_debit = sum(Decimal(str(l.get('debit', 0))) for l in lines)
        total_credit = sum(Decimal(str(l.get('credit', 0))) for l in lines)
        if total_debit != total_credit:
            raise ValueError(f'القيد غير متوازن: مدين={total_debit}, دائن={total_credit}')

        fiscal_year = FiscalYear.objects.get(start_date__lte=date_val, end_date__gte=date_val, is_closed=False)
        
        entry = JournalEntry.objects.create(
            number=JournalService._generate_number(entry_type),
            date=date_val,
            fiscal_year=fiscal_year,
            entry_type=entry_type,
            description=description,
            reference=reference,
            created_by=created_by,
        )
        
        if source_document:
            entry.content_type = ContentType.objects.get_for_model(source_document)
            entry.object_id = source_document.pk
            entry.save()

        for line_data in lines:
            JournalLine.objects.create(entry=entry, **line_data)

        entry.is_posted = True
        entry.posted_by = created_by
        entry.posted_at = timezone.now()
        entry.save()
        
        from .services import AuditService
        AuditService.log(created_by, 'Create & Post', entry, f'إنشاء وترحيل قيد آلي رقم {entry.number}')
        
        return entry

    @staticmethod
    @transaction.atomic
    def reverse_entry(entry: JournalEntry, date_val: date, created_by) -> JournalEntry:
        reversal_lines = []
        for line in entry.lines.all():
            reversal_lines.append({
                'account': line.account,
                'debit': line.credit,    # Swap debit/credit
                'credit': line.debit,
                'description': f'عكس قيد: {line.description}',
            })
        
        new_entry = JournalService.create_entry(
            date_val=date_val,
            entry_type=entry.entry_type,
            description=f'عكس قيد رقم {entry.number}',
            lines=reversal_lines,
            created_by=created_by,
        )
        
        entry.is_reversed = True
        entry.reversed_by = new_entry
        entry.reversed_at = timezone.now()
        entry.save()
        
        from .services import AuditService
        AuditService.log(created_by, 'Reverse', entry, f'عكس قيد رقم {entry.number} بواسطة القيد {new_entry.number}')
        
        return new_entry

    @staticmethod
    def _generate_number(entry_type: str) -> str:
        """
        Robust number generation with retry logic.
        """
        today_str = timezone.now().strftime('%Y%m%d')
        prefix = f"{entry_type.upper()}-{today_str}-"
        
        with transaction.atomic():
            # Use select_for_update on the latest matching entry to lock and prevent race conditions
            last_entry = JournalEntry.objects.filter(
                number__startswith=prefix
            ).select_for_update().order_by('-number').first()
            
            if last_entry:
                try:
                    last_num = int(last_entry.number.split('-')[-1])
                    next_num = last_num + 1
                except (ValueError, IndexError):
                    next_num = 1
            else:
                next_num = 1
                
            return f"{prefix}{next_num:04d}"
        
        # Fallback with timestamp if retries fail
        import time
        return f"{entry_type.upper()}-{today_str}-{int(time.time()*1000)}"

    @staticmethod
    @transaction.atomic
    def post_opening_balances(fiscal_year, created_by) -> JournalEntry:
        """يحول initial_balance لكل حساب إلى قيد افتتاحي متزن باستخدام حساب الأرصدة الافتتاحية (35)"""
        from .models import Account
        from decimal import Decimal

        accounts = Account.objects.filter(is_leaf=True, initial_balance__gt=0)
        if not accounts.exists():
            return None
            
        lines = []
        total_debit = Decimal('0')
        total_credit = Decimal('0')
        
        for acc in accounts:
            if acc.initial_balance_type == 'debit':
                debit = acc.initial_balance
                credit = Decimal(0)
                total_debit += debit
            else:
                debit = Decimal(0)
                credit = acc.initial_balance
                total_credit += credit
                
            lines.append({
                'account': acc,
                'debit': debit,
                'credit': credit,
                'description': f'رصيد افتتاحي - {acc.name}'
            })
            
        # موازنة القيد باستخدام حساب الأرصدة الافتتاحية (35)
        difference = total_debit - total_credit
        if difference != 0:
            try:
                clearing_account = Account.objects.get(code='35')
            except Account.DoesNotExist:
                raise ValueError("لا يمكن الموازنة لعدم وجود حساب الأرصدة الافتتاحية (35)")
                
            if difference > 0:
                # الطرف المدين أكبر، نضيف الفرق للطرف الدائن
                lines.append({
                    'account': clearing_account,
                    'debit': Decimal(0),
                    'credit': difference,
                    'description': 'رصيد افتتاحي وسيط (للموازنة)'
                })
            else:
                # الطرف الدائن أكبر، نضيف الفرق للطرف المدين
                lines.append({
                    'account': clearing_account,
                    'debit': abs(difference),
                    'credit': Decimal(0),
                    'description': 'رصيد افتتاحي وسيط (للموازنة)'
                })

        entry = JournalService.create_entry(
            date_val=fiscal_year.start_date,
            entry_type=JournalEntry.EntryType.OPENING,
            description=f'قيد افتتاحي للسنة المالية {fiscal_year.name}',
            lines=lines,
            created_by=created_by,
        )

        AuditService.log(created_by, 'Post', fiscal_year, f'ترحيل الأرصدة الافتتاحية للسنة {fiscal_year.name}')

        return entry

    @staticmethod
    @transaction.atomic
    def close_fiscal_year(fiscal_year: FiscalYear, created_by) -> JournalEntry:
        """
        إقفال السنة المالية:
        1. تصفير حسابات الإيرادات والمصروفات.
        2. ترحيل الفرق إلى حساب أرباح/خسائر العام.
        """
        from django.conf import settings
        from .models import Account, JournalLine, AccountType
        from django.db.models import Sum
        from decimal import Decimal

        if fiscal_year.is_closed:
            raise ValueError("هذه السنة المالية مغلقة بالفعل")

        # 1. جلب كل حسابات الإيرادات والمصروفات (الورقة فقط)
        closing_accounts = Account.objects.filter(
            account_type__in=[AccountType.REVENUE, AccountType.EXPENSE],
            is_leaf=True
        )

        lines = []
        net_profit_loss = Decimal(0)

        for acc in closing_accounts:
            # حساب الرصيد الحالي لهذه السنة
            balance = JournalLine.objects.filter(
                account=acc,
                entry__fiscal_year=fiscal_year,
                entry__is_posted=True
            ).aggregate(bal=Sum('debit') - Sum('credit'))['bal'] or Decimal(0)

            if balance == 0:
                continue

            # لعكس الحساب: إذا كان مدين نجعله دائن والعكس
            if balance > 0: # مدين (مصروف غالباً)
                debit = 0
                credit = balance
                net_profit_loss -= balance
            else: # دائن (إيراد غالباً)
                debit = abs(balance)
                credit = 0
                net_profit_loss += abs(balance)

            lines.append({
                'account': acc,
                'debit': debit,
                'credit': credit,
                'description': f'إقفال حساب {acc.name} لعام {fiscal_year.name}'
            })

        if not lines:
            raise ValueError("لا توجد حركات لإقفالها في هذه السنة")

        # 2. إضافة سطر صافي الربح/الخسارة
        retained_acc_code = getattr(settings, 'RETAINED_EARNINGS_ACCOUNT', '34')
        try:
            profit_loss_acc = Account.objects.get(code=retained_acc_code)
        except Account.DoesNotExist:
            raise ValueError(f"حساب الأرباح المرحلة ({retained_acc_code}) غير موجود — تحقق من إعدادات النظام")

        if net_profit_loss > 0: # ربح (دائن)
            lines.append({
                'account': profit_loss_acc,
                'debit': 0,
                'credit': net_profit_loss,
                'description': f'صافي أرباح العام {fiscal_year.name}'
            })
        elif net_profit_loss < 0: # خسارة (مدين)
            lines.append({
                'account': profit_loss_acc,
                'debit': abs(net_profit_loss),
                'credit': 0,
                'description': f'صافي خسائر العام {fiscal_year.name}'
            })

        # 3. إنشاء قيد الإقفال
        closing_entry = JournalService.create_entry(
            date_val=fiscal_year.end_date,
            entry_type=JournalEntry.EntryType.CLOSING,
            description=f'قيد إقفال السنة المالية {fiscal_year.name}',
            lines=lines,
            created_by=created_by,
        )

        # 4. تحديث حالة السنة
        fiscal_year.is_closed = True
        fiscal_year.save()

        AuditService.log(created_by, 'Post', fiscal_year, f'إقفال السنة المالية {fiscal_year.name}')

        return closing_entry

class AccountService:
    @staticmethod
    @transaction.atomic
    def initialize_default_chart():
        """
        تنشئ شجرة الحسابات الافتراضية بالكامل (رئيسية وفرعية).
        """
        from .models import Account, AccountType, TaxType
        
        DEFAULT_ACCOUNTS = [
            # ── 1. أصول ──
            ('1', 'الأصول', AccountType.ASSET, None, False),
              ('11', 'الأصول المتداولة', AccountType.ASSET, '1', False),
                ('111', 'النقدية والبنوك', AccountType.ASSET, '11', False),
                  ('1111', 'خزائن النقدية', AccountType.ASSET, '111', True),
                  ('1112', 'البنوك', AccountType.ASSET, '111', True),
                  ('1113', 'عهد نقدية / صندوق نثرية', AccountType.ASSET, '111', True), 
                  ('1114', 'نقدية بالطريق', AccountType.ASSET, '111', True), 
                ('112', 'الذمم المدينة', AccountType.ASSET, '11', False),
                  ('1121', 'العملاء', AccountType.ASSET, '112', False),
                  ('1122', 'ضريبة خصم وتحصيل - مدينة', AccountType.ASSET, '112', True),
                ('113', 'المخزون', AccountType.ASSET, '11', False),
                  ('1131', 'مخزون البضاعة', AccountType.ASSET, '113', True),
                  ('1132', 'اعتمادات مستندية وبضاعة بالطريق', AccountType.ASSET, '113', True),
                  ('1134', 'مخازن المناديب', AccountType.ASSET, '113', False),
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
                ('129', 'مجمع إهلاك الأصول', AccountType.ASSET, '12', False),
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
                ('216', 'المخصصات المتداولة', AccountType.LIABILITY, '21', False),
                  ('2161', 'مخصص ديون مشكوك في تحصيلها', AccountType.LIABILITY, '216', True),
                  ('2162', 'مخصص إجازات مستحقة', AccountType.LIABILITY, '216', True),
                ('217', 'حسابات الشركاء', AccountType.LIABILITY, '21', False),
                  ('2171', 'جاري الشركاء / المالك', AccountType.LIABILITY, '217', True),
              ('22', 'الخصوم غير المتداولة', AccountType.LIABILITY, '2', False), 
                ('221', 'قروض وتسهيلات بنكية', AccountType.LIABILITY, '22', True), 
                ('222', 'مخصص مكافأة نهاية الخدمة', AccountType.LIABILITY, '22', True),

            # ── 3. حقوق الملكية ──
            ('3', 'حقوق الملكية', AccountType.EQUITY, None, False),
              ('31', 'رأس المال', AccountType.EQUITY, '3', True),
              ('32', 'الاحتياطيات', AccountType.EQUITY, '3', True),
              ('33', 'الأرباح المرحلة', AccountType.EQUITY, '3', True),
              ('34', 'أرباح/خسائر العام', AccountType.EQUITY, '3', True),
              ('35', 'الأرصدة الافتتاحية', AccountType.EQUITY, '3', True),
              ('36', 'المسحوبات الشخصية', AccountType.EQUITY, '3', True),

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
                ('423', 'أرباح فروق عملة', AccountType.REVENUE, '42', True),
                ('424', 'فروقات تسوية وزيادة المخزون', AccountType.REVENUE, '42', True),

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
                ('526', 'مصروف الإهلاك', AccountType.EXPENSE, '52', False), 
              ('53', 'مصروفات التمويل', AccountType.EXPENSE, '5', False),
                ('531', 'عمولات ومصاريف بنكية', AccountType.EXPENSE, '53', True), 
                ('532', 'فوائد قروض مدينة', AccountType.EXPENSE, '53', True), 
              ('54', 'مصروفات وخسائر أخرى', AccountType.EXPENSE, '5', False),
                ('541', 'خسائر فروق عملة', AccountType.EXPENSE, '54', True),
                ('542', 'عجز وتوالف المخزون', AccountType.EXPENSE, '54', True),
                ('543', 'ديون معدومة', AccountType.EXPENSE, '54', True),
        ]

        created_count = 0
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
            if not created:
                # تحديث البيانات للحسابات الموجودة مسبقاً (Clean up)
                acc.name = name
                acc.parent = parent
                acc.account_type = acc_type
                acc.is_leaf = is_leaf
                acc.save()
                
            accounts_map[code] = acc
            if created:
                created_count += 1
        
        # إنشاء الضرائب الافتراضية
        taxes = [
            ('ضريبة القيمة المضافة 14%', 'vat', 14.00, '2121'),
            ('ضريبة أ.ت.ص 1% (مبيعات)', 'wht', 1.00, '1122'),
            ('ضريبة أ.ت.ص 1% (مشتريات)', 'wht', 1.00, '2123'),
        ]
        for name, cat, rate, acc_code in taxes:
            try:
                acc = Account.objects.get(code=acc_code)
                TaxType.objects.get_or_create(
                    name=name,
                    defaults={'category': cat, 'rate': rate, 'account': acc}
                )
            except Account.DoesNotExist:
                continue

        return created_count

    @staticmethod
    @transaction.atomic
    def setup_common_sub_accounts():
        """
        تضيف أشهر الحسابات الفرعية (Leaf Accounts) التي تحتاجها أغلب الشركات
        """
        from .models import Account, AccountType
        
        common_accounts = [
            ('111101', 'الخزينة الرئيسية', AccountType.ASSET, '1111'),
            ('111201', 'البنك الأهلي المصري', AccountType.ASSET, '1112'),
            ('5231', 'مصروفات كهرباء', AccountType.EXPENSE, '523'),
            ('5241', 'أدوات مكتبية ومطبوعات', AccountType.EXPENSE, '524'),
            ('5242', 'ضيافة وبوفيه', AccountType.EXPENSE, '524'),
            ('5243', 'نظافة وأدوات صحية', AccountType.EXPENSE, '524'),
            ('5244', 'مصاريف صيانة عمومية', AccountType.EXPENSE, '524'),
            # ── إيرادات متنوعة ──
            ('421', 'إيرادات أوراق مالية', AccountType.REVENUE, '42'),
            ('422', 'أرباح بيع أصول ثابتة', AccountType.REVENUE, '42'),
        ]
        
        created_count = 0
        for code, name, acc_type, parent_code in common_accounts:
            try:
                parent = Account.objects.get(code=parent_code)
                acc, created = Account.objects.get_or_create(
                    code=code,
                    defaults={
                        'name': name,
                        'account_type': acc_type,
                        'parent': parent,
                        'is_leaf': True
                    }
                )
                if created:
                    created_count += 1
            except Account.DoesNotExist:
                continue # Skip if parent not found
                
        return created_count

class AuditService:
    @staticmethod
    def log(user, action, obj, notes='', changes=None):
        """
        تسجيل عملية في سجل المراجعة
        """
        AuditLog.objects.create(
            user=user,
            action=action,
            content_type=ContentType.objects.get_for_model(obj),
            object_id=obj.pk,
            notes=notes,
            changes=changes
        )

class DocumentService:
    @staticmethod
    def generate_number(model_class, prefix: str) -> str:
        """
        Generates a unique document number using select_for_update to avoid race conditions.
        Example: generate_number(SalesInvoice, 'SINV') -> 'SINV-00001'
        """
        with transaction.atomic():
            last = model_class.objects.select_for_update().order_by('-id').first()
            next_id = (last.id + 1) if last else 1
            return f'{prefix}-{next_id:05d}'
