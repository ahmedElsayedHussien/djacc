import re

def main():
    file_path = 'apps/treasury/models.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    # 1. CashBox clean
    old_cashbox_clean = """    def clean(self):
        if self.account:
            if self.account.account_type != 'asset':
                raise ValidationError({'account': 'حساب الخزينة يجب أن يكون من الأصول'})
            if self.account.name != self.name:
                raise ValidationError({'account': 'اسم الحساب المحاسبي يجب أن يتطابق مع اسم الخزينة'})"""
    new_cashbox_clean = """    def clean(self):
        super().clean()
        if self.account:
            if not self.account.is_leaf:
                raise ValidationError({'account': 'يجب ربط الخزينة بحساب ورقي (Leaf Account) في الدليل المحاسبي'})
            if not self.account.is_active:
                raise ValidationError({'account': 'الحساب المحاسبي المختار غير نشط'})
            if self.account.account_type != 'asset':
                raise ValidationError({'account': 'حساب الخزينة يجب أن يكون من الأصول'})
            if self.account.name != self.name:
                raise ValidationError({'account': 'اسم الحساب المحاسبي يجب أن يتطابق مع اسم الخزينة'})"""
    content = content.replace(old_cashbox_clean, new_cashbox_clean)

    # 2. BankAccount clean
    old_bank_clean = """    def clean(self):
        if self.account:
            if self.account.account_type != 'asset':
                raise ValidationError({'account': 'حساب البنك يجب أن يكون من الأصول'})
            if self.account.name != self.name:
                raise ValidationError({'account': 'اسم الحساب المحاسبي يجب أن يتطابق مع اسم البنك'})"""
    new_bank_clean = """    def clean(self):
        super().clean()
        if self.account:
            if not self.account.is_leaf:
                raise ValidationError({'account': 'يجب ربط الحساب البنكي بحساب ورقي (Leaf Account) في الدليل المحاسبي'})
            if not self.account.is_active:
                raise ValidationError({'account': 'الحساب المحاسبي المختار غير نشط'})
            if self.account.account_type != 'asset':
                raise ValidationError({'account': 'حساب البنك يجب أن يكون من الأصول'})
            if self.account.name != self.name:
                raise ValidationError({'account': 'اسم الحساب المحاسبي يجب أن يتطابق مع اسم البنك'})"""
    content = content.replace(old_bank_clean, new_bank_clean)

    # 3. MobileWallet clean
    old_wallet_clean = """    def clean(self):
        if self.account:
            if self.account.account_type != 'asset':
                raise ValidationError({'account': 'حساب المحفظة يجب أن يكون من الأصول'})"""
    new_wallet_clean = """    def clean(self):
        super().clean()
        if self.account:
            if not self.account.is_leaf:
                raise ValidationError({'account': 'يجب ربط حساب المحفظة بحساب ورقي (Leaf Account) في الدليل المحاسبي'})
            if not self.account.is_active:
                raise ValidationError({'account': 'الحساب المحاسبي المختار غير نشط'})
            if self.account.account_type != 'asset':
                raise ValidationError({'account': 'حساب المحفظة يجب أن يكون من الأصول'})"""
    content = content.replace(old_wallet_clean, new_wallet_clean)

    # 4. BankTransaction clean
    old_banktrans_str = """    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.amount} - {self.bank_account.name}\""""
    new_banktrans_str = """    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.amount} - {self.bank_account.name}"
        
    def clean(self):
        super().clean()
        if self.date and self.date > date.today():
             raise ValidationError({'date': 'تاريخ العملية لا يمكن أن يكون في المستقبل'})
        
        if self.pk:
            old_instance = BankTransaction.objects.get(pk=self.pk)
            if old_instance.is_reconciled:
                raise ValidationError("لا يمكن تعديل أو حذف حركة بنكية تمت تسويتها.")"""
    content = content.replace(old_banktrans_str, new_banktrans_str)
    
    # Also override delete in BankTransaction to block deleting reconciled
    old_banktrans_meta = """    class Meta:
        verbose_name = "حركة بنكية"
        verbose_name_plural = "حركات بنكية\""""
    new_banktrans_meta = """    def delete(self, *args, **kwargs):
        if self.is_reconciled:
            raise ValidationError("لا يمكن حذف حركة بنكية تمت تسويتها.")
        super().delete(*args, **kwargs)

    class Meta:
        verbose_name = "حركة بنكية"
        verbose_name_plural = "حركات بنكية\""""
    content = content.replace(old_banktrans_meta, new_banktrans_meta)

    # 5. BankReconciliation MinValueValidator
    old_bal1 = "statement_balance = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(0)], verbose_name=\"الرصيد في الكشف\")"
    new_bal1 = "statement_balance = models.DecimalField(max_digits=18, decimal_places=2, verbose_name=\"الرصيد في الكشف\")"
    content = content.replace(old_bal1, new_bal1)
    
    old_bal2 = "book_balance = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(0)], verbose_name=\"الرصيد في الدفاتر\")"
    new_bal2 = "book_balance = models.DecimalField(max_digits=18, decimal_places=2, verbose_name=\"الرصيد في الدفاتر\")"
    content = content.replace(old_bal2, new_bal2)

    # 6. BankReconciliation clean TypeError
    old_rec_clean = """    def clean(self):
        super().clean()
        if self.statement_date and self.statement_date > date.today():
            raise ValidationError({'statement_date': 'تاريخ كشف الحساب لا يمكن أن يكون في المستقبل'})
        self.difference = self.statement_balance - self.book_balance"""
    new_rec_clean = """    def clean(self):
        super().clean()
        if self.statement_date and self.statement_date > date.today():
            raise ValidationError({'statement_date': 'تاريخ كشف الحساب لا يمكن أن يكون في المستقبل'})
        if self.statement_balance is not None and self.book_balance is not None:
            self.difference = self.statement_balance - self.book_balance"""
    content = content.replace(old_rec_clean, new_rec_clean)

    # 7. CashTransfer clean
    old_transfer_clean = """    def clean(self):
        super().clean()
        
        # Validation for source
        if not self.from_cash_box and not self.from_bank:
            raise ValidationError('يجب اختيار الخزينة أو البنك المحول منه')
        if self.from_cash_box and self.from_bank:
            raise ValidationError('لا يمكن التحويل من خزينة وبنك في نفس الوقت')
            
        # Validation for destination
        if not self.to_cash_box and not self.to_bank:
            raise ValidationError('يجب اختيار الخزينة أو البنك المحول إليه')
        if self.to_cash_box and self.to_bank:
            raise ValidationError('لا يمكن التحويل إلى خزينة وبنك في نفس الوقت')"""
            
    new_transfer_clean = """    def clean(self):
        super().clean()
        
        if self.pk:
            old_instance = CashTransfer.objects.filter(pk=self.pk).first()
            if old_instance and old_instance.status == self.Status.COMPLETED and self.status == self.Status.COMPLETED:
                if old_instance.amount != self.amount or old_instance.from_cash_box_id != self.from_cash_box_id or old_instance.to_cash_box_id != self.to_cash_box_id or old_instance.from_bank_id != self.from_bank_id or old_instance.to_bank_id != self.to_bank_id:
                    raise ValidationError("لا يمكن تعديل بيانات تحويل مالي بعد اكتماله.")
        
        # Validation for source
        if not self.from_cash_box and not self.from_bank:
            raise ValidationError('يجب اختيار الخزينة أو البنك المحول منه')
        if self.from_cash_box and self.from_bank:
            raise ValidationError('لا يمكن التحويل من خزينة وبنك في نفس الوقت')
            
        # Validation for destination
        if not self.to_cash_box and not self.to_bank:
            raise ValidationError('يجب اختيار الخزينة أو البنك المحول إليه')
        if self.to_cash_box and self.to_bank:
            raise ValidationError('لا يمكن التحويل إلى خزينة وبنك في نفس الوقت')
            
        source = self.from_cash_box.account if self.from_cash_box else (self.from_bank.account if self.from_bank else None)
        dest = self.to_cash_box.account if self.to_cash_box else (self.to_bank.account if self.to_bank else None)
        if source and not source.is_active:
            raise ValidationError("حساب المصدر غير نشط أو موقوف.")
        if dest and not dest.is_active:
            raise ValidationError("حساب الوجهة غير نشط أو موقوف.")
            
        source_currency = getattr(self.from_cash_box, 'currency', None) or getattr(self.from_bank, 'currency', None)
        dest_currency = getattr(self.to_cash_box, 'currency', None) or getattr(self.to_bank, 'currency', None)
        if source_currency and dest_currency and source_currency != dest_currency:
            raise ValidationError("لا يمكن التحويل بين حسابات بعملات مختلفة بدون تحديد سعر الصرف المزدوج. يجب أن تتطابق العملة.")"""
    content = content.replace(old_transfer_clean, new_transfer_clean)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
    print("Models patched.")

if __name__ == '__main__':
    main()
