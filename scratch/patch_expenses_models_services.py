import re

def main():
    # 1. models.py
    file_path = 'apps/expenses/models.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    # ExpenseCategory
    old_cat_acc = """    account = models.ForeignKey(
        'core.Account', 
        on_delete=models.PROTECT, 
        verbose_name="الحساب المحاسبي"
    )"""
    new_cat_acc = """    account = models.ForeignKey(
        'core.Account', 
        on_delete=models.PROTECT, 
        verbose_name="الحساب المحاسبي",
        limit_choices_to={'account_type': 'expense', 'is_active': True, 'is_leaf': True}
    )

    def clean(self):
        super().clean()
        if self.account_id:
            if getattr(self.account, 'account_type', '') != 'expense':
                raise ValidationError({'account': 'يجب اختيار حساب من نوع مصروفات'})
            if not getattr(self.account, 'is_leaf', False):
                raise ValidationError({'account': 'يجب اختيار حساب فرعي (Leaf)'})
            if not getattr(self.account, 'is_active', False):
                raise ValidationError({'account': 'الحساب غير نشط'})"""
    content = content.replace(old_cat_acc, new_cat_acc)

    # Expense clean
    old_exp_clean = """    def clean(self):
        if self.date and self.date > date.today():
            raise ValidationError({'date': 'تاريخ المصروف لا يمكن أن يكون في المستقبل'})"""
    new_exp_clean = """    def clean(self):
        super().clean()
        if self.date and self.date > date.today():
            raise ValidationError({'date': 'تاريخ المصروف لا يمكن أن يكون في المستقبل'})
            
        if self.subtotal + self.tax_amount != self.total:
            raise ValidationError("الإجمالي يجب أن يساوي مجموع المبلغ قبل الضريبة مع إجمالي الضريبة")
            
        if self.tax_type and self.tax_percent <= 0:
            raise ValidationError({'tax_percent': 'يجب إدخال نسبة ضريبة'})
        if not self.tax_type and (self.tax_percent > 0 or self.tax_amount > 0):
            raise ValidationError('لا يمكن إدخال ضريبة بدون تحديد نوعها')

        if self.payment_method == 'cash' and not self.cash_box_id:
            raise ValidationError({'cash_box': 'يجب تحديد الخزينة عند الدفع النقدي'})
        if self.payment_method == 'bank' and not self.bank_account_id:
            raise ValidationError({'bank_account': 'يجب تحديد الحساب البنكي'})
        if self.payment_method == 'custody' and not self.custody_id:
            raise ValidationError({'custody': 'يجب تحديد العهدة'})

        if self.pk and (self.status in [self.Status.POSTED, self.Status.APPROVED] or self.journal_entry_id):
            old = Expense.objects.filter(pk=self.pk).first()
            if old and (old.total != self.total or old.category_id != self.category_id or old.amount != self.amount):
                raise ValidationError("لا يمكن تعديل المبالغ أو التصنيف لمصروف معتمد أو مرحل")"""
    content = content.replace(old_exp_clean, new_exp_clean)

    # Custody clean
    old_cus_clean = """    def clean(self):
        if self.date and self.date > date.today():
            raise ValidationError({'date': 'تاريخ العهدة لا يمكن أن يكون في المستقبل'})
        if self.settled_amount > self.amount:
            raise ValidationError({'settled_amount': 'المبلغ المسوي لا يمكن أن يتجاوز قيمة العهدة'})"""
    new_cus_clean = """    def clean(self):
        super().clean()
        if self.date and self.date > date.today():
            raise ValidationError({'date': 'تاريخ العهدة لا يمكن أن يكون في المستقبل'})
            
        if self.account_id and (not getattr(self.account, 'is_leaf', False) or not self.account.is_active):
            raise ValidationError({'account': 'حساب العهدة يجب أن يكون فرعي (Leaf) ونشط'})

        if self.settled_amount > self.amount:
            raise ValidationError({'settled_amount': 'المبلغ المسوي لا يمكن أن يتجاوز قيمة العهدة'})
            
        if self.status == self.Status.SETTLED and self.settled_amount != self.amount:
            raise ValidationError({'status': 'العهدة المسواة بالكامل يجب أن يكون مبلغها المسوي مساوياً لقيمتها'})
            
        if self.pk and self.journal_entry_id:
            old = Custody.objects.filter(pk=self.pk).first()
            if old and (old.amount != self.amount or old.employee_id != self.employee_id):
                raise ValidationError("لا يمكن تعديل بيانات العهدة المالية بعد إنشاء القيد")"""
    content = content.replace(old_cus_clean, new_cus_clean)

    # CustodySettlement clean
    old_sett_clean = """    def clean(self):
        if self.date and self.date > date.today():
            raise ValidationError({'date': 'تاريخ التسوية لا يمكن أن يكون في المستقبل'})
        if self.custody_id and self.expenses_amount + self.returned_amount > self.custody.amount:
            raise ValidationError('إجمالي المصاريف + المبلغ المرتجع لا يمكن أن يتجاوز قيمة العهدة الأصلية')"""
    new_sett_clean = """    def clean(self):
        super().clean()
        if self.date and self.date > date.today():
            raise ValidationError({'date': 'تاريخ التسوية لا يمكن أن يكون في المستقبل'})
            
        if self.returned_amount > 0 and not self.cash_box_id:
            raise ValidationError({'cash_box': 'يجب تحديد الخزينة المودع بها عند وجود مبلغ مرتجع'})

        if self.custody_id:
            from django.db.models import Sum, F
            from decimal import Decimal
            other_settlements = self.custody.settlements.exclude(pk=self.pk) if self.pk else self.custody.settlements.all()
            total_settled_so_far = other_settlements.aggregate(
                total=Sum(F('expenses_amount') + F('returned_amount'))
            )['total'] or Decimal('0')
            
            current_total = self.expenses_amount + self.returned_amount
            
            if total_settled_so_far + current_total > self.custody.amount:
                raise ValidationError(
                    f'إجمالي التسويات (الحالية والسابقة) '
                    f'يتجاوز قيمة العهدة الأصلية ({self.custody.amount})'
                )"""
    content = content.replace(old_sett_clean, new_sett_clean)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Models patched.")

    # 2. services.py
    file_path = 'apps/expenses/services.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    # ExpenseService.post_expense
    old_post_exp = """        # Note: expense.amount should already be the net paid amount from the view"""
    new_post_exp = """        net_paid = (subtotal + capitalized_tax + 
                    sum(t['debit'] for t in tax_entries) - 
                    sum(t['credit'] for t in tax_entries))

        if expense.amount != net_paid:
            raise ValueError(f"قيمة السداد ({expense.amount}) لا تتطابق مع صافي المصروف بعد الضرائب ({net_paid})")"""
    content = content.replace(old_post_exp, new_post_exp)

    # ExpenseService.reverse_expense
    old_rev_exp = """    def reverse_expense(expense: Expense, reversed_by) -> JournalEntry:
        if not expense.journal_entry:
            raise ValueError("لا يوجد قيد مالي لعكسه")"""
    new_rev_exp = """    def reverse_expense(expense: Expense, reversed_by) -> JournalEntry:
        if expense.settlement_id:
            raise ValueError("لا يمكن عكس مصروف مرتبط بتسوية عهدة. قم بإلغاء/عكس التسوية أولاً")
        if not expense.journal_entry:
            raise ValueError("لا يوجد قيد مالي لعكسه")"""
    content = content.replace(old_rev_exp, new_rev_exp)

    # CustodyService.issue_custody
    old_iss_cus = """    @staticmethod
    @transaction.atomic
    def issue_custody(custody: Custody, created_by) -> JournalEntry:
        # Credit cash/bank
        credit_account = None"""
    new_iss_cus = """    @staticmethod
    @transaction.atomic
    def issue_custody(custody: Custody, created_by) -> JournalEntry:
        custody = Custody.objects.select_for_update().get(pk=custody.pk)
        if custody.journal_entry:
            raise ValueError("تم صرف هذه العهدة وإصدار قيد لها بالفعل")
        # Credit cash/bank
        credit_account = None"""
    content = content.replace(old_iss_cus, new_iss_cus)

    # CustodyService.settle_custody returned cash box validation
    old_sett_cash = """        # If there is a returned amount to a cash box
        if settlement.returned_amount > 0:
            lines.append({
                'account': settlement.cash_box.account,"""
    new_sett_cash = """        # If there is a returned amount to a cash box
        if settlement.returned_amount > 0:
            if not settlement.cash_box:
                raise ValueError("يجب تحديد الخزينة لاستلام النقدية المتبقية (المرتجعة) من العهدة")
            lines.append({
                'account': settlement.cash_box.account,"""
    content = content.replace(old_sett_cash, new_sett_cash)

    # CustodyService.settle_custody total expenses calculation
    old_tot_exp = """        total_expenses_all = custody.expense_set.filter(settlement__isnull=False).aggregate(t=Sum('amount'))['t'] or 0"""
    new_tot_exp = """        total_expenses_all = custody.expense_set.filter(settlement__is_posted=True).aggregate(t=Sum('amount'))['t'] or 0"""
    content = content.replace(old_tot_exp, new_tot_exp)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Services patched.")

if __name__ == '__main__':
    main()
