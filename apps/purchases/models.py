from django.db import models
from django.conf import settings
from apps.core.models import ConcurrencyModel

class Supplier(ConcurrencyModel):
    code = models.CharField(max_length=20, unique=True, verbose_name="كود المورد")
    name = models.CharField(max_length=200, verbose_name="اسم المورد")
    account = models.OneToOneField('core.Account', on_delete=models.PROTECT, verbose_name="الحساب المحاسبي")  # Payable account
    tax_number = models.CharField(max_length=50, blank=True, verbose_name="الرقم الضريبي")
    phone = models.CharField(max_length=20, blank=True, verbose_name="الهاتف")
    email = models.EmailField(blank=True, verbose_name="البريد الإلكتروني")
    payment_terms_days = models.IntegerField(default=30, verbose_name="فترة السداد (أيام)")
    address = models.TextField(blank=True, verbose_name="العنوان")

    @property
    def balance(self):
        from apps.core.utils import get_account_balance
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
    date = models.DateField(verbose_name="التاريخ")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, verbose_name="المورد")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, verbose_name="الحالة")
    expected_delivery_date = models.DateField(null=True, blank=True, verbose_name="تاريخ الاستلام المتوقع")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    def __str__(self):
        return self.number

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
    supplier_invoice_number = models.CharField(max_length=100, verbose_name="رقم فاتورة المورد")     # Supplier's invoice number
    date = models.DateField(verbose_name="تاريخ الفاتورة")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, verbose_name="المورد")
    payment_type = models.CharField(max_length=10, choices=PaymentType.choices, default=PaymentType.CREDIT, verbose_name="نوع الدفع")
    payment_method = models.CharField(max_length=20, choices=[('cash','نقدي'),('bank','بنك')], default='cash', verbose_name="طريقة الدفع")
    cash_box = models.ForeignKey('treasury.CashBox', on_delete=models.PROTECT, null=True, blank=True, verbose_name="الخزينة")
    bank_account = models.ForeignKey('treasury.BankAccount', on_delete=models.PROTECT, null=True, blank=True, verbose_name="الحساب البنكي")
    purchase_order = models.ForeignKey(PurchaseOrder, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="أمر الشراء المرتبط")
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="الصافي")
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="إجمالي الخصم")
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="إجمالي الضريبة")
    total = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="الإجمالي")
    paid_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="المبلغ المدفوع")
    due_date = models.DateField(verbose_name="تاريخ الاستحقاق")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, verbose_name="الحالة")
    cost_center = models.ForeignKey('core.CostCenter', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="مركز التكلفة")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="أنشئ بواسطة")
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="قيد اليومية")

    def __str__(self):
        return self.number

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('purchases:invoice-detail', kwargs={'pk': self.pk})

    def save(self, *args, **kwargs):
        if not self.number:
            from apps.core.services import DocumentService
            self.number = DocumentService.generate_number(PurchaseInvoice, 'PINV')
        
        if not self.supplier_invoice_number:
            self.supplier_invoice_number = self.number

        super().save(*args, **kwargs)

class PurchaseInvoiceLine(models.Model):
    invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.CASCADE, related_name='lines', verbose_name="الفاتورة")
    item = models.ForeignKey('inventory.Item', on_delete=models.PROTECT, verbose_name="الصنف")
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT, verbose_name="المخزن")
    unit = models.ForeignKey('inventory.UnitOfMeasure', on_delete=models.PROTECT, null=True, blank=True, verbose_name="الوحدة")
    quantity = models.DecimalField(max_digits=14, decimal_places=4, verbose_name="الكمية")
    base_quantity = models.DecimalField(max_digits=14, decimal_places=4, default=0, help_text="الكمية بالوحدة الأساسية", verbose_name="الكمية الأساسية")
    unit_cost = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="سعر الشراء")
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="نسبة الخصم %")
    tax_type = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT, verbose_name="نوع الضريبة 1")
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="نسبة ضريبة 1")
    tax_type2 = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT, related_name='+', verbose_name="نوع الضريبة 2")
    tax_percent2 = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="نسبة ضريبة 2")
    total = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="الإجمالي")

class SupplierPayment(models.Model):
    """سداد لمورد"""
    number = models.CharField(max_length=50, unique=True, verbose_name="رقم السند")
    date = models.DateField(verbose_name="تاريخ السداد")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, verbose_name="المورد")
    amount = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="المبلغ")
    payment_method = models.CharField(max_length=20, choices=[('cash','نقدي'),('bank','بنك'),('cheque','شيك')], verbose_name="طريقة السداد")
    bank_account = models.ForeignKey('treasury.BankAccount', null=True, blank=True, on_delete=models.PROTECT, verbose_name="الحساب البنكي")
    cash_box = models.ForeignKey('treasury.CashBox', null=True, blank=True, on_delete=models.PROTECT, verbose_name="الخزينة")
    invoices = models.ManyToManyField(PurchaseInvoice, through='PaymentAllocation', verbose_name="الفواتير المسددة")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='supplier_payments', verbose_name="أنشئ بواسطة")
    reference = models.CharField(max_length=200, blank=True, verbose_name="المرجع")
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="قيد اليومية")

    def __str__(self):
        return self.number

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('purchases:payment-detail', kwargs={'pk': self.pk})

    def save(self, *args, **kwargs):
        if not self.number:
            from apps.core.services import DocumentService
            self.number = DocumentService.generate_number(SupplierPayment, 'PAY')
        super().save(*args, **kwargs)

class PaymentAllocation(models.Model):
    payment = models.ForeignKey(SupplierPayment, on_delete=models.CASCADE, verbose_name="السند")
    invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.CASCADE, verbose_name="الفاتورة")
    amount = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="المبلغ المخصص")

class PurchaseReturn(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        POSTED = 'posted', 'مرحل'
        CANCELLED = 'cancelled', 'ملغي'

    number = models.CharField(max_length=50, unique=True, verbose_name="رقم المرتجع")
    date = models.DateField(verbose_name="تاريخ المرتجع")
    invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.PROTECT, null=True, blank=True, verbose_name='الفاتورة الأصلية')
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, verbose_name="المورد")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, verbose_name="الحالة")
    
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="الصافي")
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="إجمالي الخصم")
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="إجمالي الضريبة")
    total = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="الإجمالي")
    
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    cost_center = models.ForeignKey('core.CostCenter', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="مركز التكلفة")
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="قيد اليومية")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="أنشئ بواسطة")

    def __str__(self):
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            from apps.core.services import DocumentService
            self.number = DocumentService.generate_number(PurchaseReturn, 'PRET')
        super().save(*args, **kwargs)

class PurchaseReturnLine(models.Model):
    purchase_return = models.ForeignKey(PurchaseReturn, on_delete=models.CASCADE, related_name='lines', verbose_name="سند المرتجع")
    item = models.ForeignKey('inventory.Item', on_delete=models.PROTECT, verbose_name="الصنف")
    unit = models.ForeignKey('inventory.UnitOfMeasure', on_delete=models.PROTECT, null=True, blank=True, verbose_name="الوحدة")
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT, verbose_name="المخزن")
    quantity = models.DecimalField(max_digits=14, decimal_places=4, verbose_name="الكمية")
    base_quantity = models.DecimalField(max_digits=14, decimal_places=4, default=0, help_text="الكمية بالوحدة الأساسية", verbose_name="الكمية الأساسية")
    unit_cost = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="سعر الوحدة")
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="نسبة الخصم %")
    tax_type = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT, verbose_name="نوع الضريبة 1")
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="نسبة ضريبة 1")
    tax_type2 = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT, related_name='+', verbose_name="نوع الضريبة 2")
    tax_percent2 = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="نسبة ضريبة 2")
    total = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="الإجمالي")

