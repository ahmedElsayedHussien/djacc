from django.db import models
from django.conf import settings

class Supplier(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    account = models.OneToOneField('core.Account', on_delete=models.PROTECT)  # Payable account
    tax_number = models.CharField(max_length=50, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    payment_terms_days = models.IntegerField(default=30)
    address = models.TextField(blank=True)

    def __str__(self):
        return f"{self.code} - {self.name}"

class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        APPROVED = 'approved', 'معتمد'
        RECEIVED = 'received', 'مستلم'
        INVOICED = 'invoiced', 'مفوتر'
        CANCELLED = 'cancelled', 'ملغي'

    number = models.CharField(max_length=50, unique=True)
    date = models.DateField()
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    expected_delivery_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return self.number

class PurchaseInvoice(models.Model):
    """فاتورة شراء من مورد"""
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        POSTED = 'posted', 'مرحّل'
        CANCELLED = 'cancelled', 'ملغي'

    number = models.CharField(max_length=50, unique=True)
    supplier_invoice_number = models.CharField(max_length=100)     # Supplier's invoice number
    date = models.DateField()
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    purchase_order = models.ForeignKey(PurchaseOrder, null=True, blank=True, on_delete=models.SET_NULL)
    subtotal = models.DecimalField(max_digits=18, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=18, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    cost_center = models.ForeignKey('core.CostCenter', null=True, blank=True, on_delete=models.SET_NULL)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return self.number

class PurchaseInvoiceLine(models.Model):
    invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey('inventory.Item', on_delete=models.PROTECT)
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT)
    unit = models.ForeignKey('inventory.UnitOfMeasure', on_delete=models.PROTECT, null=True, blank=True)
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    base_quantity = models.DecimalField(max_digits=14, decimal_places=4, default=0, help_text="الكمية بالوحدة الأساسية")
    unit_cost = models.DecimalField(max_digits=18, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_type = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_type2 = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    tax_percent2 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=18, decimal_places=2)

class SupplierPayment(models.Model):
    """سداد لمورد"""
    number = models.CharField(max_length=50, unique=True)
    date = models.DateField()
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=[('cash','نقدي'),('bank','بنك'),('cheque','شيك')])
    bank_account = models.ForeignKey('treasury.BankAccount', null=True, blank=True, on_delete=models.PROTECT)
    cash_box = models.ForeignKey('treasury.CashBox', null=True, blank=True, on_delete=models.PROTECT)
    invoices = models.ManyToManyField(PurchaseInvoice, through='PaymentAllocation')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='supplier_payments')
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return self.number

class PaymentAllocation(models.Model):
    payment = models.ForeignKey(SupplierPayment, on_delete=models.CASCADE)
    invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=18, decimal_places=2)

class PurchaseReturn(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        POSTED = 'posted', 'مرحل'
        CANCELLED = 'cancelled', 'ملغي'

    number = models.CharField(max_length=50, unique=True)
    date = models.DateField()
    invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.PROTECT, null=True, blank=True, verbose_name='الفاتورة الأصلية')
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    
    notes = models.TextField(blank=True)
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    def __str__(self):
        return self.number

class PurchaseReturnLine(models.Model):
    purchase_return = models.ForeignKey(PurchaseReturn, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey('inventory.Item', on_delete=models.PROTECT)
    unit = models.ForeignKey('inventory.UnitOfMeasure', on_delete=models.PROTECT, null=True, blank=True)
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    base_quantity = models.DecimalField(max_digits=14, decimal_places=4, default=0, help_text="الكمية بالوحدة الأساسية")
    unit_cost = models.DecimalField(max_digits=18, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_type = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_type2 = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    tax_percent2 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=18, decimal_places=2)

