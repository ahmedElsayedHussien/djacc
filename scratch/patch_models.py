import re
import sys

def main():
    file_path = 'apps/purchases/models.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    # 1. Supplier payment_terms_days validation
    content = content.replace(
        'payment_terms_days = models.IntegerField(default=30, verbose_name="فترة السداد (أيام)")',
        'payment_terms_days = models.IntegerField(default=30, validators=[MinValueValidator(0)], verbose_name="فترة السداد (أيام)")'
    )

    # 2. PurchaseOrder clean() and auto-generation
    old_po = """    def __str__(self):
        return self.number"""
    
    new_po = """    def __str__(self):
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = DocumentService.generate_number(PurchaseOrder, 'PO')
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        if self.expected_delivery_date and self.date and self.expected_delivery_date < self.date:
            raise ValidationError({'expected_delivery_date': 'تاريخ الاستلام لا يمكن أن يسبق تاريخ الأمر'})"""
    
    content = content.replace(old_po, new_po)

    # 3. PurchaseInvoice fields validation
    fields_to_fix = [
        ('subtotal = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="الصافي")',
         'subtotal = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal(\'0.00\'))], verbose_name="الصافي")'),
        ('discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="إجمالي الخصم")',
         'discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(Decimal(\'0.00\'))], verbose_name="إجمالي الخصم")'),
        ('tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="إجمالي الضريبة")',
         'tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(Decimal(\'0.00\'))], verbose_name="إجمالي الضريبة")'),
        ('total = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="الإجمالي")',
         'total = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal(\'0.00\'))], verbose_name="الإجمالي")'),
        ('paid_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="المبلغ المدفوع")',
         'paid_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(Decimal(\'0.00\'))], verbose_name="المبلغ المدفوع")')
    ]
    for old, new in fields_to_fix:
        content = content.replace(old, new)

    # 4. PurchaseInvoice clean method fix
    old_pi_clean = """    def clean(self):
        if self.date and self.date > date.today():
            raise ValidationError({'date': 'تاريخ الفاتورة لا يمكن أن يكون في المستقبل'})
        if self.due_date and self.date and self.due_date < self.date:
            raise ValidationError({'due_date': 'تاريخ الاستحقاق يجب أن يكون بعد تاريخ الفاتورة'})
        if self.paid_amount > self.total:
            raise ValidationError({'paid_amount': 'المبلغ المدفوع لا يمكن أن يتجاوز إجمالي الفاتورة'})"""
    
    new_pi_clean = """    def clean(self):
        if self.date and self.date > date.today():
            raise ValidationError({'date': 'تاريخ الفاتورة لا يمكن أن يكون في المستقبل'})
        if self.due_date and self.date and self.due_date < self.date:
            raise ValidationError({'due_date': 'تاريخ الاستحقاق يجب أن يكون بعد تاريخ الفاتورة'})
        if self.paid_amount is not None and self.total is not None and self.paid_amount > self.total:
            raise ValidationError({'paid_amount': 'المبلغ المدفوع لا يمكن أن يتجاوز إجمالي الفاتورة'})
        if self.payment_type == self.PaymentType.CREDIT:
            self.cash_box = None
            self.bank_account = None"""
            
    content = content.replace(old_pi_clean, new_pi_clean)

    # 5. SupplierPayment amount validation and clean method
    content = content.replace(
        'amount = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="المبلغ")',
        'amount = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal(\'0.01\'))], verbose_name="المبلغ")'
    )
    
    old_sp = """        if not self.number:
            self.number = DocumentService.generate_number(SupplierPayment, 'PAY')
        self.full_clean()
        super().save(*args, **kwargs)"""
    
    new_sp = """        if not self.number:
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
            raise ValidationError({'cleared_at': 'يجب تحديد تاريخ الصرف الفعلي'})"""
            
    content = content.replace(old_sp, new_sp)

    # 6. PaymentAllocation amount validation and clean method
    content = content.replace(
        'amount = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="المبلغ المخصص")',
        'amount = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal(\'0.01\'))], verbose_name="المبلغ المخصص")'
    )
    
    old_pa = """    class Meta:
        verbose_name = "توزيع سداد\""""
        
    new_pa = """    def clean(self):
        if getattr(self, 'payment', None) and getattr(self, 'invoice', None):
            if self.payment.supplier != self.invoice.supplier:
                raise ValidationError("يجب أن تكون الفاتورة والسند لنفس المورد")
            if self.amount and self.amount > self.payment.amount:
                raise ValidationError({'amount': 'المبلغ المخصص لا يمكن أن يتجاوز مبلغ السند'})

    class Meta:
        verbose_name = "توزيع سداد\""""
    content = content.replace(old_pa, new_pa)

    # 7. PurchaseReturn financial validations and clean method
    fields_to_fix2 = [
        ('subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="الصافي")',
         'subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(Decimal(\'0.00\'))], verbose_name="الصافي")'),
        ('discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="إجمالي الخصم")',
         'discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(Decimal(\'0.00\'))], verbose_name="إجمالي الخصم")'),
        ('tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="إجمالي الضريبة")',
         'tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(Decimal(\'0.00\'))], verbose_name="إجمالي الضريبة")'),
        ('total = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="الإجمالي")',
         'total = models.DecimalField(max_digits=18, decimal_places=2, default=0, validators=[MinValueValidator(Decimal(\'0.00\'))], verbose_name="الإجمالي")')
    ]
    for old, new in fields_to_fix2:
        content = content.replace(old, new)
        
    old_pr = """        if not self.number:
            self.number = DocumentService.generate_number(PurchaseReturn, 'PRET')
        self.full_clean()
        super().save(*args, **kwargs)"""
        
    new_pr = """        if not self.number:
            self.number = DocumentService.generate_number(PurchaseReturn, 'PRET')
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        if self.invoice and self.supplier and self.invoice.supplier != self.supplier:
            raise ValidationError({'supplier': 'مورد المرتجع يجب أن يطابق مورد الفاتورة الأصلية'})
        if self.date and self.date > date.today():
            raise ValidationError({'date': 'تاريخ المرتجع لا يمكن أن يكون في المستقبل'})"""
            
    content = content.replace(old_pr, new_pr)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
    print("Models updated successfully.")

if __name__ == '__main__':
    main()
