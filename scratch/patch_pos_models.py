import re

def main():
    file_path = 'apps/pos/models.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    # Add missing imports
    if 'from django.db.models import UniqueConstraint, Q' not in content:
        content = content.replace("from django.db import models", "from django.db import models\nfrom django.db.models import UniqueConstraint, Q")

    # POSSession Meta & clean
    old_session_meta = """    class Meta:
        verbose_name = "وردية نقطة بيع"
        verbose_name_plural = "ورديات نقاط البيع"

    def __str__(self):"""
    new_session_meta = """    class Meta:
        verbose_name = "وردية نقطة بيع"
        verbose_name_plural = "ورديات نقاط البيع"
        constraints = [
            UniqueConstraint(
                fields=['station'], 
                condition=Q(status='open'), 
                name='unique_open_station_session'
            ),
            UniqueConstraint(
                fields=['user'], 
                condition=Q(status='open'), 
                name='unique_open_user_session'
            )
        ]

    def __str__(self):"""
    content = content.replace(old_session_meta, new_session_meta)
    
    old_session_clean = """    def clean(self):
        if self.end_time and self.start_time and self.end_time < self.start_time:
            raise ValidationError({'end_time': 'وقت النهاية لا يمكن أن يكون قبل وقت البداية'})"""
    new_session_clean = """    def clean(self):
        if self.end_time and self.start_time and self.end_time < self.start_time:
            raise ValidationError({'end_time': 'وقت النهاية لا يمكن أن يكون قبل وقت البداية'})
        if self.status in [self.Status.CLOSED, self.Status.POSTED]:
            expected_diff = (self.actual_cash or Decimal('0')) - (self.expected_cash or Decimal('0'))
            if self.difference != expected_diff:
                raise ValidationError({'difference': 'قيمة العجز/الزيادة غير صحيحة ويجب أن تطابق الفعلي ناقص المتوقع.'})"""
    content = content.replace(old_session_clean, new_session_clean)

    # POSOrder clean
    old_order_clean = """    def clean(self):
        if self.discount > self.subtotal:
            raise ValidationError({'discount': 'الخصم لا يمكن أن يتجاوز الإجمالي قبل الخصم'})"""
    new_order_clean = """    def clean(self):
        if self.session.status != POSSession.Status.OPEN:
            raise ValidationError("لا يمكن إنشاء أو تعديل طلب في وردية مغلقة.")
        if self.discount > self.subtotal:
            raise ValidationError({'discount': 'الخصم لا يمكن أن يتجاوز الإجمالي قبل الخصم'})
        expected_grand_total = (self.subtotal or Decimal('0')) - (self.discount or Decimal('0')) + (self.tax or Decimal('0'))
        if round(self.grand_total, 2) != round(expected_grand_total, 2):
            raise ValidationError({'grand_total': 'الصافي المطلوب غير صحيح أو تم التلاعب به.'})"""
    content = content.replace(old_order_clean, new_order_clean)

    # POSOrderLine clean
    old_line_clean = """    def clean(self):
        if self.price < 0:
            raise ValidationError({'price': 'سعر الوحدة لا يمكن أن يكون سالباً'})"""
    new_line_clean = """    def clean(self):
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
            raise ValidationError({'total': 'إجمالي السطر غير صحيح أو تم التلاعب به.'})"""
    content = content.replace(old_line_clean, new_line_clean)

    # POSPayment amount and clean
    old_payment_amount = """    amount = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="المبلغ المدفوع")"""
    new_payment_amount = """    amount = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="المبلغ المدفوع", validators=[MinValueValidator(Decimal('0.01'))])"""
    content = content.replace(old_payment_amount, new_payment_amount)

    old_payment_clean = """    def clean(self):
        if self.method in ('card', 'wallet') and not self.reference:
            raise ValidationError({'reference': 'يجب إدخال رقم العملية لطرق الدفع الإلكترونية'})"""
    new_payment_clean = """    def clean(self):
        if self.order.status not in [POSOrder.Status.DRAFT, POSOrder.Status.PAID]:
            raise ValidationError("الطلب غير متاح لإضافة مدفوعات.")
        if self.method in ('card', 'wallet') and not self.reference:
            raise ValidationError({'reference': 'يجب إدخال رقم العملية لطرق الدفع الإلكترونية'})
        station = self.order.session.station
        if self.method == self.PaymentMethod.CARD and not station.bank_account:
            raise ValidationError({'method': 'نقطة البيع غير مرتبطة بحساب بنكي.'})
        if self.method == self.PaymentMethod.WALLET and not station.mobile_wallet:
            raise ValidationError({'method': 'نقطة البيع غير مرتبطة بمحفظة إلكترونية.'})"""
    content = content.replace(old_payment_clean, new_payment_clean)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Models patched.")

if __name__ == '__main__':
    main()
