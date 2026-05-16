from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from decimal import Decimal
from django.conf import settings
from django.utils import timezone

class ItemCategory(models.Model):
    code = models.CharField(max_length=20, unique=True, verbose_name="كود التصنيف")
    name = models.CharField(max_length=200, verbose_name="اسم التصنيف")
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, verbose_name="التصنيف الأب")

    def __str__(self):
        return self.name

class UnitOfMeasure(models.Model):
    code = models.CharField(max_length=10, unique=True, verbose_name="كود الوحدة")
    name = models.CharField(max_length=50, verbose_name="اسم الوحدة")

    def __str__(self):
        return self.name

class Item(models.Model):

    code = models.CharField(max_length=50, unique=True, verbose_name="كود الصنف")
    name = models.CharField(max_length=300, verbose_name="اسم الصنف")
    category = models.ForeignKey(ItemCategory, on_delete=models.PROTECT, verbose_name="التصنيف")
    
    # Unit Management
    base_unit = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, related_name='items_as_base', verbose_name='الوحدة الأساسية (أصغر وحدة)')
    purchase_unit = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, related_name='items_as_purchase', null=True, blank=True, verbose_name="وحدة المشتريات")
    sales_unit = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, related_name='items_as_sales', null=True, blank=True, verbose_name="وحدة المبيعات")
    
    # Factor: 1 Box = X Pieces. Example: base=Piece, sales=Box, factor=12.
    conversion_factor = models.DecimalField(max_digits=10, decimal_places=4, default=1, help_text="كم وحدة أساسية توجد في وحدة المبيعات؟", verbose_name="معامل تحويل البيع")
    purchase_conversion_factor = models.DecimalField(max_digits=10, decimal_places=4, default=1, help_text="كم وحدة أساسية توجد في وحدة المشتريات؟", verbose_name="معامل تحويل الشراء")

    inventory_account = models.ForeignKey('core.Account', on_delete=models.PROTECT, related_name='inventory_items', verbose_name="حساب المخزون (أصول)")
    cogs_account = models.ForeignKey('core.Account', on_delete=models.PROTECT, related_name='cogs_items', verbose_name="حساب التكلفة (مصروف)")
    sales_account = models.ForeignKey('core.Account', on_delete=models.PROTECT, related_name='sales_items', null=True, blank=True, verbose_name="حساب المبيعات (إيراد)")
    minimum_stock = models.DecimalField(max_digits=14, decimal_places=4, default=0, verbose_name="حد الطلب")
    barcode = models.CharField(max_length=100, blank=True, verbose_name="الباركود")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    standard_price = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="السعر الافتراضي")

    def __str__(self):
        return f"{self.code} - {self.name}"
    
    def clean(self):
        from django.core.exceptions import ValidationError
        # Rule: If units are the same, factor MUST be 1
        if self.sales_unit == self.base_unit and self.conversion_factor != 1:
            self.conversion_factor = 1
            
        if self.purchase_unit == self.base_unit and self.purchase_conversion_factor != 1:
            self.purchase_conversion_factor = 1

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def convert_to_base(self, quantity, unit):
        """Converts a quantity in a specific unit to the base unit."""
        if unit == self.base_unit:
            return quantity
        if unit == self.sales_unit:
            return quantity * self.conversion_factor
        if unit == self.purchase_unit:
            return quantity * self.purchase_conversion_factor
        
        # ✅ Fix #8: منع التحويل الصامت في حالة استخدام وحدة غير معروفة للصنف
        raise ValueError(f"الوحدة '{unit}' غير مرتبطة بالصنف '{self.name}'. لا يمكن إجراء التحويل.")

class Warehouse(models.Model):
    code = models.CharField(max_length=20, unique=True, verbose_name="كود المخزن")
    name = models.CharField(max_length=200, verbose_name="اسم المخزن")
    gl_account = models.ForeignKey('core.Account', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="حساب المخزون (أستاذ عام)")
    location = models.TextField(blank=True, verbose_name="العنوان/الموقع")
    is_active = models.BooleanField(default=True, verbose_name="نشط")

    def __str__(self):
        return self.name

class StockMovement(models.Model):
    """
    Every inventory change is recorded as a StockMovement.
    Positive quantity = stock in. Negative = stock out.
    """
    class MovementType(models.TextChoices):
        PURCHASE_RECEIPT = 'purchase_in', 'استلام مشتريات'
        SALES_ISSUE = 'sales_out', 'صرف مبيعات'
        TRANSFER_IN = 'transfer_in', 'تحويل وارد'
        TRANSFER_OUT = 'transfer_out', 'تحويل صادر'
        ADJUSTMENT_IN = 'adj_in', 'تسوية زيادة'
        ADJUSTMENT_OUT = 'adj_out', 'تسوية نقص'
        OPENING = 'opening', 'رصيد افتتاحي'
        LOADING_IN = 'loading_in', 'تحميل وارد (للمندوب)'
        LOADING_OUT = 'loading_out', 'تحميل صادر (من المخزن)'
        SALE_RETURN = 'sale_return', 'مرتجع مبيعات'
        PURCHASE_RETURN = 'purchase_return', 'مرتجع مشتريات'

    date = models.DateField()
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=2)
    total_cost = models.DecimalField(max_digits=18, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True)
    
    content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    source = GenericForeignKey('content_type', 'object_id')
    
    running_quantity = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    running_value = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)

    @property
    def get_source_url(self):
        if not self.content_type:
            return None
        
        from django.urls import reverse
        model_name = self.content_type.model
        
        try:
            if model_name == 'stockvoucher':
                return reverse('inventory:voucher-detail', args=[self.object_id])
            elif model_name == 'warehousetransfer':
                return reverse('inventory:transfer-detail', args=[self.object_id])
            elif model_name == 'loadingorder':
                return reverse('inventory:loading-detail', args=[self.object_id])
            elif model_name == 'salesinvoice':
                return reverse('sales:invoice-detail', args=[self.object_id])
            elif model_name == 'purchaseinvoice':
                return reverse('purchases:invoice-detail', args=[self.object_id])
            elif model_name == 'salesreturn':
                return reverse('sales:return-detail', args=[self.object_id])
            elif model_name == 'purchasereturn':
                return reverse('purchases:return-detail', args=[self.object_id])
        except:
            pass
        return None


    def __str__(self):
        return f"{self.item.name} - {self.movement_type} - {self.quantity}"

class ItemLedger(models.Model):
    """Per-item, per-warehouse balance snapshot for fast queries"""
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE)
    quantity_on_hand = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    total_value = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('item', 'warehouse')]

    @property
    def average_cost(self):
        if self.quantity_on_hand == 0:
            return Decimal('0')
        # Ensure cost is always positive even if stock is negative
        cost = self.total_value / self.quantity_on_hand
        return abs(cost).quantize(Decimal('0.00'))

class WarehouseTransfer(models.Model):
    """تحويل مخزني بين المستودعات"""
    number = models.CharField(max_length=50, unique=True, verbose_name="رقم التحويل")
    date = models.DateField(verbose_name="تاريخ التحويل")
    from_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='transfers_out', verbose_name="من مخزن")
    to_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='transfers_in', verbose_name="إلى مخزن")
    status = models.CharField(max_length=20, choices=[('draft', 'مسودة'), ('posted', 'مرحّب'), ('cancelled', 'ملغي')], default='draft', verbose_name="الحالة")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    
    def __str__(self):
        return f"{self.number}"

class WarehouseTransferLine(models.Model):
    """سطر تحويل مخزني"""
    transfer = models.ForeignKey(WarehouseTransfer, on_delete=models.CASCADE, related_name='lines', verbose_name="طلب التحويل")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, verbose_name="الصنف")
    quantity = models.DecimalField(max_digits=14, decimal_places=4, verbose_name="الكمية")
    unit_cost = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, verbose_name="تكلفة الوحدة")
    notes = models.CharField(max_length=200, blank=True, verbose_name="ملاحظات")
    
    def __str__(self):
        return f"{self.item.name} - {self.quantity}"



class LoadingOrder(models.Model):
    """طلب تحميل من المخزن الرئيسي لمخزن المندوب"""
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        PENDING = 'pending', 'في انتظار الاعتماد'
        APPROVED = 'approved', 'معتمد'
        ISSUED = 'issued', 'تم الصرف'
        CANCELLED = 'cancelled', 'ملغي'
    
    number = models.CharField(max_length=50, unique=True, verbose_name="رقم الطلب")
    date = models.DateField(verbose_name="تاريخ الطلب")
    sales_rep = models.ForeignKey('sales.SalesRepresentative', on_delete=models.PROTECT, verbose_name="مندوب المبيعات")
    from_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='loading_orders_out', verbose_name="من مخزن (الرئيسي)")
    to_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='loading_orders_in', verbose_name="إلى مخزن (المندوب)")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, verbose_name="الحالة")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='requested_loadings', verbose_name="أنشئ بواسطة")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='approved_loadings', verbose_name="اعتمد بواسطة")
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الاعتماد")
    issued_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الصرف الفعلي")
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="قيد اليومية")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    def __str__(self):
        return f"{self.number} - {self.sales_rep.name}"

class LoadingOrderLine(models.Model):
    """سطر طلب تحميل"""
    loading_order = models.ForeignKey(LoadingOrder, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    requested_qty = models.DecimalField(max_digits=14, decimal_places=4)
    approved_qty = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    issued_qty = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    notes = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.item.name} ({self.requested_qty})"

class StockVoucher(models.Model):
    """أذون الصرف والإضافة المخزنية"""
    class VoucherType(models.TextChoices):
        RECEIPT = 'receipt', 'إذن إضافة'
        ISSUE = 'issue', 'إذن صرف'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        POSTED = 'posted', 'مرحّل'
        CANCELLED = 'cancelled', 'ملغي'

    number = models.CharField(max_length=50, unique=True, verbose_name="رقم الإذن")
    date = models.DateField(default=timezone.now, verbose_name="تاريخ الإذن")
    voucher_type = models.CharField(max_length=10, choices=VoucherType.choices, verbose_name="نوع الإذن")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, verbose_name="المخزن")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, verbose_name="الحالة")
    
    # Optional financial impact
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="قيد اليومية")
    offset_account = models.ForeignKey('core.Account', null=True, blank=True, on_delete=models.PROTECT, 
                                     verbose_name="الحساب المقابل",
                                     help_text="الحساب المقابل (مثل: حساب التلفيات، مصروفات العينات، إلخ)")
    
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="أنشئ بواسطة")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    def __str__(self):
        return f"{self.get_voucher_type_display()} - {self.number}"

class StockVoucherLine(models.Model):
    voucher = models.ForeignKey(StockVoucher, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, help_text="سيتم حسابه تلقائياً عند الترحيل إذا كان إذن صرف")
    total_cost = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    notes = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.item.name} - {self.quantity}"

