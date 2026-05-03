from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from decimal import Decimal

class AccountType(models.TextChoices):
    ASSET = 'asset', 'أصول'
    LIABILITY = 'liability', 'خصوم'
    EQUITY = 'equity', 'حقوق ملكية'
    REVENUE = 'revenue', 'إيرادات'
    EXPENSE = 'expense', 'مصروفات'

class Account(models.Model):
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
    initial_balance = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    initial_balance_type = models.CharField(max_length=10, choices=[('debit', 'مدين'), ('credit', 'دائن')], default='debit')
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

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
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} - {self.name}"

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
    is_reversed = models.BooleanField(default=False)
    reversed_by = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total_debit(self):
        return self.lines.aggregate(t=models.Sum('debit'))['t'] or 0

    @property
    def total_credit(self):
        return self.lines.aggregate(t=models.Sum('credit'))['t'] or 0

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
    debit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='EGP')
    exchange_rate = models.DecimalField(max_digits=12, decimal_places=6, default=1)

    def clean(self):
        if self.debit > 0 and self.credit > 0:
            raise ValidationError('السطر لا يمكن أن يكون مدين ودائن في نفس الوقت')
        if self.debit == 0 and self.credit == 0:
            raise ValidationError('يجب إدخال قيمة مدين أو دائن')

class TaxType(models.Model):
    """أنواع الضرائب (قيمة مضافة، خصم من المنبع، دمغة)"""
    class Category(models.TextChoices):
        VAT = 'vat', 'ضريبة القيمة المضافة'
        TABLE = 'table', 'ضريبة الجدول'
        WHT = 'wht', 'ضريبة الخصم والتحصيل (تحت حساب الضريبة)'
        STAMP = 'stamp', 'ضريبة الدمغة'
        SALARY = 'salary', 'ضريبة كسب العمل'
        INCOME = 'income', 'ضريبة الدخل (شركات/أفراد)'
        ESTATE = 'estate', 'ضريبة التصرفات العقارية'
        CUSTOMS = 'customs', 'ضرائب جمركية'
        INSURANCE = 'insurance', 'تأمينات اجتماعية'
        OTHER = 'other', 'أخرى'

    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=Category.choices)
    rate = models.DecimalField(max_digits=5, decimal_places=2, help_text="النسبة المئوية (مثال: 14.00)")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, help_text="الحساب المحاسبي المرتبط")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.rate}%)"

class AuditLog(models.Model):
    """سجل مراجعة العمليات"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=50) # Create, Update, Post, Cancel
    timestamp = models.DateTimeField(auto_now_add=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    changes = models.JSONField(null=True, blank=True) # To store old/new values
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user} - {self.action} - {self.content_object} at {self.timestamp}"
