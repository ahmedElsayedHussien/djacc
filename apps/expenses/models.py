from datetime import date
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator
from apps.core.models import ConcurrencyModel

class ExpenseCategory(models.Model):
    name = models.CharField(max_length=200, verbose_name="اسم التصنيف")
    account = models.ForeignKey('core.Account', on_delete=models.PROTECT, verbose_name="الحساب المحاسبي")

    class Meta:
        verbose_name = "تصنيف مصروف"
        verbose_name_plural = "تصنيفات المصروفات"
        ordering = ['name']

    def __str__(self):
        return self.name

class Expense(ConcurrencyModel):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        APPROVED = 'approved', 'معتمد'
        POSTED = 'posted', 'مرحّل'
        REVERSED = 'reversed', 'معكوس'
        REJECTED = 'rejected', 'مرفوض'

    number = models.CharField(max_length=50, unique=True, verbose_name="رقم المصروف")
    date = models.DateField(db_index=True, verbose_name="تاريخ الصرف")
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, db_index=True, verbose_name="التصنيف")
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(0)], verbose_name="المبلغ قبل الضريبة")
    tax_type = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT, related_name='expenses1', verbose_name="نوع الضريبة 1")
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)], verbose_name="نسبة ضريبة 1")
    tax_type2 = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT, related_name='expenses2', verbose_name="نوع الضريبة 2")
    tax_percent2 = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)], verbose_name="نسبة ضريبة 2")
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(0)], verbose_name="إجمالي الضريبة")
    total = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(0)], verbose_name="الإجمالي")
    amount = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(0)], help_text="المبلغ المدفوع فعلياً (الصافي)", verbose_name="المبلغ المدفوع")
    description = models.TextField(verbose_name="البيان/الوصف")
    cost_center = models.ForeignKey('core.CostCenter', null=True, blank=True, on_delete=models.PROTECT, verbose_name="مركز التكلفة")
    payment_method = models.CharField(max_length=20, choices=[('cash','نقدي'),('bank','بنك'),('custody','عهدة')], verbose_name="طريقة الدفع")
    bank_account = models.ForeignKey('treasury.BankAccount', null=True, blank=True, on_delete=models.PROTECT, verbose_name="الحساب البنكي")
    cash_box = models.ForeignKey('treasury.CashBox', null=True, blank=True, on_delete=models.PROTECT, verbose_name="الخزينة")
    custody = models.ForeignKey('Custody', null=True, blank=True, on_delete=models.PROTECT, verbose_name="العهدة المرتبطة")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True, verbose_name="الحالة")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_expenses', verbose_name="أنشئ بواسطة")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='approved_expenses', verbose_name="اعتمد بواسطة")
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="قيد اليومية")
    attachment = models.FileField(
        upload_to='expenses/', 
        blank=True, 
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png'])],
        verbose_name="المرفقات (صورة الفاتورة)"
    )
    settlement = models.ForeignKey('CustodySettlement', null=True, blank=True, on_delete=models.SET_NULL, related_name='expenses', verbose_name="تسوية العهدة")

    class Meta:
        verbose_name = "مصروف"
        verbose_name_plural = "المصروفات"
        ordering = ['-date', '-id']

    def __str__(self):
        return self.number

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.date and self.date > date.today():
            raise ValidationError({'date': 'تاريخ المصروف لا يمكن أن يكون في المستقبل'})
            
        # Validation for total is removed as tax can be deductions (WHT) which decreases total.            
        if self.tax_type and self.tax_percent <= 0:
            raise ValidationError({'tax_percent': 'يجب إدخال نسبة ضريبة'})
        if not self.tax_type and (self.tax_percent > 0 or self.tax_amount > 0):
            raise ValidationError('لا يمكن إدخال ضريبة بدون تحديد نوعها')

        if self.payment_method == 'cash' and not self.cash_box_id:
            raise ValidationError({'cash_box': 'يجب تحديد الخزينة عند الدفع النقدي'})
        if self.payment_method == 'bank' and not self.bank_account_id:
            raise ValidationError({'bank_account': 'يجب تحديد الحساب البنكي'})
        if self.payment_method == 'custody' and not self.custody_id:
            raise ValidationError({'custody': 'يجب تحديد العهدة'})

        if self.pk and (self.status in [self.Status.POSTED, self.Status.APPROVED] or self.journal_entry_id):
            old = Expense.objects.filter(pk=self.pk).first()
            if old and (old.total != self.total or old.category_id != self.category_id or old.amount != self.amount):
                raise ValidationError("لا يمكن تعديل المبالغ أو التصنيف لمصروف معتمد أو مرحل")

class Custody(ConcurrencyModel):
    """
    عهدة — Cash advance given to an employee to cover expenses.
    """
    class Status(models.TextChoices):
        OPEN = 'open', 'مفتوحة'
        PARTIALLY_SETTLED = 'partial', 'مسواة جزئياً'
        SETTLED = 'settled', 'مسواة'

    number = models.CharField(max_length=50, unique=True, verbose_name="رقم العهدة")
    date = models.DateField(db_index=True, verbose_name="تاريخ الصرف")
    employee = models.ForeignKey('hr.Employee', on_delete=models.PROTECT, verbose_name="الموظف المستلم")
    amount = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))], verbose_name="قيمة العهدة")
    purpose = models.TextField(verbose_name="الغرض من العهدة")
    account = models.ForeignKey('core.Account', on_delete=models.PROTECT, verbose_name="حساب ذمة الموظف")
    cash_box = models.ForeignKey('treasury.CashBox', on_delete=models.PROTECT, verbose_name="الخزينة الصادر منها")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True, verbose_name="الحالة")
    settled_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(0)], verbose_name="المبلغ المسوي")
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="قيد اليومية")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='created_custodies', verbose_name="أنشئ بواسطة")

    class Meta:
        verbose_name = "عهدة"
        verbose_name_plural = "العهد"
        ordering = ['-date', '-id']

    def __str__(self):
        return f"{self.number} - {self.employee}"

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.date and self.date > date.today():
            raise ValidationError({'date': 'تاريخ العهدة لا يمكن أن يكون في المستقبل'})
            
        if self.account_id and (not getattr(self.account, 'is_leaf', False) or not self.account.is_active):
            raise ValidationError({'account': 'حساب العهدة يجب أن يكون فرعي (Leaf) ونشط'})

        if self.settled_amount > self.amount:
            raise ValidationError({'settled_amount': 'المبلغ المسوي لا يمكن أن يتجاوز قيمة العهدة'})
            
        if self.status == self.Status.SETTLED and self.settled_amount != self.amount:
            raise ValidationError({'status': 'العهدة المسواة بالكامل يجب أن يكون مبلغها المسوي مساوياً لقيمتها'})
            
        if self.pk and self.journal_entry_id:
            old = Custody.objects.filter(pk=self.pk).first()
            if old and (old.amount != self.amount or old.employee_id != self.employee_id):
                raise ValidationError("لا يمكن تعديل بيانات العهدة المالية بعد إنشاء القيد")

class CustodySettlement(ConcurrencyModel):
    """تسوية عهدة"""
    custody = models.ForeignKey(Custody, on_delete=models.PROTECT, related_name='settlements', verbose_name="العهدة الأصلية")
    date = models.DateField(verbose_name="تاريخ التسوية")
    expenses_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(0)], verbose_name="إجمالي المصاريف (فواتير)")    # Spent amount with receipts
    returned_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(0)], verbose_name="المبلغ المتبقي (المرتجع)")    # Cash returned
    cash_box = models.ForeignKey('treasury.CashBox', on_delete=models.PROTECT, null=True, blank=True, verbose_name="الخزينة المودع بها")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    is_posted = models.BooleanField(default=False, db_index=True, verbose_name="تم الترحيل")
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="قيد اليومية")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, verbose_name="أنشئ بواسطة")

    class Meta:
        verbose_name = "تسوية عهدة"
        verbose_name_plural = "تسويات العهد"
        ordering = ['-date', '-id']

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.date and self.date > date.today():
            raise ValidationError({'date': 'تاريخ التسوية لا يمكن أن يكون في المستقبل'})
        if self.custody_id and self.expenses_amount + self.returned_amount > self.custody.amount:
            raise ValidationError('إجمالي المصاريف + المبلغ المرتجع لا يمكن أن يتجاوز قيمة العهدة الأصلية')
