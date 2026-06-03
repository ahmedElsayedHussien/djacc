from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Sum, Q
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from decimal import Decimal

from decimal import Decimal

class AccountType(models.TextChoices):
    ASSET = 'asset', 'أصول'
    LIABILITY = 'liability', 'خصوم'
    EQUITY = 'equity', 'حقوق ملكية'
    REVENUE = 'revenue', 'إيرادات'
    EXPENSE = 'expense', 'مصروفات'

from django.utils import timezone

class ConcurrencyModel(models.Model):
    """
    Base model to handle concurrency and auditing.
    """
    created_at = models.DateTimeField(default=timezone.now, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التحديث")
    version = models.PositiveIntegerField(default=1, verbose_name="الإصدار")

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_state = self.__dict__.copy()

    @property
    def is_dirty(self):
        for field in self._meta.fields:
            if field.name in ['updated_at', 'version']:
                continue
            if getattr(self, field.attname) != self._original_state.get(field.attname):
                return True
        return False

    def save(self, *args, **kwargs):
        if self.pk and self.is_dirty:
            self.version += 1
        super().save(*args, **kwargs)
        self._original_state = self.__dict__.copy()

class Account(ConcurrencyModel):
    """
    Chart of Accounts (دليل الحسابات)
    Supports multi-level hierarchy via parent FK (self-referential).
    """
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    account_type = models.CharField(max_length=20, choices=AccountType.choices)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='children')
    is_leaf = models.BooleanField(default=True)          # Only leaf accounts accept journal lines
    currency = models.CharField(max_length=3, default='EGP')
    initial_balance = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))])
    initial_balance_type = models.CharField(max_length=10, choices=[('debit', 'مدين'), ('credit', 'دائن')], default='debit')
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        if self.parent:
            if self.pk is None:
                self.account_type = self.parent.account_type
                self.initial_balance_type = self.parent.initial_balance_type
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        if self.parent and self.pk and self.parent.pk == self.pk:
            raise ValidationError('لا يمكن أن يكون الحساب أباً لنفسه')
        if self.parent:
            if not self.code.startswith(self.parent.code):
                raise ValidationError(
                    f'كود الحساب ({self.code}) يجب أن يبدأ بكود الأب ({self.parent.code})'
                )
            if self.parent.is_leaf:
                raise ValidationError('لا يمكن إضافة حساب فرعي لحساب ورقي (leaf)')
            if self.account_type and self.parent.account_type and self.account_type != self.parent.account_type:
                raise ValidationError('نوع الحساب يجب أن يطابق نوع الحساب الأب')
        if self.is_leaf and self.pk and self.children.exists():
            raise ValidationError('لا يمكن جعل الحساب ورقي (leaf) وله حسابات فرعية')
        if self.pk:
            current = self.parent
            while current:
                if current.pk == self.pk:
                    raise ValidationError('تم اكتشاف مرجع دائري في شجرة الحسابات')
                current = current.parent

    def __str__(self):
        return f"{self.code} - {self.name}"

class FiscalYear(models.Model):
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    is_closed = models.BooleanField(default=False)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    closed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name

    def clean(self):
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValidationError("تاريخ البداية يجب أن يكون قبل تاريخ النهاية")
        
        # Check for overlaps
        overlaps = FiscalYear.objects.filter(
            models.Q(start_date__range=(self.start_date, self.end_date)) |
            models.Q(end_date__range=(self.start_date, self.end_date)) |
            models.Q(start_date__lte=self.start_date, end_date__gte=self.end_date)
        )
        if self.pk:
            overlaps = overlaps.exclude(pk=self.pk)
        
        if overlaps.exists():
            raise ValidationError("هذه الفترة تتداخل مع سنة مالية أخرى")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(start_date__lt=models.F('end_date')),
                name='fy_dates_valid'
            )
        ]

class CostCenter(models.Model):
    """
    شجرة مراكز التكلفة — هرمية مثل دليل الحسابات.
    المراكز الطرفية (is_leaf=True) فقط هي التي تُستخدم في قيود اليومية.
    """
    class CenterType(models.TextChoices):
        PRODUCTION    = 'production',    'إنتاج / تشغيل'
        SERVICE       = 'service',       'خدمات آلات ومعدات'
        MARKETING     = 'marketing',     'خدمات تسويقية'
        ADMIN         = 'admin',         'خدمات إدارية ومالية'
        CAPITAL       = 'capital',       'عمليات رأسمالية'
        OTHER         = 'other',         'أخرى'

    code        = models.CharField(max_length=20, unique=True, verbose_name="الكود")
    name        = models.CharField(max_length=200, verbose_name="الاسم")
    center_type = models.CharField(max_length=20, choices=CenterType.choices,
                                   default=CenterType.OTHER, verbose_name="نوع المركز")
    parent      = models.ForeignKey('self', null=True, blank=True,
                                    on_delete=models.PROTECT, related_name='children',
                                    verbose_name="المركز الرئيسي")
    is_leaf     = models.BooleanField(default=True,
                                      verbose_name="مركز طرفي (يقبل قيوداً)")
    description = models.TextField(blank=True, verbose_name="الوصف / الملاحظات")
    is_active   = models.BooleanField(default=True, verbose_name="نشط")

    class Meta:
        verbose_name = "مركز تكلفة"
        verbose_name_plural = "مراكز التكلفة"
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def full_path(self):
        """المسار الكامل من الجذر للمركز الحالي"""
        parts = [self.name]
        p = self.parent
        while p:
            parts.insert(0, p.name)
            p = p.parent
        return ' > '.join(parts)

    @property
    def level(self):
        lvl = 0
        p = self.parent
        while p:
            lvl += 1
            p = p.parent
        return lvl

    def clean(self):
        if self.parent:
            if self.parent.pk == self.pk:
                raise ValidationError({'parent': 'لا يمكن أن يكون المركز الرئيسي هو نفس المركز'})
            if self.parent.is_leaf:
                raise ValidationError({'parent': 'لا يمكن إضافة مركز فرعي لمركز طرفي (leaf)'})
            if self.center_type and self.parent.center_type and self.center_type != self.parent.center_type:
                raise ValidationError({'center_type': 'نوع المركز يجب أن يطابق نوع المركز الأب'})
            if self.pk:
                def _check_cycle(node, target):
                    if node is None:
                        return False
                    if node.pk == target.pk:
                        return True
                    return any(_check_cycle(c, target) for c in node.children.all())
                if _check_cycle(self.parent, self):
                    raise ValidationError({'parent': 'تسلسل هرمي دائري غير مسموح به'})

    def save(self, *args, **kwargs):
        if self.parent and self.pk is None:
            self.center_type = self.parent.center_type
        self.full_clean()
        super().save(*args, **kwargs)

class JournalEntry(models.Model):
    """
    القيد اليومي — header record.
    Lines must always balance: sum(debit) == sum(credit).
    """
    class EntryType(models.TextChoices):
        MANUAL = 'manual', 'يدوي'
        SALE = 'sale', 'مبيعات'
        PURCHASE = 'purchase', 'مشتريات'
        RECEIPT = 'receipt', 'تحصيل'
        PAYMENT = 'payment', 'سداد'
        EXPENSE = 'expense', 'مصروف'
        BANK = 'bank', 'بنك'
        CUSTODY = 'custody', 'عهدة'
        INVENTORY = 'inventory', 'مخزون'
        OPENING = 'opening', 'افتتاحي'
        CLOSING = 'closing', 'إقفال'

    number = models.CharField(max_length=50, unique=True)  # Auto-generated
    date = models.DateField()
    fiscal_year = models.ForeignKey(FiscalYear, on_delete=models.PROTECT)
    entry_type = models.CharField(max_length=20, choices=EntryType.choices)
    description = models.TextField()
    reference = models.CharField(max_length=100, blank=True)   # Source document number
    
    # Generic relation to source documents
    content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    source_document = GenericForeignKey('content_type', 'object_id')  
    
    is_posted = models.BooleanField(default=False)
    posted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='posted_entries')
    posted_at = models.DateTimeField(null=True, blank=True)
    
    is_reversed = models.BooleanField(default=False)
    reversed_by = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='reversed_entries')
    reversed_at = models.DateTimeField(null=True, blank=True)
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_entries')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='updated_entries')
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_reversal(self):
        return self.reversed_entries.exists()

    @property
    def total_debit(self):
        return self.lines.aggregate(t=models.Sum(models.F('debit') * models.F('exchange_rate')))['t'] or 0

    @property
    def total_credit(self):
        return self.lines.aggregate(t=models.Sum(models.F('credit') * models.F('exchange_rate')))['t'] or 0

    def clean(self):
        if self.date and self.date > timezone.now().date():
            raise ValidationError({'date': 'تاريخ القيد لا يمكن أن يكون في المستقبل'})
        if self.fiscal_year:
            if self.date and (self.date < self.fiscal_year.start_date or self.date > self.fiscal_year.end_date):
                raise ValidationError({'date': f'تاريخ القيد يجب أن يقع ضمن السنة المالية ({self.fiscal_year.start_date} إلى {self.fiscal_year.end_date})'})
            if self.fiscal_year.is_closed:
                raise ValidationError({'fiscal_year': 'لا يمكن إضافة قيود في سنة مالية مقفلة'})

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from .utils import clear_balance_cache
        clear_balance_cache()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        from .utils import clear_balance_cache
        clear_balance_cache()

    def __str__(self):
        return self.number

class JournalLine(models.Model):
    """
    سطر القيد — always created in pairs (debit + credit).
    Either debit > 0 OR credit > 0, never both.
    """
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='journal_lines')
    cost_center = models.ForeignKey(CostCenter, null=True, blank=True, on_delete=models.SET_NULL)
    description = models.CharField(max_length=300, blank=True)
    debit = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))])
    credit = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))])
    currency = models.CharField(max_length=3, default='EGP')
    exchange_rate = models.DecimalField(max_digits=12, decimal_places=6, default=1, validators=[MinValueValidator(Decimal('0.000001'))])

    def clean(self):
        if self.debit > 0 and self.credit > 0:
            raise ValidationError('السطر لا يمكن أن يكون مدين ودائن في نفس الوقت')
        if self.debit == 0 and self.credit == 0:
            raise ValidationError('يجب إدخال قيمة مدين أو دائن')
        if self.account and not self.account.is_leaf:
            raise ValidationError({'account': 'لا يمكن الترحيل لحساب غير ورقي (non-leaf)'})
        if self.account and not self.account.is_active:
            raise ValidationError({'account': 'الحساب غير نشط'})
        if self.cost_center:
            if not self.cost_center.is_leaf:
                raise ValidationError({'cost_center': 'مركز التكلفة يجب أن يكون طرفياً (leaf)'})
            if not self.cost_center.is_active:
                raise ValidationError({'cost_center': 'مركز التكلفة غير نشط'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        from .utils import clear_balance_cache
        clear_balance_cache()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        from .utils import clear_balance_cache
        clear_balance_cache()

    class Meta:
        ordering = ['entry', 'id']

class TaxType(models.Model):
    """أنواع الضرائب (قيمة مضافة، خصم من المنبع، دمغة)"""
    class Category(models.TextChoices):
        VAT = 'vat', 'ضريبة القيمة المضافة'
        TABLE = 'table', 'ضريبة الجدول'
        WHT = 'wht', 'ضريبة الخصم والتحصيل (تحت حساب الضريبة)'
        STAMP = 'stamp', 'ضريبة الدمغة'
        SALARY = 'salary', 'ضريبة كسب العمل'
        ESTATE = 'estate', 'ضريبة التصرفات العقارية'
        CUSTOMS = 'customs', 'ضرائب جمركية'
        INSURANCE = 'insurance', 'تأمينات اجتماعية'
        OTHER = 'other', 'أخرى'

    _category_account_types = {
        Category.VAT: ['liability'],
        Category.TABLE: ['asset'],
        Category.WHT: ['asset', 'liability'],
        Category.STAMP: ['liability', 'asset', 'expense'],
        Category.SALARY: ['liability'],
        Category.ESTATE: ['liability'],
        Category.CUSTOMS: ['expense', 'asset'],
        Category.INSURANCE: ['liability'],
        Category.OTHER: ['liability', 'expense', 'asset'],
    }

    name = models.CharField(max_length=100, verbose_name="اسم الضريبة")
    category = models.CharField(
        max_length=20, 
        choices=Category.choices, 
        default=Category.VAT,
        verbose_name="تصنيف الضريبة"
    )
    rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, verbose_name="النسبة الافتراضية (%)", validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))])
    account = models.ForeignKey(
        Account, 
        on_delete=models.PROTECT, 
        verbose_name="الحساب المحاسبي المرتبط"
    )
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    
    # حقول التحكم في ظهور الضريبة في واجهات النظام
    appear_in_invoices = models.BooleanField(default=True, verbose_name="تظهر في فواتير البيع والشراء")
    appear_in_payroll = models.BooleanField(default=False, verbose_name="تظهر في مسيرات الرواتب")

    class Meta:
        verbose_name = "نوع الضريبة"
        verbose_name_plural = "أنواع الضرائب"

    def clean(self):
        if self.rate is not None and (self.rate < 0 or self.rate > 100):
            raise ValidationError({'rate': 'نسبة الضريبة يجب أن تكون بين 0 و 100'})
        allowed_types = self._category_account_types.get(self.category, [])
        if allowed_types and self.account and self.account.account_type not in allowed_types:
            raise ValidationError({
                'account': f'نوع الحساب غير مناسب لهذه الفئة الضريبية. '
                          f'الأنواع المسموحة: {", ".join(allowed_types)}'
            })
        if self.account and not self.account.is_leaf:
            raise ValidationError({'account': 'الحساب المحاسبي للضريبة يجب أن يكون طرفياً (leaf)'})
        if self.account and not self.account.is_active:
            raise ValidationError({'account': 'الحساب المحاسبي للضريبة غير نشط'})

    def __str__(self):
        return f"{self.name} ({self.rate}%)"

class AuditLog(models.Model):
    """سجل مراجعة العمليات"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=50) # Create, Update, Post, Cancel
    timestamp = models.DateTimeField(auto_now_add=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField(db_index=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    changes = models.JSONField(null=True, blank=True) # To store old/new values
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user} - {self.action} - {self.content_object} at {self.timestamp}"


class SystemNotification(models.Model):
    """إشعارات النظام للمحاسبين والإدارة"""
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='system_notifications', verbose_name="المستلم")
    title = models.CharField(max_length=200, verbose_name="العنوان")
    message = models.TextField(verbose_name="الرسالة")
    url = models.CharField(max_length=500, blank=True, null=True, verbose_name="رابط الإجراء")
    is_read = models.BooleanField(default=False, verbose_name="مقروء")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإشعار")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "إشعار النظام"
        verbose_name_plural = "إشعارات النظام"

    def __str__(self):
        return f"{self.recipient.username} - {self.title} - {self.is_read}"

    @classmethod
    def notify_accountants(cls, title, message, url=None):
        # Find all accountants/admins:
        # 1. Superusers
        # 2. Staff members
        # 3. Users in groups containing 'محاسب' or 'حسابات' or 'admin' or 'manager'
        # 4. Users with view_journalentry permission
        User = get_user_model()
        accountants = User.objects.filter(
            Q(is_superuser=True) |
            Q(is_staff=True) |
            Q(groups__name__icontains='محاسب') |
            Q(groups__name__icontains='حسابات') |
            Q(groups__name__icontains='admin') |
            Q(groups__name__icontains='manager') |
            Q(groups__name__icontains='ادمن') |
            Q(groups__name__icontains='مدير') |
            Q(user_permissions__codename='view_journalentry')
        ).distinct()
        
        notifications = []
        for accountant in accountants:
            notifications.append(
                cls(
                    recipient=accountant,
                    title=title,
                    message=message,
                    url=url
                )
            )
        if notifications:
            cls.objects.bulk_create(notifications)
