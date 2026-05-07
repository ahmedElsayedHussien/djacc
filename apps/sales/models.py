from django.db import models
from django.core.validators import MinValueValidator
from django.conf import settings

class CustomerSector(models.Model):
    """قطاع العملاء (مثلاً: قطاع التجزئة، قطاع الجملة، قطاع التصدير)"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

class Customer(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    account = models.OneToOneField('core.Account', on_delete=models.PROTECT)  # Receivable account
    sector = models.ForeignKey(CustomerSector, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="القطاع")
    tax_number = models.CharField(max_length=50, blank=True)
    credit_limit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    payment_terms_days = models.IntegerField(default=30)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    customer_type = models.CharField(max_length=10, choices=[('cash','نقدي'), ('credit','آجل')], default='credit')
    price_list = models.ForeignKey('PriceList', null=True, blank=True, on_delete=models.SET_NULL)
    is_taxable = models.BooleanField(default=True, verbose_name="خاضع للضريبة")
    default_tax1 = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.SET_NULL, related_name='+', verbose_name="الضريبة الافتراضية 1")
    default_tax2 = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.SET_NULL, related_name='+', verbose_name="الضريبة الافتراضية 2")

    def __str__(self):
        return f"{self.code} - {self.name}"

class SalesRepresentative(models.Model):
    """مندوب مبيعات"""
    employee = models.OneToOneField('hr.Employee', on_delete=models.CASCADE, related_name='sales_profile', null=True, blank=True, verbose_name="الموظف المرتبط")
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200, help_text="سيتم جلبه تلقائياً من الموظف")
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    phone = models.CharField(max_length=20, blank=True)
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT)  # مخزن المندوب
    cash_box = models.ForeignKey('treasury.CashBox', on_delete=models.PROTECT)       # خزنة المندوب
    account = models.OneToOneField(
        'core.Account',
        on_delete=models.PROTECT,
        null=True, blank=True,
        help_text='حساب ذمة المندوب — يُنشأ تلقائياً'
    )
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0) # نسبة العمولة %
    territory = models.CharField(max_length=200, blank=True)                         # المنطقة الجغرافية
    is_active = models.BooleanField(default=True)
    supervisor = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL) # المشرف

    def save(self, *args, **kwargs):
        if self.employee:
            self.name = f"{self.employee.first_name} {self.employee.last_name}"
            self.phone = self.employee.phone
            self.user = self.employee.user
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class PriceList(models.Model):
    """قائمة أسعار"""
    name = models.CharField(max_length=200)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class PriceListItem(models.Model):
    """سعر صنف في قائمة أسعار"""
    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey('inventory.Item', on_delete=models.PROTECT)
    unit_price = models.DecimalField(max_digits=18, decimal_places=2)
    min_qty = models.DecimalField(max_digits=14, decimal_places=4, default=1)

    class Meta:
        unique_together = ['price_list', 'item', 'min_qty']

    def __str__(self):
        return f"{self.price_list.name} - {self.item.name} - {self.unit_price}"

class IntermediaryCompany(models.Model):
    """شركات التحصيل الوسيطة (فوري، أمان، مندوب خارجي)"""
    name = models.CharField(max_length=200)
    account = models.OneToOneField('core.Account', on_delete=models.PROTECT) # حساب وسيط (مدين)
    commission_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class SalesInvoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        POSTED = 'posted', 'مرحل'
        CANCELLED = 'cancelled', 'ملغي'

    class PaymentType(models.TextChoices):
        CASH = 'cash', 'نقدي'
        CREDIT = 'credit', 'آجل'

    number = models.CharField(max_length=50, unique=True)
    date = models.DateField()
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    payment_type = models.CharField(max_length=10, choices=PaymentType.choices, default=PaymentType.CREDIT)
    sales_rep = models.ForeignKey(SalesRepresentative, on_delete=models.PROTECT, null=True, blank=True)
    cash_box = models.ForeignKey('treasury.CashBox', on_delete=models.PROTECT, null=True, blank=True)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    subtotal = models.DecimalField(max_digits=18, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=18, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    cost_center = models.ForeignKey('core.CostCenter', null=True, blank=True, on_delete=models.SET_NULL)
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    def __str__(self):
        return self.number

class SalesInvoiceLine(models.Model):
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey('inventory.Item', on_delete=models.PROTECT)
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT)
    unit = models.ForeignKey('inventory.UnitOfMeasure', on_delete=models.PROTECT, null=True, blank=True)
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    base_quantity = models.DecimalField(max_digits=14, decimal_places=4, default=0, help_text="الكمية بالوحدة الأساسية")
    unit_price = models.DecimalField(max_digits=18, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_type = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_type2 = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    tax_percent2 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=18, decimal_places=2)
    cost = models.DecimalField(max_digits=18, decimal_places=2, default=0, help_text="تكلفة الوحدة وقت البيع")
    revenue_account = models.ForeignKey('core.Account', on_delete=models.PROTECT)
    cost_of_goods_account = models.ForeignKey('core.Account', on_delete=models.PROTECT, related_name='+')

class CustomerReceipt(models.Model):
    """تحصيل من عميل"""
    number = models.CharField(max_length=50, unique=True)
    date = models.DateField()
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=[
        ('cash','نقدي'),
        ('bank','تحويل بنكي'),
        ('cheque','شيك'),
        ('intermediary','شركة وسيطة (فوري/أمان)')
    ])
    bank_account = models.ForeignKey('treasury.BankAccount', null=True, blank=True, on_delete=models.PROTECT)
    cash_box = models.ForeignKey('treasury.CashBox', null=True, blank=True, on_delete=models.PROTECT)
    intermediary_company = models.ForeignKey(IntermediaryCompany, null=True, blank=True, on_delete=models.PROTECT)
    
    # Cheque details
    cheque_number = models.CharField(max_length=50, blank=True)
    cheque_due_date = models.DateField(null=True, blank=True)
    
    reference = models.CharField(max_length=100, blank=True)
    is_collected = models.BooleanField(default=False)
    collected_at = models.DateField(null=True, blank=True)
    invoices = models.ManyToManyField(SalesInvoice, through='ReceiptAllocation')
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return self.number

class ReceiptAllocation(models.Model):
    receipt = models.ForeignKey(CustomerReceipt, on_delete=models.CASCADE)
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=18, decimal_places=2)

class SalesTarget(models.Model):
    """Target for a sales representative within a period"""
    sales_rep = models.ForeignKey('SalesRepresentative', on_delete=models.PROTECT, related_name='targets')
    target_amount = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(0)])
    start_date = models.DateField()
    end_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date']
        unique_together = ('sales_rep', 'start_date', 'end_date')

    def __str__(self):
        return f"{self.sales_rep.name} - {self.target_amount} ({self.start_date} to {self.end_date})"

class SalesReturn(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        POSTED = 'posted', 'مرحل'
        CANCELLED = 'cancelled', 'ملغي'

    number = models.CharField(max_length=50, unique=True)
    date = models.DateField()
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.PROTECT, null=True, blank=True, verbose_name='الفاتورة الأصلية')
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    sales_rep = models.ForeignKey(SalesRepresentative, on_delete=models.PROTECT, null=True, blank=True)
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

class SalesReturnLine(models.Model):
    sales_return = models.ForeignKey(SalesReturn, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey('inventory.Item', on_delete=models.PROTECT)
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    base_quantity = models.DecimalField(max_digits=14, decimal_places=4, default=0, help_text="الكمية بالوحدة الأساسية")
    unit_price = models.DecimalField(max_digits=18, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_type = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_type2 = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    tax_percent2 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=18, decimal_places=2)
    cost = models.DecimalField(max_digits=18, decimal_places=2, default=0, help_text="تكلفة الوحدة وقت المرتجع")
    
    return_account = models.ForeignKey('core.Account', on_delete=models.PROTECT) # حساب المردودات
    cogs_account = models.ForeignKey('core.Account', on_delete=models.PROTECT, related_name='+')


class RepDailySettlement(models.Model):
    """
    تسوية يومية للمندوب — يسلم فيها:
    - النقدية المحصلة من المبيعات
    - قائمة الفواتير اللي باعها
    - الفرق (إن وجد) يصبح ذمة عليه
    """
    class Status(models.TextChoices):
        DRAFT    = 'draft',    'مسودة'
        POSTED   = 'posted',   'مرحل'
        CANCELLED = 'cancelled','ملغي'

    number          = models.CharField(max_length=50, unique=True)
    date            = models.DateField()
    sales_rep       = models.ForeignKey(SalesRepresentative, on_delete=models.PROTECT)

    # المبالغ
    total_sales     = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    cash_delivered  = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    difference      = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    # وجهة الاستلام
    to_cash_box     = models.ForeignKey(
        'treasury.CashBox', null=True, blank=True,
        on_delete=models.PROTECT, related_name='rep_settlements_received'
    )
    to_bank         = models.ForeignKey(
        'treasury.BankAccount', null=True, blank=True,
        on_delete=models.PROTECT, related_name='rep_settlements_received'
    )

    notes           = models.TextField(blank=True)
    status          = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    journal_entry   = models.OneToOneField(
        'core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL
    )
    created_by      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at      = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.number} — {self.sales_rep.name} — {self.date}"

    def calculate_totals(self):
        """يحسب مجموع الفواتير اليومية للمندوب"""
        from django.db.models import Sum
        total = SalesInvoice.objects.filter(
            id__in=self.invoice_lines.values_list('invoice_id', flat=True)
        ).aggregate(t=Sum('total'))['t'] or 0
        self.total_sales = total
        self.difference  = total - self.cash_delivered
        return self


class RepSettlementInvoice(models.Model):
    """الفواتير المدرجة في التسوية"""
    settlement = models.ForeignKey(
        RepDailySettlement, on_delete=models.CASCADE, related_name='invoice_lines'
    )
    invoice    = models.ForeignKey(SalesInvoice, on_delete=models.PROTECT)

    class Meta:
        unique_together = ['settlement', 'invoice']

class Quotation(models.Model):
    """عرض سعر (أو عرض ترويجي) يطبق على قطاع كامل"""
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        ACTIVE = 'active', 'نشط'
        INVOICED = 'invoiced', 'محول لفاتورة'
        EXPIRED = 'expired', 'منتهي'
        CANCELLED = 'cancelled', 'ملغي'

    number = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200, verbose_name="اسم العرض", default="عرض جديد")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, verbose_name="العميل", null=True, blank=True)
    sector = models.ForeignKey(CustomerSector, on_delete=models.PROTECT, verbose_name="القطاع المستهدف", null=True, blank=True)
    sales_rep = models.ForeignKey(SalesRepresentative, on_delete=models.PROTECT, null=True, blank=True, verbose_name="مندوب المبيعات")
    start_date = models.DateField(verbose_name="تاريخ البدء")
    end_date = models.DateField(verbose_name="تاريخ الانتهاء")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    is_active = models.BooleanField(default=True)
    
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.sector.name}"

class QuotationLine(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey('inventory.Item', on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=14, decimal_places=4, default=1)
    unit_price = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    extra_discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="نسبة خصم إضافية %")
    tax_type = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.item.name} - {self.extra_discount_percent}%"

