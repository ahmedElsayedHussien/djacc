from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from decimal import Decimal

class AssetCategory(models.Model):
    name = models.CharField(max_length=100, verbose_name="اسم التصنيف")
    description = models.TextField(blank=True, verbose_name="وصف التصنيف")
    
    # Default accounts for this category
    asset_account = models.ForeignKey('core.Account', on_delete=models.PROTECT, related_name='asset_categories', verbose_name="حساب الأصل")
    accumulated_depreciation_account = models.ForeignKey('core.Account', on_delete=models.PROTECT, related_name='acc_dep_categories', verbose_name="حساب مجمع الإهلاك")
    depreciation_expense_account = models.ForeignKey('core.Account', on_delete=models.PROTECT, related_name='dep_exp_categories', verbose_name="حساب مصروف الإهلاك")
    
    default_depreciation_rate = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="نسبة الإهلاك السنوية", help_text="النسبة الافتراضية لهذا النوع (مثلاً: 25% للحواسب، 10% للأثاث)", validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))])

    class Meta:
        verbose_name = "تصنيف أصول"
        verbose_name_plural = "تصنيفات الأصول"

    def clean(self):
        accounts = [self.asset_account_id, self.accumulated_depreciation_account_id, self.depreciation_expense_account_id]
        if len(set(filter(None, accounts))) != len(list(filter(None, accounts))):
            raise ValidationError('حسابات التصنيف (الأصل، مجمع الإهلاك، مصروف الإهلاك) يجب أن تكون مختلفة عن بعضها البعض')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Asset(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'نشط'
        DISPOSED = 'disposed', 'مستبعد'
        FULLY_DEPRECIATED = 'fully_depreciated', 'مهلك بالكامل'

    code = models.CharField(max_length=50, unique=True, verbose_name="كود الأصل")
    name = models.CharField(max_length=300, verbose_name="اسم الأصل")
    category = models.ForeignKey(AssetCategory, on_delete=models.PROTECT, related_name='assets', verbose_name="التصنيف")
    
    purchase_date = models.DateField(verbose_name="تاريخ الشراء")
    purchase_value = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))], verbose_name="قيمة الشراء")
    salvage_value = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="القيمة التخريدية (الخردة)", help_text="القيمة المتوقعة للأصل في نهاية عمره (كم سيساوي كخردة؟)", validators=[MinValueValidator(Decimal('0.00'))])
    
    # Depreciation parameters
    depreciation_rate = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="نسبة الإهلاك السنوية", help_text="النسبة المئوية التي يتم استقطاعها سنوياً (مثلاً: 10 للسيارات)", validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))])
    
    # Opening balances for assets
    initial_accumulated_depreciation = models.DecimalField(
        max_digits=18, decimal_places=2, default=0, 
        verbose_name="مجمع الإهلاك الافتتاحي", 
        help_text="إجمالي الإهلاك المتراكم للأصل قبل البدء في استخدام هذا النظام",
        validators=[MinValueValidator(Decimal('0.00'))]
    )

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, verbose_name="الحالة")
    
    # Location/Department Tracking
    department = models.ForeignKey('hr.Department', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="الإدارة")
    location = models.CharField(max_length=200, blank=True, verbose_name="الموقع")
    
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "أصل ثابت"
        verbose_name_plural = "الأصول الثابتة"

    def clean(self):
        if self.purchase_date and self.purchase_date > timezone.now().date():
            raise ValidationError({'purchase_date': 'تاريخ الشراء لا يمكن أن يكون في المستقبل'})
        if self.salvage_value is not None and self.purchase_value is not None and self.salvage_value >= self.purchase_value:
            raise ValidationError({'salvage_value': 'القيمة التخريدية يجب أن تكون أقل من قيمة الشراء'})
        if self.initial_accumulated_depreciation is not None and self.purchase_value is not None and self.initial_accumulated_depreciation >= self.purchase_value:
            raise ValidationError({'initial_accumulated_depreciation': 'مجمع الإهلاك الافتتاحي يجب أن يكون أقل من قيمة الشراء'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def total_depreciation(self):
        """إجمالي الإهلاك المتراكم (الافتتاحي + المسجل بالنظام)"""
        system_depreciation = self.depreciation_logs.aggregate(total=models.Sum('amount'))['total'] or Decimal('0')
        return self.initial_accumulated_depreciation + system_depreciation

    @property
    def book_value(self):
        """القيمة الدفترية الحالية (قيمة الشراء - إجمالي الإهلاك)"""
        return self.purchase_value - self.total_depreciation

class DepreciationLog(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='depreciation_logs')
    date = models.DateField(verbose_name="تاريخ الإهلاك")
    amount = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="مبلغ الإهلاك", validators=[MinValueValidator(Decimal('0.01'))])
    journal_entry = models.OneToOneField('core.JournalEntry', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="قيد اليومية")
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        verbose_name = "سجل إهلاك"
        verbose_name_plural = "سجلات الإهلاك"

    def clean(self):
        if self.date and self.date > timezone.now().date():
            raise ValidationError({'date': 'تاريخ الإهلاك لا يمكن أن يكون في المستقبل'})
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({'amount': 'مبلغ الإهلاك يجب أن يكون أكبر من صفر'})
        if self.asset_id and self.asset.status != Asset.Status.ACTIVE:
            raise ValidationError('لا يمكن تسجيل إهلاك لأصل غير نشط')

    def __str__(self):
        return f"إهلاك {self.asset.name} في {self.date}"
