from django.db import models
from django.conf import settings
from apps.core.models import ConcurrencyModel

class ExpenseCategory(models.Model):
    name = models.CharField(max_length=200, verbose_name="اسم التصنيف")
    account = models.ForeignKey('core.Account', on_delete=models.PROTECT, verbose_name="الحساب المحاسبي")

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
    date = models.DateField(verbose_name="تاريخ الصرف")
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, verbose_name="التصنيف")
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="المبلغ قبل الضريبة")
    tax_type = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT, related_name='expenses1', verbose_name="نوع الضريبة 1")
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="نسبة ضريبة 1")
    tax_type2 = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT, related_name='expenses2', verbose_name="نوع الضريبة 2")
    tax_percent2 = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="نسبة ضريبة 2")
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="إجمالي الضريبة")
    total = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="الإجمالي")
    amount = models.DecimalField(max_digits=18, decimal_places=2, help_text="المبلغ المدفوع فعلياً (الصافي)", verbose_name="المبلغ المدفوع")
    description = models.TextField(verbose_name="البيان/الوصف")
    cost_center = models.ForeignKey('core.CostCenter', null=True, blank=True, on_delete=models.PROTECT, verbose_name="مركز التكلفة")
    payment_method = models.CharField(max_length=20, choices=[('cash','نقدي'),('bank','بنك'),('custody','عهدة')], verbose_name="طريقة الدفع")
    bank_account = models.ForeignKey('treasury.BankAccount', null=True, blank=True, on_delete=models.PROTECT, verbose_name="الحساب البنكي")
    cash_box = models.ForeignKey('treasury.CashBox', null=True, blank=True, on_delete=models.PROTECT, verbose_name="الخزينة")
    custody = models.ForeignKey('Custody', null=True, blank=True, on_delete=models.PROTECT, verbose_name="العهدة المرتبطة")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, verbose_name="الحالة")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_expenses', verbose_name="أنشئ بواسطة")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='approved_expenses', verbose_name="اعتمد بواسطة")
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="قيد اليومية")
    attachment = models.FileField(upload_to='expenses/', blank=True, verbose_name="المرفقات (صورة الفاتورة)")
    settlement = models.ForeignKey('CustodySettlement', null=True, blank=True, on_delete=models.SET_NULL, related_name='expenses', verbose_name="تسوية العهدة")

    def __str__(self):
        return self.number

class Custody(ConcurrencyModel):
    """
    عهدة — Cash advance given to an employee to cover expenses.
    """
    class Status(models.TextChoices):
        OPEN = 'open', 'مفتوحة'
        PARTIALLY_SETTLED = 'partial', 'مسواة جزئياً'
        SETTLED = 'settled', 'مسواة'

    number = models.CharField(max_length=50, unique=True, verbose_name="رقم العهدة")
    date = models.DateField(verbose_name="تاريخ الصرف")
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="الموظف المستلم")
    amount = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="قيمة العهدة")
    purpose = models.TextField(verbose_name="الغرض من العهدة")
    account = models.ForeignKey('core.Account', on_delete=models.PROTECT, verbose_name="حساب ذمة الموظف")   # Employee advance account
    cash_box = models.ForeignKey('treasury.CashBox', on_delete=models.PROTECT, verbose_name="الخزينة الصادر منها")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, verbose_name="الحالة")
    settled_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="المبلغ المسوي")
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="قيد اليومية")

    def __str__(self):
        return f"{self.number} - {self.employee.username}"

class CustodySettlement(ConcurrencyModel):
    """تسوية عهدة"""
    custody = models.ForeignKey(Custody, on_delete=models.PROTECT, related_name='settlements', verbose_name="العهدة الأصلية")
    date = models.DateField(verbose_name="تاريخ التسوية")
    expenses_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="إجمالي المصاريف (فواتير)")    # Spent amount with receipts
    returned_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="المبلغ المتبقي (المرتجع)")    # Cash returned
    cash_box = models.ForeignKey('treasury.CashBox', on_delete=models.PROTECT, null=True, blank=True, verbose_name="الخزينة المودع بها")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    is_posted = models.BooleanField(default=False, verbose_name="تم الترحيل")
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="قيد اليومية")
