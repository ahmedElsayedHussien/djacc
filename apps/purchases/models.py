import logging
from datetime import date
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.core.models import ConcurrencyModel
from apps.core.utils import get_account_balance
from apps.core.services import DocumentService

logger = logging.getLogger(__name__)

class Supplier(ConcurrencyModel):
    code = models.CharField(max_length=20, unique=True, verbose_name="كود المورد")
    name = models.CharField(max_length=200, db_index=True, verbose_name="اسم المورد")
    account = models.OneToOneField('core.Account', on_delete=models.PROTECT, verbose_name="الحساب المحاسبي")
    tax_number = models.CharField(max_length=50, blank=True, verbose_name="الرقم الضريبي")
    phone = models.CharField(max_length=20, blank=True, verbose_name="الهاتف")
    email = models.EmailField(blank=True, verbose_name="البريد الإلكتروني")
    commercial_register = models.CharField(max_length=50, blank=True, verbose_name="السجل التجاري")
    payment_type = models.CharField(
        max_length=10, 
        choices=[('cash', 'نقدي'), ('credit', 'آجل')], 
        default='credit', 
        verbose_name="طريقة السداد المعتادة"
    )
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    payment_terms_days = models.IntegerField(default=30, validators=[MinValueValidator(0)], verbose_name="فترة السداد (أيام)")
    address = models.TextField(blank=True, verbose_name="العنوان")

    class Meta:
        verbose_name = "مورد"
        verbose_name_plural = "الموردون"
        ordering = ['code']

    @property
    def balance(self):
        if hasattr(self, '_cached_balance'):
            return self._cached_balance
        if self.account:
            return get_account_balance(self.account)
        return 0

    def __str__(self):
        return f"{self.code} - {self.name}"

class PurchaseOrder(ConcurrencyModel):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        APPROVED = 'approved', 'معتمد'
        RECEIVED = 'received', 'مستلم'
        INVOICED = 'invoiced', 'مفوتر'
        CANCELLED = 'cancelled', 'ملغي'

    number = models.CharField(max_length=50, unique=True, verbose_name="رقم أمر الشراء")
    date = models.DateField(db_index=True, verbose_name="التاريخ")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, db_index=True, verbose_name="المورد")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True, verbose_name="الحالة")
    expected_delivery_date = models.DateField(null=True, blank=True, verbose_name="تاريخ الاستلام المتوقع")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, verbose_name="أنشئ بواسطة")

    class Meta:
        verbose_name = "أمر شراء"
        verbose_name_plural = "أوامر الشراء"
        ordering = ['-date', '-id']

    def __str__(self):
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = DocumentService.generate_number(PurchaseOrder, 'PO')
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        if self.expected_delivery_date and self.date and self.expected_delivery_date < self.date:
            raise ValidationError({'expected_delivery_date': 'تاريخ الاستلام لا يمكن أن يسبق تاريخ الأمر'})

class PurchaseInvoice(ConcurrencyModel):
    """فاتورة شراء من مورد"""
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        POSTED = 'posted', 'مرحّل'
        CANCELLED = 'cancelled', 'ملغي'

    class PaymentType(models.TextChoices):
        CASH = 'cash', 'نقدي'
        CREDIT = 'credit', 'آجل'

    number = models.CharField(max_length=50, unique=True, verbose_name="رقم الفاتورة")
    supplier_invoice_number = models.CharField(max_length=100, blank=True, verbose_name="رقم فاتورة المورد")
    date = models.DateField(db_index=True, verbose_name="تاريخ الفاتورة")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, db_index=True, verbose_name="المورد")
    payment_type = models.CharField(max_length=10, choices=PaymentType.choices, default=PaymentType.CREDIT, verbose_name="نوع الدفع")
    payment_method = models.CharField(max_length=20, choices=[('cash','نقدي'),('bank','بنك')], default='cash', verbose_name="طريقة الدفع")
    cash_box = models.ForeignKey('treasury.CashBox', on_delete=models.PROTECT, null=True, blank=True, verbose_name="الخزينة")
    bank_account = models.ForeignKey('treasury.BankAccount', on_delete=models.PROTECT, null=True, blank=True, verbose_name="الحساب البنكي")
    purchase_order = models.ForeignKey(PurchaseOrder, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="أمر الشراء المرتبط")
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))], verbose_name="الصافي")
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))], verbose_name="إجمالي الخصم")
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))], verbose_name="إجمالي الضريبة")
    total = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))], verbose_name="الإجمالي")
    paid_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))], verbose_name="المبلغ المدفوع")
    due_date = models.DateField(verbose_name="تاريخ الاستحقاق")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True, verbose_name="الحالة")
    cost_center = models.ForeignKey('core.CostCenter', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="مركز التكلفة")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="أنشئ بواسطة")
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="قيد اليومية")

    class Meta:
        verbose_name = "فاتورة مشتريات"
        verbose_name_plural = "فواتير المشتريات"
        ordering = ['-date', '-id']

    def __str__(self):
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = DocumentService.generate_number(PurchaseOrder, 'PO')
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        if self.expected_delivery_date and self.date and self.expected_delivery_date < self.date:
            raise ValidationError({'expected_delivery_date': 'تاريخ الاستلام لا يمكن أن يسبق تاريخ الأمر'})

    def get_absolute_url(self):
        return reverse('purchases:invoice-detail', kwargs={'pk': self.pk})

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = DocumentService.generate_number(PurchaseInvoice, 'PINV')

        if not self.supplier_invoice_number:
            self.supplier_invoice_number = self.number

        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        if self.date and self.date > date.today():
            raise ValidationError({'date': 'تاريخ الفاتورة لا يمكن أن يكون في المستقبل'})
        if self.due_date and self.date and self.due_date < self.date:
            raise ValidationError({'due_date': 'تاريخ الاستحقاق يجب أن يكون بعد تاريخ الفاتورة'})
        if self.paid_amount is not None and self.total is not None and self.paid_amount > self.total:
            raise ValidationError({'paid_amount': 'المبلغ المدفوع لا يمكن أن يتجاوز إجمالي الفاتورة'})
        if self.payment_type == self.PaymentType.CREDIT:
            self.cash_box = None
            self.bank_account = None

class PurchaseInvoiceLine(ConcurrencyModel):
    invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.CASCADE, related_name='lines', db_index=True, verbose_name="الفاتورة")
    item = models.ForeignKey('inventory.Item', on_delete=models.PROTECT, db_index=True, verbose_name="الصنف")
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT, verbose_name="المخزن")
    unit = models.ForeignKey('inventory.UnitOfMeasure', on_delete=models.PROTECT, null=True, blank=True, verbose_name="الوحدة")
    quantity = models.DecimalField(max_digits=14, decimal_places=4, validators=[MinValueValidator(Decimal('0.0001'))], verbose_name="الكمية")
    base_quantity = models.DecimalField(max_digits=14, decimal_places=4, default=0, validators=[MinValueValidator(0)], help_text="الكمية بالوحدة الأساسية", verbose_name="الكمية الأساسية")
    unit_cost = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(0)], verbose_name="سعر الشراء")
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)], verbose_name="نسبة الخصم %")
    tax_type = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT, verbose_name="نوع الضريبة 1")
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)], verbose_name="نسبة ضريبة 1")
    tax_type2 = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT, related_name='+', verbose_name="نوع الضريبة 2")
    tax_percent2 = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)], verbose_name="نسبة ضريبة 2")
    total = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(0)], verbose_name="الإجمالي")

    class Meta:
        verbose_name = "صنف في فاتورة مشتريات"
        verbose_name_plural = "أصناف فواتير المشتريات"

class SupplierPayment(ConcurrencyModel):
    """سداد لمورد"""
    number = models.CharField(max_length=50, unique=True, verbose_name="رقم السند")
    date = models.DateField(db_index=True, verbose_name="تاريخ السداد")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, db_index=True, verbose_name="المورد")
    amount = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))], verbose_name="المبلغ")
    payment_method = models.CharField(max_length=20, choices=[('cash','نقدي'),('bank','بنك'),('cheque','شيك')], verbose_name="طريقة السداد")
    bank_account = models.ForeignKey('treasury.BankAccount', null=True, blank=True, on_delete=models.PROTECT, verbose_name="الحساب البنكي")
    cash_box = models.ForeignKey('treasury.CashBox', null=True, blank=True, on_delete=models.PROTECT, verbose_name="الخزينة")
    # Cheque details for outgoing cheques
    cheque_number = models.CharField(max_length=50, blank=True, verbose_name="رقم الشيك")
    cheque_due_date = models.DateField(null=True, blank=True, verbose_name="تاريخ استحقاق الشيك")
    is_cleared = models.BooleanField(default=False, verbose_name="تم الصرف الفعلي")
    cleared_at = models.DateField(null=True, blank=True, verbose_name="تاريخ الصرف الفعلي")
    invoices = models.ManyToManyField(PurchaseInvoice, through='PaymentAllocation', verbose_name="الفواتير المسددة")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='supplier_payments', verbose_name="أنشئ بواسطة")
    reference = models.CharField(max_length=200, blank=True, verbose_name="المرجع")
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="قيد اليومية")

    class Meta:
        verbose_name = "سند صرف مورد"
        verbose_name_plural = "سندات صرف الموردين"
        ordering = ['-date', '-id']

    def __str__(self):
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = DocumentService.generate_number(PurchaseOrder, 'PO')
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        if self.expected_delivery_date and self.date and self.expected_delivery_date < self.date:
            raise ValidationError({'expected_delivery_date': 'تاريخ الاستلام لا يمكن أن يسبق تاريخ الأمر'})

    def get_absolute_url(self):
        return reverse('purchases:payment-detail', kwargs={'pk': self.pk})

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = DocumentService.generate_number(SupplierPayment, 'PAY')
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        if self.payment_method == 'cash' and not self.cash_box:
            raise ValidationError({'cash_box': 'يجب تحديد الخزنة للسداد النقدي'})
        if self.payment_method in ['bank', 'cheque'] and not self.bank_account:
            raise ValidationError({'bank_account': 'يجب تحديد الحساب البنكي للسداد عبر البنك/شيك'})
        if self.payment_method == 'cheque':
            if not self.cheque_number:
                raise ValidationError({'cheque_number': 'رقم الشيك مطلوب'})
            if not self.cheque_due_date:
                raise ValidationError({'cheque_due_date': 'تاريخ استحقاق الشيك مطلوب'})
        if self.is_cleared and not self.cleared_at:
            raise ValidationError({'cleared_at': 'يجب تحديد تاريخ الصرف الفعلي'})

class PaymentAllocation(ConcurrencyModel):
    payment = models.ForeignKey(SupplierPayment, on_delete=models.CASCADE, db_index=True, verbose_name="السند")
    invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.CASCADE, db_index=True, verbose_name="الفاتورة")
    amount = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))], verbose_name="المبلغ المخصص")

    def clean(self):
        if getattr(self, 'payment', None) and getattr(self, 'invoice', None):
            if self.payment.supplier != self.invoice.supplier:
                raise ValidationError("يجب أن تكون الفاتورة والسند لنفس المورد")
            if self.amount and self.amount > self.payment.amount:
                raise ValidationError({'amount': 'المبلغ المخصص لا يمكن أن يتجاوز مبلغ السند'})

    class Meta:
        verbose_name = "توزيع سداد"
        verbose_name_plural = "توزيعات السداد"
        constraints = [
            models.UniqueConstraint(fields=['payment', 'invoice'], name='unique_payment_invoice')
        ]

class PurchaseReturn(ConcurrencyModel):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        POSTED = 'posted', 'مرحل'
        CANCELLED = 'cancelled', 'ملغي'

    number = models.CharField(max_length=50, unique=True, verbose_name="رقم المرتجع")
    date = models.DateField(db_index=True, verbose_name="تاريخ المرتجع")
    invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.PROTECT, null=True, blank=True, verbose_name='الفاتورة الأصلية')
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, db_index=True, verbose_name="المورد")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True, verbose_name="الحالة")
    
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))], verbose_name="الصافي")
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))], verbose_name="إجمالي الخصم")
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))], verbose_name="إجمالي الضريبة")
    total = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))], verbose_name="الإجمالي")
    
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    cost_center = models.ForeignKey('core.CostCenter', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="مركز التكلفة")
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="قيد اليومية")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="أنشئ بواسطة")

    payment_type = models.CharField(
        max_length=10,
        choices=[('cash', 'نقدي'), ('credit', 'آجل')],
        default='credit',
        verbose_name="نوع السداد"
    )
    cash_box = models.ForeignKey(
        'treasury.CashBox',
        on_delete=models.PROTECT,
        null=True, blank=True,
        verbose_name="الخزينة (للنقدي)"
    )

    class Meta:
        verbose_name = "مرتجع مشتريات"
        verbose_name_plural = "مرتجعات المشتريات"
        ordering = ['-date', '-id']

    def __str__(self):
        return self.number

    def get_absolute_url(self):
        return reverse('purchases:return-detail', kwargs={'pk': self.pk})

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = DocumentService.generate_number(PurchaseReturn, 'PRET')
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        if self.invoice and self.supplier and self.invoice.supplier != self.supplier:
            raise ValidationError('يجب أن تكون الفاتورة لنفس المورد')
        if self.payment_type == 'cash' and not self.cash_box:
            raise ValidationError({'cash_box': 'يرجى تحديد الخزينة للمرتجع النقدي'})
        if self.date and self.date > date.today():
            raise ValidationError({'date': 'تاريخ المرتجع لا يمكن أن يكون في المستقبل'})

    @property
    def payment_type_display(self):
        return 'نقدي' if self.payment_type == 'cash' else 'آجل'

class PurchaseReturnLine(ConcurrencyModel):
    purchase_return = models.ForeignKey(PurchaseReturn, on_delete=models.CASCADE, related_name='lines', db_index=True, verbose_name="سند المرتجع")
    item = models.ForeignKey('inventory.Item', on_delete=models.PROTECT, db_index=True, verbose_name="الصنف")
    unit = models.ForeignKey('inventory.UnitOfMeasure', on_delete=models.PROTECT, null=True, blank=True, verbose_name="الوحدة")
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT, verbose_name="المخزن")
    quantity = models.DecimalField(max_digits=14, decimal_places=4, validators=[MinValueValidator(Decimal('0.0001'))], verbose_name="الكمية")
    base_quantity = models.DecimalField(max_digits=14, decimal_places=4, default=0, validators=[MinValueValidator(0)], help_text="الكمية بالوحدة الأساسية", verbose_name="الكمية الأساسية")
    unit_cost = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(0)], verbose_name="سعر الوحدة")
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)], verbose_name="نسبة الخصم %")
    tax_type = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT, verbose_name="نوع الضريبة 1")
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)], verbose_name="نسبة ضريبة 1")
    tax_type2 = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT, related_name='+', verbose_name="نوع الضريبة 2")
    tax_percent2 = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)], verbose_name="نسبة ضريبة 2")
    total = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(0)], verbose_name="الإجمالي")

    class Meta:
        verbose_name = "صنف في مرتجع مشتريات"
        verbose_name_plural = "أصناف مرتجعات المشتريات"

