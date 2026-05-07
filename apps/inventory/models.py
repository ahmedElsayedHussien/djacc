from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from decimal import Decimal
from django.conf import settings
from django.utils import timezone

class ItemCategory(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT)

    def __str__(self):
        return self.name

class UnitOfMeasure(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name

class Item(models.Model):

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=300)
    category = models.ForeignKey(ItemCategory, on_delete=models.PROTECT)
    
    # Unit Management
    base_unit = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, related_name='items_as_base', verbose_name='الوحدة الأساسية (أصغر وحدة)')
    purchase_unit = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, related_name='items_as_purchase', null=True, blank=True)
    sales_unit = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, related_name='items_as_sales', null=True, blank=True)
    
    # Factor: 1 Box = X Pieces. Example: base=Piece, sales=Box, factor=12.
    conversion_factor = models.DecimalField(max_digits=10, decimal_places=4, default=1, help_text="كم وحدة أساسية توجد في وحدة المبيعات؟")
    purchase_conversion_factor = models.DecimalField(max_digits=10, decimal_places=4, default=1, help_text="كم وحدة أساسية توجد في وحدة المشتريات؟")

    inventory_account = models.ForeignKey('core.Account', on_delete=models.PROTECT, related_name='inventory_items')
    cogs_account = models.ForeignKey('core.Account', on_delete=models.PROTECT, related_name='cogs_items')
    sales_account = models.ForeignKey('core.Account', on_delete=models.PROTECT, related_name='sales_items', null=True, blank=True)
    minimum_stock = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    barcode = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} - {self.name}"
    
    def convert_to_base(self, quantity, unit):
        """Converts a quantity in a specific unit to the base unit."""
        if unit == self.base_unit:
            return quantity
        if unit == self.sales_unit:
            return quantity * self.conversion_factor
        if unit == self.purchase_unit:
            return quantity * self.purchase_conversion_factor
        return quantity # Fallback

class Warehouse(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    gl_account = models.ForeignKey('core.Account', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="حساب المخزون (أستاذ عام)")
    location = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

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
        return self.total_value / self.quantity_on_hand

class WarehouseTransfer(models.Model):
    """تحويل مخزني بين المستودعات"""
    number = models.CharField(max_length=50, unique=True)
    date = models.DateField()
    from_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='transfers_out')
    to_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='transfers_in')
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    status = models.CharField(max_length=20, choices=[('draft', 'مسودة'), ('posted', 'مرحّل')], default='draft')
    notes = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.number} - {self.item.name}"

class LoadingOrder(models.Model):
    """طلب تحميل من المخزن الرئيسي لمخزن المندوب"""
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        PENDING = 'pending', 'في انتظار الاعتماد'
        APPROVED = 'approved', 'معتمد'
        ISSUED = 'issued', 'تم الصرف'
        CANCELLED = 'cancelled', 'ملغي'
    
    number = models.CharField(max_length=50, unique=True)
    date = models.DateField()
    sales_rep = models.ForeignKey('sales.SalesRepresentative', on_delete=models.PROTECT)
    from_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='loading_orders_out')
    to_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='loading_orders_in')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='requested_loadings')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='approved_loadings')
    approved_at = models.DateTimeField(null=True, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="قيد اليومية")
    notes = models.TextField(blank=True)

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

    number = models.CharField(max_length=50, unique=True)
    date = models.DateField(default=timezone.now)
    voucher_type = models.CharField(max_length=10, choices=VoucherType.choices)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    
    # Optional financial impact
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL)
    offset_account = models.ForeignKey('core.Account', null=True, blank=True, on_delete=models.PROTECT, 
                                     help_text="الحساب المقابل (مثل: حساب التلفيات، مصروفات العينات، إلخ)")
    
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_voucher_type_display()} - {self.number}"

class StockVoucherLine(models.Model):
    voucher = models.ForeignKey(StockVoucher, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=2, help_text="سيتم حسابه تلقائياً عند الترحيل إذا كان إذن صرف")
    total_cost = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    notes = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.item.name} - {self.quantity}"

