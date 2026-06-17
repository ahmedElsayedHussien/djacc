from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db.models import Sum
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from apps.core.models import ConcurrencyModel
from apps.core.utils import get_account_balance
from apps.e_invoice.models import EInvoiceLog

class CustomerSector(models.Model):
    """قطاع العملاء (مثلاً: قطاع التجزئة، قطاع الجملة، قطاع التصدير)"""
    name = models.CharField(max_length=100, unique=True, verbose_name="اسم القطاع")
    description = models.TextField(blank=True, verbose_name="الوصف")

    class Meta:
        verbose_name = "قطاع عميل"
        verbose_name_plural = "قطاعات العملاء"
        ordering = ['name']

    def __str__(self):
        return self.name

class Customer(ConcurrencyModel):
    code = models.CharField(max_length=20, unique=True, verbose_name="كود العميل")
    name = models.CharField(max_length=200, db_index=True, verbose_name="اسم العميل")
    account = models.OneToOneField('core.Account', on_delete=models.PROTECT, verbose_name="الحساب المحاسبي")
    sector = models.ForeignKey(CustomerSector, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="القطاع")
    tax_number = models.CharField(max_length=50, blank=True, verbose_name="الرقم الضريبي")
    credit_limit = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="حد الائتمان", validators=[MinValueValidator(Decimal('0.00'))])
    payment_terms_days = models.IntegerField(default=30, verbose_name="فترة السداد (أيام)", validators=[MinValueValidator(0)])
    address = models.TextField(blank=True, verbose_name="العنوان")
    phone = models.CharField(max_length=20, blank=True, verbose_name="الهاتف")
    email = models.EmailField(blank=True, verbose_name="البريد الإلكتروني")
    customer_type = models.CharField(max_length=10, choices=[('cash','نقدي'), ('credit','آجل')], default='credit', verbose_name="نوع التعامل")
    price_list = models.ForeignKey('PriceList', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="قائمة الأسعار")
    is_taxable = models.BooleanField(default=True, verbose_name="خاضع للضريبة")
    default_tax1 = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.SET_NULL, related_name='+', verbose_name="الضريبة الافتراضية 1")
    default_tax2 = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.SET_NULL, related_name='+', verbose_name="الضريبة الافتراضية 2")

    class Meta:
        verbose_name = "عميل"
        verbose_name_plural = "العملاء"
        ordering = ['code']

    @property
    def balance(self):
        if self.account:
            return get_account_balance(self.account)
        return 0

    def clean(self):
        if self.customer_type == 'credit' and self.credit_limit <= 0:
            raise ValidationError({'credit_limit': 'حد الائتمان يجب أن يكون أكبر من صفر للعملاء الآجلين'})

    def __str__(self):
        return f"{self.code} - {self.name}"

class SalesRepresentative(models.Model):
    """مندوب مبيعات"""
    employee = models.OneToOneField('hr.Employee', on_delete=models.CASCADE, related_name='sales_profile', null=True, blank=True, verbose_name="الموظف المرتبط")
    code = models.CharField(max_length=20, unique=True, verbose_name="كود المندوب")
    name = models.CharField(max_length=200, help_text="سيتم جلبه تلقائياً من الموظف", verbose_name="اسم المندوب")
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="المستخدم")
    phone = models.CharField(max_length=20, blank=True, verbose_name="الهاتف")
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT, verbose_name="مخزن المندوب")
    cash_box = models.ForeignKey('treasury.CashBox', on_delete=models.PROTECT, verbose_name="خزنة المندوب")
    account = models.OneToOneField(
        'core.Account',
        on_delete=models.PROTECT,
        null=True, blank=True,
        verbose_name="حساب العهدة",
        help_text='حساب ذمة المندوب — يُنشأ تلقائياً'
    )
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="نسبة العمولة (%)", validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))])
    territory = models.CharField(max_length=200, blank=True, verbose_name="المنطقة/النطاق")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    supervisor = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="المشرف المباشر")

    class Meta:
        verbose_name = "مندوب مبيعات"
        verbose_name_plural = "مندوبي المبيعات"
        ordering = ['name']

    def clean(self):
        if self.supervisor and self.supervisor.pk == self.pk:
            raise ValidationError({'supervisor': 'المشرف لا يمكن أن يكون نفس المندوب'})

    def save(self, *args, **kwargs):
        if self.employee:
            self.name = f"{self.employee.first_name} {self.employee.last_name}"
            self.phone = self.employee.phone
            self.user = self.employee.user
        self.full_clean()
        super().save(*args, **kwargs)

        # Automatically assign user to the Sales (مبيعات) group
        if self.user:
            from django.contrib.auth.models import Group
            sales_group = Group.objects.filter(name__in=['مبيعات', 'المبيعات']).first()
            if sales_group:
                self.user.groups.add(sales_group)
                
                if not self.user.is_staff:
                    self.user.is_staff = True
                    self.user.save(update_fields=['is_staff'])

    def __str__(self):
        return self.name

class PriceList(models.Model):
    """قائمة أسعار"""
    name = models.CharField(max_length=200, verbose_name="اسم القائمة")
    is_default = models.BooleanField(default=False, verbose_name="القائمة الافتراضية")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="نشط")

    class Meta:
        verbose_name = "قائمة أسعار"
        verbose_name_plural = "قوائم الأسعار"
        ordering = ['name']

    def clean(self):
        if self.is_default:
            qs = PriceList.objects.filter(is_default=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError({'is_default': 'يوجد بالفعل قائمة أسعار افتراضية. قم بإلغاء تفعيلها أولاً.'})
        if not self.is_active and self.is_default:
            raise ValidationError({'is_default': 'القائمة غير النشطة لا يمكن أن تكون افتراضية'})

    def __str__(self):
        return self.name

class PriceListItem(models.Model):
    """سعر صنف في قائمة أسعار"""
    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, related_name='items', verbose_name="قائمة الأسعار")
    item = models.ForeignKey('inventory.Item', on_delete=models.PROTECT, db_index=True, verbose_name="الصنف")
    unit_price = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(0)], verbose_name="سعر الوحدة")
    min_qty = models.DecimalField(max_digits=14, decimal_places=4, default=1, validators=[MinValueValidator(0)], verbose_name="أقل كمية")

    class Meta:
        unique_together = ['price_list', 'item', 'min_qty']
        verbose_name = "سعر صنف"
        verbose_name_plural = "أسعار الأصناف"

    def clean(self):
        if self.unit_price <= 0:
            raise ValidationError({'unit_price': 'سعر الوحدة يجب أن يكون أكبر من صفر'})
        if self.min_qty <= 0:
            raise ValidationError({'min_qty': 'الحد الأدنى للكمية يجب أن يكون أكبر من صفر'})

    def __str__(self):
        return f"{self.price_list.name} - {self.item.name} - {self.unit_price}"

class IntermediaryCompany(models.Model):
    """شركات التحصيل الوسيطة (فوري، أمان، مندوب خارجي)"""
    name = models.CharField(max_length=200, verbose_name="اسم الشركة")
    account = models.OneToOneField('core.Account', on_delete=models.PROTECT, verbose_name="الحساب الوسيط")
    commission_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="نسبة عمولة التحصيل (%)", validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))])
    is_active = models.BooleanField(default=True, verbose_name="نشط")

    class Meta:
        verbose_name = "شركة وسيطة"
        verbose_name_plural = "الشركات الوسيطة"
        ordering = ['name']

    def __str__(self):
        return self.name

class SalesInvoice(ConcurrencyModel):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        POSTED = 'posted', 'مرحل'
        CANCELLED = 'cancelled', 'ملغي'

    class PaymentType(models.TextChoices):
        CASH = 'cash', 'نقدي'
        CREDIT = 'credit', 'آجل'

    number = models.CharField(max_length=50, unique=True, verbose_name="رقم الفاتورة")
    date = models.DateField(db_index=True, verbose_name="تاريخ الفاتورة")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, db_index=True, verbose_name="العميل")
    payment_type = models.CharField(max_length=10, choices=PaymentType.choices, default=PaymentType.CREDIT, verbose_name="نوع الدفع")
    sales_rep = models.ForeignKey(SalesRepresentative, on_delete=models.PROTECT, null=True, blank=True, verbose_name="المندوب")
    cash_box = models.ForeignKey('treasury.CashBox', on_delete=models.PROTECT, null=True, blank=True, verbose_name="الخزينة (للنقدي)")
    due_date = models.DateField(verbose_name="تاريخ الاستحقاق")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True, verbose_name="الحالة")
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="الصافي", validators=[MinValueValidator(Decimal('0.00'))])
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="إجمالي الخصم", validators=[MinValueValidator(Decimal('0.00'))])
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="إجمالي الضريبة", validators=[MinValueValidator(Decimal('0.00'))])
    total = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="الإجمالي النهائي", validators=[MinValueValidator(Decimal('0.00'))])
    paid_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="المبلغ المدفوع", validators=[MinValueValidator(Decimal('0.00'))])
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    cost_center = models.ForeignKey('core.CostCenter', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="مركز التكلفة")
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="قيد اليومية")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="أنشئ بواسطة")

    class Meta:
        verbose_name = "فاتورة مبيعات"
        verbose_name_plural = "فواتير المبيعات"
        ordering = ['-date', '-id']

    def clean(self):
        if self.date and self.date > timezone.now().date():
            raise ValidationError({'date': 'تاريخ الفاتورة لا يمكن أن يكون في المستقبل'})
        if self.date and self.due_date and self.due_date < self.date:
            raise ValidationError({'due_date': 'تاريخ الاستحقاق يجب أن يكون بعد أو يساوي تاريخ الفاتورة'})
        if self.payment_type == 'cash' and not self.cash_box:
            raise ValidationError({'cash_box': 'يرجى تحديد الخزينة للفاتورة النقدية'})
        if self.payment_type == 'credit' and self.cash_box:
            raise ValidationError({'cash_box': 'لا يمكن تحديد خزينة للفاتورة الآجلة'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.number

    @property
    def einvoice_log(self):
        ct = ContentType.objects.get_for_model(self)
        return EInvoiceLog.objects.filter(content_type=ct, object_id=self.id).first()

    @property
    def einvoice_status(self):
        log = self.einvoice_log
        return log.status if log else 'not_submitted'

    @property
    def einvoice_uuid(self):
        log = self.einvoice_log
        return log.uuid if log else None

class SalesInvoiceLine(models.Model):
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name='lines', db_index=True, verbose_name="الفاتورة")
    item = models.ForeignKey('inventory.Item', on_delete=models.PROTECT, db_index=True, verbose_name="الصنف")
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT, verbose_name="المخزن")
    unit = models.ForeignKey('inventory.UnitOfMeasure', on_delete=models.PROTECT, null=True, blank=True, verbose_name="الوحدة")
    quantity = models.DecimalField(max_digits=14, decimal_places=4, verbose_name="الكمية", validators=[MinValueValidator(Decimal('0.0001'))])
    base_quantity = models.DecimalField(max_digits=14, decimal_places=4, default=0, help_text="الكمية بالوحدة الأساسية", verbose_name="الكمية الأساسية", validators=[MinValueValidator(Decimal('0.00'))])
    unit_price = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="سعر الوحدة", validators=[MinValueValidator(Decimal('0.00'))])
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, blank=True, verbose_name="نسبة الخصم %", validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))])
    extra_discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, blank=True, verbose_name="نسبة خصم إضافي %", validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))])
    tax_type = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT, verbose_name="نوع الضريبة 1")
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, blank=True, verbose_name="نسبة ضريبة 1", validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))])
    tax_type2 = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT, related_name='+', verbose_name="نوع الضريبة 2")
    tax_percent2 = models.DecimalField(max_digits=5, decimal_places=2, default=0, blank=True, verbose_name="نسبة ضريبة 2", validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))])
    total = models.DecimalField(max_digits=18, decimal_places=2, default=0, blank=True, verbose_name="الإجمالي", validators=[MinValueValidator(Decimal('0.00'))])
    cost = models.DecimalField(max_digits=18, decimal_places=2, default=0, help_text="تكلفة الوحدة وقت البيع", verbose_name="التكلفة", validators=[MinValueValidator(Decimal('0.00'))])
    revenue_account = models.ForeignKey('core.Account', on_delete=models.PROTECT, verbose_name="حساب الإيرادات")
    cost_of_goods_account = models.ForeignKey('core.Account', on_delete=models.PROTECT, related_name='+', verbose_name="حساب تكلفة المبيعات")

    class Meta:
        verbose_name = "صنف في فاتورة مبيعات"
        verbose_name_plural = "أصناف فواتير المبيعات"

    def clean(self):
        disc = self.discount_percent or 0
        extra = self.extra_discount_percent or 0
        if disc + extra > 100:
            raise ValidationError('إجمالي نسبة الخصم لا يمكن أن يتجاوز 100%')

    def save(self, *args, **kwargs):
        from decimal import Decimal, ROUND_HALF_UP
        if self.total is not None:
            self.total = Decimal(str(self.total)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def discount_amount(self):
        from decimal import Decimal
        subtotal = self.quantity * self.unit_price
        disc = subtotal * ((self.discount_percent or Decimal('0')) / Decimal('100'))
        extra = subtotal * ((self.extra_discount_percent or Decimal('0')) / Decimal('100'))
        return disc + extra

    @property
    def tax_amount(self):
        subtotal = self.quantity * self.unit_price
        disc_val = self.discount_amount
        net_line = subtotal - disc_val
        return self.total - net_line

class CustomerReceipt(models.Model):
    """تحصيل من عميل"""
    class ChequeStatus(models.TextChoices):
        PENDING = 'pending', 'قيد التحصيل'
        COLLECTED = 'collected', 'تم التحصيل'
        BOUNCED = 'bounced', 'شيك مرتجع'
        CANCELLED = 'cancelled', 'ملغي'

    number = models.CharField(max_length=50, unique=True, verbose_name="رقم السند")
    date = models.DateField(db_index=True, verbose_name="تاريخ التحصيل")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, db_index=True, verbose_name="العميل")
    amount = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="المبلغ", validators=[MinValueValidator(Decimal('0.01'))])
    payment_method = models.CharField(max_length=20, choices=[
        ('cash','نقدي'),
        ('bank','تحويل بنكي'),
        ('cheque','شيك'),
        ('intermediary','شركة وسيطة (فوري/أمان)')
    ], db_index=True, verbose_name="طريقة الدفع")
    bank_account = models.ForeignKey('treasury.BankAccount', null=True, blank=True, on_delete=models.PROTECT, verbose_name="الحساب البنكي")
    cash_box = models.ForeignKey('treasury.CashBox', null=True, blank=True, on_delete=models.PROTECT, verbose_name="الخزينة المستلمة")
    intermediary_company = models.ForeignKey(IntermediaryCompany, null=True, blank=True, on_delete=models.PROTECT, verbose_name="الشركة الوسيطة")
    
    # Cheque details
    cheque_number = models.CharField(max_length=50, blank=True, verbose_name="رقم الشيك")
    cheque_due_date = models.DateField(null=True, blank=True, verbose_name="تاريخ استحقاق الشيك")
    cheque_status = models.CharField(max_length=20, choices=ChequeStatus.choices, default=ChequeStatus.PENDING, verbose_name="حالة الشيك")

    reference = models.CharField(max_length=100, blank=True, verbose_name="المرجع")
    collected_at = models.DateField(null=True, blank=True, verbose_name="تاريخ الإيداع")
    invoices = models.ManyToManyField(SalesInvoice, through='ReceiptAllocation', verbose_name="الفواتير المسددة")
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="قيد اليومية")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, verbose_name="أنشئ بواسطة")

    class Meta:
        verbose_name = "سند تحصيل"
        verbose_name_plural = "سندات التحصيل"
        ordering = ['-date', '-id']

    def clean(self):
        if self.payment_method == 'cheque':
            if not self.cheque_number:
                raise ValidationError({'cheque_number': 'يجب إدخال رقم الشيك'})
            if not self.cheque_due_date:
                raise ValidationError({'cheque_due_date': 'يجب إدخال تاريخ استحقاق الشيك'})
            if self.cheque_due_date and self.date and self.cheque_due_date < self.date:
                raise ValidationError({'cheque_due_date': 'تاريخ استحقاق الشيك يجب أن يكون بعد أو يساوي تاريخ التحصيل'})
        if self.payment_method == 'cash' and not self.cash_box:
            raise ValidationError({'cash_box': 'يجب تحديد الخزينة للدفع النقدي'})
        if self.payment_method == 'bank' and not self.bank_account:
            raise ValidationError({'bank_account': 'يجب تحديد الحساب البنكي للتحويل'})
        if self.payment_method == 'intermediary' and not self.intermediary_company:
            raise ValidationError({'intermediary_company': 'يجب تحديد الشركة الوسيطة'})

    def __str__(self):
        return self.number

    @property
    def is_collected(self):
        return self.cheque_status == self.ChequeStatus.COLLECTED

class ReceiptAllocation(models.Model):
    receipt = models.ForeignKey(CustomerReceipt, on_delete=models.CASCADE, db_index=True)
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, db_index=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])

    def clean(self):
        if self.invoice and self.receipt and self.invoice.customer_id != self.receipt.customer_id:
            raise ValidationError('الفاتورة لا تنتمي لنفس عميل سند التحصيل')
        if self.amount <= 0:
            raise ValidationError({'amount': 'مبلغ التوزيع يجب أن يكون أكبر من صفر'})
        if self.invoice:
            paid = getattr(self.invoice, 'paid_amount', 0) or 0
            remaining = self.invoice.total - paid
            if self.amount > remaining:
                raise ValidationError({
                    'amount': f'مبلغ التوزيع ({self.amount}) يتجاوز المتبقي من الفاتورة ({remaining})'
                })

    class Meta:
        verbose_name = "توزيع تحصيل"
        verbose_name_plural = "توزيعات التحصيل"

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

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError('تاريخ النهاية يجب أن يكون بعد أو يساوي تاريخ البداية')

    def __str__(self):
        return f"{self.sales_rep.name} - {self.target_amount} ({self.start_date} to {self.end_date})"

class SalesReturn(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        POSTED = 'posted', 'مرحل'
        CANCELLED = 'cancelled', 'ملغي'

    number = models.CharField(max_length=50, unique=True, verbose_name="رقم المرتجع")
    date = models.DateField(db_index=True, verbose_name="التاريخ")
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.PROTECT, null=True, blank=True, verbose_name='الفاتورة الأصلية')
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, db_index=True, verbose_name="العميل")
    sales_rep = models.ForeignKey(SalesRepresentative, on_delete=models.PROTECT, null=True, blank=True, verbose_name="المندوب")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True, verbose_name="الحالة")
    
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="الصافي")
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="إجمالي الخصم")
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="إجمالي الضريبة")
    total = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="الإجمالي", validators=[MinValueValidator(Decimal('0.00'))])
    
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
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
        verbose_name = "مرتجع مبيعات"
        verbose_name_plural = "مرتجعات المبيعات"
        ordering = ['-date', '-id']

    @property
    def payment_type_display(self):
        return 'نقدي' if self.payment_type == 'cash' else 'آجل'

    def clean(self):
        if self.date and self.date > timezone.now().date():
            raise ValidationError({'date': 'تاريخ المرتجع لا يمكن أن يكون في المستقبل'})
        if self.invoice and self.date and self.invoice.date and self.date < self.invoice.date:
            raise ValidationError({'date': 'تاريخ المرتجع لا يمكن أن يكون قبل تاريخ الفاتورة الأصلية'})
        if self.invoice and self.customer_id != self.invoice.customer_id:
            raise ValidationError('العميل لا يتطابق مع عميل الفاتورة الأصلية')
        if self.payment_type == 'cash' and not self.cash_box:
            raise ValidationError({'cash_box': 'يرجى تحديد الخزينة للمرتجع النقدي'})

    def save(self, *args, **kwargs):
        if self.invoice:
            self.payment_type = self.invoice.payment_type
            if self.invoice.payment_type == 'cash' and self.invoice.cash_box:
                self.cash_box = self.invoice.cash_box
        elif self.sales_rep and self.sales_rep.cash_box and self.payment_type == 'cash':
            self.cash_box = self.sales_rep.cash_box
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.number

class SalesReturnLine(models.Model):
    sales_return = models.ForeignKey(SalesReturn, on_delete=models.CASCADE, related_name='lines', verbose_name="المرتجع")
    item = models.ForeignKey('inventory.Item', on_delete=models.PROTECT, db_index=True, verbose_name="الصنف")
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT, verbose_name="المخزن")
    unit = models.ForeignKey('inventory.UnitOfMeasure', on_delete=models.PROTECT, null=True, blank=True, verbose_name="الوحدة")
    quantity = models.DecimalField(max_digits=14, decimal_places=4, verbose_name="الكمية", validators=[MinValueValidator(Decimal('0.0001'))])
    base_quantity = models.DecimalField(max_digits=14, decimal_places=4, default=0, help_text="الكمية بالوحدة الأساسية", verbose_name="الكمية الأساسية", validators=[MinValueValidator(Decimal('0.00'))])
    unit_price = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="سعر الوحدة", validators=[MinValueValidator(Decimal('0.00'))])
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="نسبة الخصم", validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))])
    tax_type = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT, verbose_name="نوع الضريبة")
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="نسبة الضريبة", validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))])
    tax_type2 = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT, related_name='+', verbose_name="نوع الضريبة 2")
    tax_percent2 = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="نسبة الضريبة 2", validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))])
    total = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="الإجمالي", validators=[MinValueValidator(Decimal('0.00'))])
    cost = models.DecimalField(max_digits=18, decimal_places=2, default=0, help_text="تكلفة الوحدة وقت المرتجع", verbose_name="التكلفة", validators=[MinValueValidator(Decimal('0.00'))])
    
    return_account = models.ForeignKey('core.Account', on_delete=models.PROTECT, related_name='+', verbose_name="حساب المردودات")
    cogs_account = models.ForeignKey('core.Account', on_delete=models.PROTECT, related_name='+', verbose_name="حساب تكلفة المبيعات")

    class Meta:
        verbose_name = "صنف في مرتجع"
        verbose_name_plural = "أصناف المرتجعات"

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError({'quantity': 'الكمية يجب أن تكون أكبر من صفر'})
        if self.unit_price < 0:
            raise ValidationError({'unit_price': 'سعر الوحدة لا يمكن أن يكون سالباً'})
        if hasattr(self, 'sales_return') and self.sales_return and getattr(self.sales_return, 'invoice', None):
            # User requested to allow returning items not in the invoice and quantities exceeding it.
            # We just leave this block empty or remove the constraints.
            pass
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

    number          = models.CharField(max_length=50, unique=True, verbose_name="رقم التسوية")
    date            = models.DateField(db_index=True, verbose_name="التاريخ")
    sales_rep       = models.ForeignKey(SalesRepresentative, on_delete=models.PROTECT, db_index=True, verbose_name="المندوب")

    # المبالغ
    total_sales     = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))])
    cash_delivered  = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(Decimal('0.00'))])
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
    to_wallet       = models.ForeignKey(
        'treasury.MobileWallet', null=True, blank=True,
        on_delete=models.PROTECT, related_name='rep_settlements_received'
    )

    notes           = models.TextField(blank=True, verbose_name="ملاحظات")
    status          = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True, verbose_name="الحالة")
    journal_entry   = models.OneToOneField(
        'core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="قيد اليومية"
    )
    created_by      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="أنشئ بواسطة")
    created_at      = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "تسوية يومية"
        verbose_name_plural = "التسويات اليومية"
        ordering = ['-date', '-id']

    def clean(self):
        if self.date and self.date > timezone.now().date():
            raise ValidationError({'date': 'تاريخ التسوية لا يمكن أن يكون في المستقبل'})
        if not self.to_cash_box and not self.to_bank and not self.to_wallet:
            raise ValidationError('يجب تحديد وجهة واحدة على الأقل (خزينة أو بنك أو محفظة)')

    def __str__(self):
        return f"{self.number} — {self.sales_rep.name} — {self.date}"

    @property
    def abs_difference(self):
        return abs(self.difference)

    def calculate_totals(self):
        """يحسب مجموع الفواتير اليومية للمندوب (ناقص المرتجعات النقدية)"""
        total = Decimal('0')
        if self.invoice_lines.exists():
            total = SalesInvoice.objects.filter(
                id__in=self.invoice_lines.values_list('invoice_id', flat=True)
            ).aggregate(t=Sum('total'))['t'] or Decimal('0')
            
        total_returns = SalesReturn.objects.filter(
            sales_rep=self.sales_rep,
            date=self.date,
            payment_type='cash',
            status=SalesReturn.Status.POSTED
        ).aggregate(t=Sum('total'))['t'] or Decimal('0')
        
        self.total_sales = total - total_returns
        self.difference  = self.total_sales - self.cash_delivered
        return self

    def save(self, *args, **kwargs):
        if self.pk and self.invoice_lines.exists() and not kwargs.get('update_fields'):
            self.calculate_totals()
        super().save(*args, **kwargs)


class RepSettlementInvoice(models.Model):
    """الفواتير المدرجة في التسوية"""
    settlement = models.ForeignKey(
        RepDailySettlement, on_delete=models.CASCADE, related_name='invoice_lines', verbose_name="التسوية"
    )
    invoice    = models.ForeignKey(SalesInvoice, on_delete=models.PROTECT, verbose_name="الفاتورة")

    class Meta:
        unique_together = ['settlement', 'invoice']
        verbose_name = "فاتورة تسوية"
        verbose_name_plural = "فواتير التسوية"

    def clean(self):
        existing = RepSettlementInvoice.objects.filter(invoice=self.invoice).exclude(
            settlement__status=RepDailySettlement.Status.DRAFT
        ).exclude(pk=self.pk)
        if existing.exists():
            raise ValidationError(
                f'الفاتورة {self.invoice} مدرجة بالفعل في تسوية أخرى (رقم {existing.first().settlement.number})'
            )

class Quotation(models.Model):
    """عرض سعر (أو عرض ترويجي) يطبق على قطاع كامل"""
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        ACTIVE = 'active', 'نشط'
        INVOICED = 'invoiced', 'محول لفاتورة'
        EXPIRED = 'expired', 'منتهي'
        CANCELLED = 'cancelled', 'ملغي'

    number = models.CharField(max_length=50, unique=True, verbose_name="رقم العرض")
    name = models.CharField(max_length=200, verbose_name="اسم العرض", default="عرض جديد")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, verbose_name="العميل", null=True, blank=True)
    sector = models.ForeignKey(CustomerSector, on_delete=models.PROTECT, verbose_name="القطاع المستهدف", null=True, blank=True)
    sales_rep = models.ForeignKey(SalesRepresentative, on_delete=models.PROTECT, null=True, blank=True, verbose_name="مندوب المبيعات")
    start_date = models.DateField(verbose_name="تاريخ البدء")
    end_date = models.DateField(verbose_name="تاريخ الانتهاء")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True, verbose_name="الحالة")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="الصافي", validators=[MinValueValidator(Decimal('0.00'))])
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="إجمالي الخصم", validators=[MinValueValidator(Decimal('0.00'))])
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="إجمالي الضريبة", validators=[MinValueValidator(Decimal('0.00'))])
    total = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="الإجمالي", validators=[MinValueValidator(Decimal('0.00'))])
    
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="أنشئ بواسطة")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "عرض سعر"
        verbose_name_plural = "عروض الأسعار"
        ordering = ['-start_date', '-id']

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({'end_date': 'تاريخ الانتهاء يجب أن يكون بعد أو يساوي تاريخ البدء'})
        if not self.customer and not self.sector:
            raise ValidationError('يجب تحديد عميل أو قطاع لعرض السعر')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} - {self.sector.name if self.sector else '—'}"

class QuotationLine(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='lines', verbose_name="العرض")
    item = models.ForeignKey('inventory.Item', on_delete=models.PROTECT, db_index=True, verbose_name="الصنف")
    unit = models.ForeignKey('inventory.UnitOfMeasure', on_delete=models.PROTECT, null=True, blank=True, verbose_name="الوحدة")
    quantity = models.DecimalField(max_digits=14, decimal_places=4, default=1, verbose_name="الكمية", validators=[MinValueValidator(Decimal('0.0001'))])
    base_quantity = models.DecimalField(max_digits=14, decimal_places=4, default=0, help_text="الكمية بالوحدة الأساسية", verbose_name="الكمية الأساسية", validators=[MinValueValidator(Decimal('0.00'))])
    unit_price = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="سعر الوحدة", validators=[MinValueValidator(Decimal('0.00'))])
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="نسبة الخصم", validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))])
    tax_type = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT, verbose_name="نوع الضريبة")
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="نسبة الضريبة", validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))])
    total = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="الإجمالي", validators=[MinValueValidator(Decimal('0.00'))])

    class Meta:
        verbose_name = "صنف في عرض سعر"
        verbose_name_plural = "أصناف عروض الأسعار"

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError({'quantity': 'الكمية يجب أن تكون أكبر من صفر'})
        if self.unit_price < 0:
            raise ValidationError({'unit_price': 'سعر الوحدة لا يمكن أن يكون سالباً'})
        if self.discount_percent < 0:
            raise ValidationError({'discount_percent': 'نسبة الخصم لا يمكن أن تكون سالبة'})
        if self.discount_percent > 100:
            raise ValidationError({'discount_percent': 'نسبة الخصم لا يمكن أن تتجاوز 100%'})
        if self.tax_percent < 0:
            raise ValidationError({'tax_percent': 'نسبة الضريبة لا يمكن أن تكون سالبة'})
        if self.tax_percent > 100:
            raise ValidationError({'tax_percent': 'نسبة الضريبة لا يمكن أن تتجاوز 100%'})

    def __str__(self):
        return f"{self.item.name} - {self.discount_percent}%"
