import re

with open('apps/sales/models.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. ReceiptAllocation clean
content = content.replace(
"""    def clean(self):
        if self.invoice and self.receipt and self.invoice.customer_id != self.receipt.customer_id:
            raise ValidationError('الفاتورة لا تنتمي لنفس عميل سند التحصيل')""",
"""    def clean(self):
        if self.invoice and self.receipt and self.invoice.customer_id != self.receipt.customer_id:
            raise ValidationError('الفاتورة لا تنتمي لنفس عميل سند التحصيل')
        if self.amount <= 0:
            raise ValidationError({'amount': 'مبلغ التوزيع يجب أن يكون أكبر من صفر'})
        if self.invoice and self.amount > self.invoice.total:
            raise ValidationError({'amount': 'مبلغ التوزيع لا يمكن أن يتجاوز إجمالي الفاتورة'})"""
)

# 2. SalesReturnLine clean
content = content.replace(
"""    class Meta:
        verbose_name = "صنف في مرتجع"
        verbose_name_plural = "أصناف المرتجعات"
""",
"""    class Meta:
        verbose_name = "صنف في مرتجع"
        verbose_name_plural = "أصناف المرتجعات"

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError({'quantity': 'الكمية يجب أن تكون أكبر من صفر'})
        if self.unit_price < 0:
            raise ValidationError({'unit_price': 'سعر الوحدة لا يمكن أن يكون سالباً'})
        if hasattr(self, 'sales_return') and self.sales_return and self.sales_return.invoice:
            original_line = self.sales_return.invoice.lines.filter(item=self.item).first()
            if not original_line:
                raise ValidationError({'item': 'هذا الصنف غير موجود في الفاتورة الأصلية'})
            if self.quantity > original_line.quantity:
                raise ValidationError({'quantity': 'كمية المرتجع لا يمكن أن تتجاوز الكمية في الفاتورة الأصلية'})
"""
)

# 3. SalesInvoiceLine clean
content = content.replace(
"""    class Meta:
        verbose_name = "صنف في فاتورة مبيعات"
        verbose_name_plural = "أصناف فواتير المبيعات"
""",
"""    class Meta:
        verbose_name = "صنف في فاتورة مبيعات"
        verbose_name_plural = "أصناف فواتير المبيعات"

    def clean(self):
        if self.discount_percent + self.extra_discount_percent > 100:
            raise ValidationError('إجمالي نسبة الخصم لا يمكن أن يتجاوز 100%')
"""
)

with open('apps/sales/models.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done models!")
