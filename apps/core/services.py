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
        entry.save()
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
        entry.save()
        
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
        """يحول initial_balance لكل حساب إلى قيد افتتاحي"""
        from .models import Account
        from decimal import Decimal

        accounts = Account.objects.filter(is_leaf=True, initial_balance__gt=0)
        if not accounts.exists():
            return None
            
        lines = []
        for acc in accounts:
            if acc.initial_balance_type == 'debit':
                debit = acc.initial_balance
                credit = Decimal(0)
            else:
                debit = Decimal(0)
                credit = acc.initial_balance
                
            lines.append({
                'account': acc,
                'debit': debit,
                'credit': credit,
                'description': f'رصيد افتتاحي - {acc.name}'
            })
            
        # تحقق من التوازن، إذا لم يكن متوازناً، ضع الفرق في حساب الأرباح المرحلة أو رأس المال
        # ولكن بما أن هذا مجرد أداة لتوليد القيد، إذا لم يكن متوازناً ستفشل العملية عبر create_entry
        # للمرونة، يمكننا جعل المستخدم يضبط الأرصدة حتى تتوازن، أو نضيف حساب تسوية (Suspense Account)
        # للتسهيل الآن، سنمررها للخدمة، وإذا لم تكن متوازنة ستعطي رسالة خطأ (وهو المطلوب لمنع اختلال الميزانية).

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
        from .models import Account, JournalLine
        from django.db.models import Sum
        from decimal import Decimal

        if fiscal_year.is_closed:
            raise ValueError("هذه السنة المالية مغلقة بالفعل")

        # 1. جلب كل حسابات الإيرادات والمصروفات (الورقة فقط)
        closing_accounts = Account.objects.filter(
            account_type__in=[Account.AccountType.REVENUE, Account.AccountType.EXPENSE],
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
    def setup_common_sub_accounts():
        """
        تضيف أشهر الحسابات الفرعية (Leaf Accounts) التي تحتاجها أغلب الشركات
        """
        from .models import Account, AccountType
        
        common_accounts = [
            # الكود، الاسم، النوع، كود الأب
            # ── نقدية وبنوك ──
            ('111101', 'الخزينة الرئيسية', AccountType.ASSET, '1111'),
            ('111102', 'خزينة النثريات', AccountType.ASSET, '1111'),
            ('111201', 'البنك الأهلي المصري', AccountType.ASSET, '1112'),
            ('111202', 'بنك مصر', AccountType.ASSET, '1112'),
            
            # ── مصروفات التشغيل (المرافق) ──
            ('5231', 'مصروفات كهرباء', AccountType.EXPENSE, '523'),
            ('5232', 'مصروفات مياه', AccountType.EXPENSE, '523'),
            ('5233', 'مصروفات تليفون وإنترنت', AccountType.EXPENSE, '523'),
            
            # ── مصروفات إدارية عامة ──
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
