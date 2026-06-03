import logging
from decimal import Decimal
from django.db import models
from django.db.models import UniqueConstraint, Q
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from apps.core.models import ConcurrencyModel

logger = logging.getLogger(__name__)

class POSStation(ConcurrencyModel):
    """نقطة البيع (الكاشير كجهاز أو محطة عمل)"""
    code = models.CharField(max_length=20, unique=True, verbose_name="كود النقطة")
    name = models.CharField(max_length=100, verbose_name="اسم نقطة البيع")
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT, verbose_name="المخزن المرتبط (لسحب البضاعة)")
    cash_box = models.ForeignKey('treasury.CashBox', on_delete=models.PROTECT, verbose_name="درج النقدية (الخزينة الافتراضية)")
    bank_account = models.ForeignKey('treasury.BankAccount', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="حساب البنك (لمدفوعات الفيزا)")
    mobile_wallet = models.ForeignKey('treasury.MobileWallet', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="المحفظة الإلكترونية المرتبطة")
    is_active = models.BooleanField(default=True, verbose_name="نشط")

    class Meta:
        verbose_name = "نقطة بيع"
        verbose_name_plural = "نقاط البيع"

    def __str__(self):
        return f"{self.name} - {self.warehouse.name}"

class POSSession(ConcurrencyModel):
    """وردية الكاشير (جلسة العمل من الفتح للإغلاق)"""
    class Status(models.TextChoices):
        OPEN = 'open', 'مفتوحة (قيد العمل)'
        CLOSED = 'closed', 'مغلقة'
        POSTED = 'posted', 'مرحّلة (تمت التسوية)'

    station = models.ForeignKey(POSStation, on_delete=models.PROTECT, related_name='sessions', verbose_name="نقطة البيع")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="الكاشير (المستخدم)")
    
    start_time = models.DateTimeField(auto_now_add=True, verbose_name="وقت فتح الوردية")
    end_time = models.DateTimeField(null=True, blank=True, verbose_name="وقت إغلاق الوردية")
    
    opening_cash = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="عُهدة الفتح (الكاش المبدئي)", validators=[MinValueValidator(Decimal('0.00'))])
    expected_cash = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="النقدية المتوقعة بنهاية الوردية", validators=[MinValueValidator(Decimal('0.00'))])
    actual_cash = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="النقدية الفعلية (الجرد الفعلي)", validators=[MinValueValidator(Decimal('0.00'))])
    difference = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="العجز / الزيادة")
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, verbose_name="حالة الوردية")
    
    # 🔗 جسر العبور للـ ERP الخلفي
    settlement = models.OneToOneField(
        'sales.RepDailySettlement', 
        null=True, blank=True, 
        on_delete=models.SET_NULL, 
        verbose_name="التسوية اليومية المرتبطة بالـ ERP"
    )

    shortage_collected_at = models.DateTimeField(null=True, blank=True, verbose_name="تم تحصيل العجز في")

    class Meta:
        verbose_name = "وردية نقطة بيع"
        verbose_name_plural = "ورديات نقاط البيع"

    def clean(self):
        if self.end_time and self.start_time and self.end_time < self.start_time:
            raise ValidationError({'end_time': 'وقت الإغلاق يجب أن يكون بعد وقت الفتح'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"وردية {self.user.username} - {self.station.name} ({self.start_time.strftime('%Y-%m-%d')})"

class POSOrder(ConcurrencyModel):
    """إيصال البيع (الفاتورة السريعة للعميل الطيار)"""
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة (قيد الإدخال)'
        PAID = 'paid', 'مدفوعة (جاهزة للتسليم)'
        POSTED = 'posted', 'مرحّلة للـ ERP (كفاتورة مبيعات)'
        CANCELLED = 'cancelled', 'ملغاة'

    receipt_number = models.CharField(max_length=50, unique=True, verbose_name="رقم الإيصال")
    session = models.ForeignKey(POSSession, on_delete=models.PROTECT, related_name='orders', verbose_name="الوردية")
    date = models.DateTimeField(auto_now_add=True, verbose_name="وقت الطلب")
    
    customer = models.ForeignKey('sales.Customer', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="العميل (يُترك فارغاً للعميل النقدي)")
    
    # الأرقام الإجمالية السريعة
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="الإجمالي قبل الضريبة والخصم", validators=[MinValueValidator(Decimal('0.00'))])
    discount = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="الخصم", validators=[MinValueValidator(Decimal('0.00'))])
    tax = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="الضريبة", validators=[MinValueValidator(Decimal('0.00'))])
    grand_total = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="الصافي المطلوب", validators=[MinValueValidator(Decimal('0.00'))])
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, verbose_name="الحالة")
    
    # 🔗 جسر العبور للـ ERP الخلفي
    sales_invoice = models.OneToOneField(
        'sales.SalesInvoice', 
        null=True, blank=True, 
        on_delete=models.SET_NULL, 
        verbose_name="فاتورة المبيعات الضريبية المرتبطة"
    )

    class Meta:
        verbose_name = "طلب نقطة بيع"
        verbose_name_plural = "طلبات نقاط البيع"

    def clean(self):
        if self.session.status != POSSession.Status.OPEN:
            raise ValidationError("لا يمكن إنشاء أو تعديل طلب في وردية مغلقة.")
        if self.discount > self.subtotal:
            raise ValidationError({'discount': 'الخصم لا يمكن أن يتجاوز الإجمالي قبل الخصم'})
        expected_grand_total = (self.subtotal or Decimal('0')) - (self.discount or Decimal('0')) + (self.tax or Decimal('0'))
        if round(self.grand_total, 2) != round(expected_grand_total, 2):
            raise ValidationError({'grand_total': 'الصافي المطلوب غير صحيح أو تم التلاعب به.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.receipt_number

class POSOrderLine(ConcurrencyModel):
    """سطر المنتجات داخل إيصال الـ POS"""
    order = models.ForeignKey(POSOrder, on_delete=models.PROTECT, related_name='lines', db_index=True)
    item = models.ForeignKey('inventory.Item', on_delete=models.PROTECT, verbose_name="الصنف", db_index=True)
    qty = models.DecimalField(max_digits=14, decimal_places=4, verbose_name="الكمية", validators=[MinValueValidator(Decimal('0.0001'))])
    price = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="سعر الوحدة", validators=[MinValueValidator(Decimal('0.00'))])
    discount = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="خصم السطر", validators=[MinValueValidator(Decimal('0.00'))])
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="نسبة الضريبة", validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))])
    total = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="إجمالي السطر", validators=[MinValueValidator(Decimal('0.00'))])

    class Meta:
        verbose_name = "سطر طلب نقطة بيع"
        verbose_name_plural = "أسطر طلبات نقاط البيع"
        ordering = ['-id']

    def clean(self):
        if self.order.status != POSOrder.Status.DRAFT:
            raise ValidationError("لا يمكن تعديل أو إضافة منتجات لطلب تم دفع أو ترحيله.")
        if self.price < 0:
            raise ValidationError({'price': 'سعر الوحدة لا يمكن أن يكون سالباً'})
        line_subtotal = (self.qty or Decimal('0')) * (self.price or Decimal('0'))
        if (self.discount or Decimal('0')) > line_subtotal:
            raise ValidationError({'discount': 'خصم السطر لا يمكن أن يتجاوز قيمته الإجمالية'})
        tax_amount = (line_subtotal - (self.discount or Decimal('0'))) * ((self.tax_percent or Decimal('0')) / Decimal('100'))
        expected_total = line_subtotal - (self.discount or Decimal('0')) + tax_amount
        if round(self.total, 2) != round(expected_total, 2):
            raise ValidationError({'total': 'إجمالي السطر غير صحيح أو تم التلاعب به.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.item.name} x {self.qty}"

class POSPayment(ConcurrencyModel):
    """مدفوعات الإيصال (يتيح للعميل الدفع كاش وفيزا لنفس الفاتورة)"""
    class PaymentMethod(models.TextChoices):
        CASH = 'cash', 'كاش (نقدية)'
        CARD = 'card', 'بطاقة بنكية (فيزا/ماستركارد)'
        WALLET = 'wallet', 'محفظة إلكترونية / فوري'

    order = models.ForeignKey(POSOrder, on_delete=models.PROTECT, related_name='payments', db_index=True)
    method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH, verbose_name="طريقة الدفع")
    amount = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="المبلغ المدفوع", validators=[MinValueValidator(Decimal('0.01'))])
    reference = models.CharField(max_length=100, blank=True, null=True, verbose_name="رقم العملية (للفيزا/المحفظة)")
    
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "مدفوعات نقطة بيع"
        verbose_name_plural = "مدفوعات نقاط البيع"
        ordering = ['-id']

    def clean(self):
        if self.order.status not in [POSOrder.Status.DRAFT, POSOrder.Status.PAID]:
            raise ValidationError("الطلب غير متاح لإضافة مدفوعات.")
        if self.method in ('card', 'wallet') and not self.reference:
            raise ValidationError({'reference': 'يجب إدخال رقم العملية لطرق الدفع الإلكترونية'})
        station = self.order.session.station
        if self.method == self.PaymentMethod.CARD and not station.bank_account:
            raise ValidationError({'method': 'نقطة البيع غير مرتبطة بحساب بنكي.'})
        if self.method == self.PaymentMethod.WALLET and not station.mobile_wallet:
            raise ValidationError({'method': 'نقطة البيع غير مرتبطة بمحفظة إلكترونية.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_method_display()} - {self.amount}"
