import re

def main():
    # 1. views.py
    file_path = 'apps/expenses/views.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    # ExpensePostView
    old_post_exp = """    def post(self, request, pk):
        try:
            with transaction.atomic():
                expense = get_object_or_404(Expense.objects.select_for_update(), pk=pk)
                ExpenseService.post_expense(expense, request.user)"""
    new_post_exp = """    def post(self, request, pk):
        try:
            with transaction.atomic():
                expense = get_object_or_404(Expense, pk=pk)
                ExpenseService.post_expense(expense, request.user)"""
    content = content.replace(old_post_exp, new_post_exp)

    # CustodySettlementCreateView get_context_data
    old_sett_ctx = """        if hasattr(self, 'custody_obj'):
            custody = self.custody_obj
            expenses = custody.expense_set.filter(status=Expense.Status.POSTED).select_related('category', 'cost_center')"""
    new_sett_ctx = """        if hasattr(self, 'custody_obj'):
            custody = self.custody_obj
            expenses = custody.expense_set.filter(
                status=Expense.Status.POSTED, 
                settlement__isnull=True
            ).select_related('category', 'cost_center')"""
    content = content.replace(old_sett_ctx, new_sett_ctx)

    # CustodyCreateView form_valid
    old_cus_fv = """    def form_valid(self, form):
        with transaction.atomic():
            form.instance.created_by = self.request.user
            self.object = form.save()
            CustodyService.issue_custody(self.object, self.request.user)
            messages.success(self.request, 'تم إنشاء وصرف العهدة بنجاح')
            return redirect('expenses:custody-detail', pk=self.object.pk)"""
    new_cus_fv = """    def form_valid(self, form):
        try:
            with transaction.atomic():
                form.instance.created_by = self.request.user
                self.object = form.save()
                CustodyService.issue_custody(self.object, self.request.user)
                messages.success(self.request, 'تم إنشاء وصرف العهدة بنجاح')
                return redirect('expenses:custody-detail', pk=self.object.pk)
        except Exception as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)"""
    content = content.replace(old_cus_fv, new_cus_fv)

    # CustodySettlementCreateView dispatch
    old_sett_dsp = """    def dispatch(self, request, *args, **kwargs):
        self.custody_obj = get_object_or_404(Custody, pk=self.kwargs.get('custody_id'))
        return super().dispatch(request, *args, **kwargs)"""
    new_sett_dsp = """    def dispatch(self, request, *args, **kwargs):
        self.custody_obj = get_object_or_404(Custody, pk=self.kwargs.get('custody_id'))
        if self.custody_obj.status == Custody.Status.SETTLED:
            messages.warning(request, "العهدة مسواة بالكامل ولا يمكن إنشاء تسوية جديدة.")
            return redirect('expenses:custody-detail', pk=self.custody_obj.pk)
        return super().dispatch(request, *args, **kwargs)"""
    content = content.replace(old_sett_dsp, new_sett_dsp)

    # CustodySettlementCreateView form_valid
    old_sett_fv = """    def form_valid(self, form):
        with transaction.atomic():
            custody = self.custody_obj
            form.instance.custody = custody
            form.instance.created_by = self.request.user
            
            self.object = form.save()
            
            # Post the settlement
            CustodyService.settle_custody(self.object, self.request.user)
            
            messages.success(self.request, 'تمت تسوية العهدة بنجاح')
            return redirect('expenses:custody-detail', pk=custody.pk)"""
    new_sett_fv = """    def form_valid(self, form):
        try:
            with transaction.atomic():
                custody = self.custody_obj
                form.instance.custody = custody
                form.instance.created_by = self.request.user
                
                self.object = form.save()
                
                # Post the settlement
                CustodyService.settle_custody(self.object, self.request.user)
                
                messages.success(self.request, 'تمت تسوية العهدة بنجاح')
                return redirect('expenses:custody-detail', pk=custody.pk)
        except Exception as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)"""
    content = content.replace(old_sett_fv, new_sett_fv)

    # ExpenseReverseView post
    old_rev_post = """    def post(self, request, pk):
        try:
            with transaction.atomic():
                expense = get_object_or_404(Expense.objects.select_for_update(), pk=pk)
                ExpenseService.reverse_expense(expense, request.user)"""
    new_rev_post = """    def post(self, request, pk):
        expense = get_object_or_404(Expense, pk=pk)
        if expense.status != Expense.Status.POSTED:
            messages.warning(request, "لا يمكن عكس المصروف إلا إذا كان مرحلاً")
            return redirect('expenses:expense-detail', pk=pk)
        try:
            with transaction.atomic():
                expense = Expense.objects.select_for_update().get(pk=pk)
                ExpenseService.reverse_expense(expense, request.user)"""
    content = content.replace(old_rev_post, new_rev_post)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Views patched.")


    # 2. forms.py
    file_path = 'apps/expenses/forms.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    # Add django.utils.timezone import
    if "from django.utils.timezone import localdate" not in content:
        content = content.replace("from datetime import date", "from datetime import date\nfrom django.utils.timezone import localdate")
    # replace date.today() with localdate()
    content = content.replace("date.today()", "localdate()")

    # ExpenseForm.__init__
    old_exp_init = """        if 'cost_center' in self.fields:
            self.fields['cost_center'].queryset = CostCenter.objects.filter(is_active=True, is_leaf=True).order_by('code')
            
        if 'cash_box' in self.fields and user:"""
    new_exp_init = """        if 'cost_center' in self.fields:
            self.fields['cost_center'].queryset = CostCenter.objects.filter(is_active=True, is_leaf=True).order_by('code')
            
        if 'bank_account' in self.fields:
            self.fields['bank_account'].queryset = self.fields['bank_account'].queryset.filter(is_active=True)
            
        if 'tax_type' in self.fields:
            self.fields['tax_type'].queryset = self.fields['tax_type'].queryset.filter(is_active=True)
            
        if 'tax_type2' in self.fields:
            self.fields['tax_type2'].queryset = self.fields['tax_type2'].queryset.filter(is_active=True)
            
        if 'custody' in self.fields:
            self.fields['custody'].queryset = self.fields['custody'].queryset.filter(
                status__in=[Custody.Status.OPEN, Custody.Status.PARTIALLY_SETTLED]
            )
            
        if 'cash_box' in self.fields and user:"""
    content = content.replace(old_exp_init, new_exp_init)

    # ExpenseForm.clean
    old_exp_clean_form = """    def clean(self):
        cleaned = super().clean()
        method = cleaned.get('payment_method')
        
        if method == 'bank' and not cleaned.get('bank_account'):
            self.add_error('bank_account', 'يجب تحديد الحساب البنكي عند الدفع بالبنك')
        elif method == 'cash' and not cleaned.get('cash_box'):
            self.add_error('cash_box', 'يجب تحديد الخزنة عند الدفع نقداً')
        elif method == 'custody' and not cleaned.get('custody'):
            self.add_error('custody', 'يجب تحديد العهدة')
            
        return cleaned"""
    new_exp_clean_form = """    def clean(self):
        from django import forms
        cleaned = super().clean()
        method = cleaned.get('payment_method')
        
        if method == 'bank':
            if not cleaned.get('bank_account'):
                self.add_error('bank_account', 'يجب تحديد الحساب البنكي عند الدفع بالبنك')
            cleaned['cash_box'] = None
            cleaned['custody'] = None
        elif method == 'cash':
            if not cleaned.get('cash_box'):
                self.add_error('cash_box', 'يجب تحديد الخزنة عند الدفع نقداً')
            cleaned['bank_account'] = None
            cleaned['custody'] = None
        elif method == 'custody':
            if not cleaned.get('custody'):
                self.add_error('custody', 'يجب تحديد العهدة')
            cleaned['cash_box'] = None
            cleaned['bank_account'] = None
            
        tax_type = cleaned.get('tax_type')
        tax_percent = cleaned.get('tax_percent') or 0
        if tax_type and tax_percent <= 0:
            self.add_error('tax_percent', 'يجب إدخال نسبة ضريبة صحيحة')
        if not tax_type and tax_percent > 0:
            self.add_error('tax_type', 'يجب اختيار نوع الضريبة')

        tax_type2 = cleaned.get('tax_type2')
        tax_percent2 = cleaned.get('tax_percent2') or 0
        if tax_type2 and tax_percent2 <= 0:
            self.add_error('tax_percent2', 'يجب إدخال نسبة ضريبة صحيحة')
        if not tax_type2 and tax_percent2 > 0:
            self.add_error('tax_type2', 'يجب اختيار نوع الضريبة')

        custody = cleaned.get('custody')
        subtotal = cleaned.get('subtotal') or 0
        
        if method == 'custody' and custody and subtotal > 0:
            from apps.core.tax_utils import calculate_line_taxes
            from django.db.models import Sum
            
            res = calculate_line_taxes(
                subtotal, tax_type, tax_percent, tax_type2, tax_percent2, is_purchase_or_expense=True
            )
            expense_total = subtotal + res['tax1_signed'] + res['tax2_signed']
            
            other_expenses = custody.expense_set.exclude(pk=self.instance.pk if self.instance else None)\\
                                    .exclude(status__in=['reversed', 'rejected'])\\
                                    .aggregate(t=Sum('amount'))['t'] or 0
            
            remaining_balance = custody.amount - custody.settled_amount - other_expenses
            
            if expense_total > remaining_balance:
                raise forms.ValidationError(
                    f'إجمالي المصروف المقدر ({expense_total}) أكبر من الرصيد المتاح للعهدة ({remaining_balance}).'
                )
            
        return cleaned"""
    content = content.replace(old_exp_clean_form, new_exp_clean_form)

    # CustodyForm.__init__
    old_cus_init = """        self.fields['account'].queryset = Account.objects.filter(
            code__startswith=custody_parent, is_leaf=True
        )"""
    new_cus_init = """        self.fields['account'].queryset = Account.objects.filter(
            code__startswith=custody_parent, is_leaf=True, is_active=True
        )"""
    content = content.replace(old_cus_init, new_cus_init)

    # CustodySettlementForm.clean
    old_sett_clean_form = """    def clean(self):
        cleaned = super().clean()
        
        return cleaned"""
    new_sett_clean_form = """    def clean(self):
        cleaned = super().clean()
        returned_amount = cleaned.get('returned_amount') or 0
        cash_box = cleaned.get('cash_box')
        
        if returned_amount > 0 and not cash_box:
            self.add_error('cash_box', 'يجب تحديد الخزنة لاستلام النقدية المرتجعة.')
        elif returned_amount == 0:
            cleaned['cash_box'] = None
            
        return cleaned"""
    content = content.replace(old_sett_clean_form, new_sett_clean_form)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Forms patched.")

if __name__ == '__main__':
    main()
