import re

def main():
    file_path = 'apps/purchases/forms.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    # 1. BasePurchaseLineFormSet for at least one item
    old_imports = "from .models import ("
    new_imports = """from django.forms.models import BaseInlineFormSet\nfrom .models import ("""
    content = content.replace(old_imports, new_imports)
    
    base_formset_code = """
class BasePurchaseLineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        valid_forms = [f for f in self.forms if not self.can_delete or not f.cleaned_data.get('DELETE')]
        if not valid_forms:
            raise forms.ValidationError("يجب إضافة صنف واحد على الأقل.")
"""
    # Find the place to insert BasePurchaseLineFormSet (before PurchaseInvoiceLineFormSet)
    content = content.replace('PurchaseInvoiceLineFormSet = inlineformset_factory(', base_formset_code + '\nPurchaseInvoiceLineFormSet = inlineformset_factory(')
    
    # 2. Add BasePurchaseLineFormSet to factories
    content = content.replace(
        'PurchaseInvoiceLineFormSet = inlineformset_factory(\n    PurchaseInvoice, PurchaseInvoiceLine, form=PurchaseInvoiceLineForm,\n    extra=1, can_delete=True\n)',
        'PurchaseInvoiceLineFormSet = inlineformset_factory(\n    PurchaseInvoice, PurchaseInvoiceLine, form=PurchaseInvoiceLineForm,\n    formset=BasePurchaseLineFormSet, extra=1, can_delete=True\n)'
    )
    content = content.replace(
        'PurchaseReturnLineFormSet = inlineformset_factory(\n    PurchaseReturn, PurchaseReturnLine, form=PurchaseReturnLineForm,\n    extra=1, can_delete=True\n)',
        'PurchaseReturnLineFormSet = inlineformset_factory(\n    PurchaseReturn, PurchaseReturnLine, form=PurchaseReturnLineForm,\n    formset=BasePurchaseLineFormSet, extra=1, can_delete=True\n)'
    )

    # 3. Add validations to fields in SupplierForm, PurchaseInvoiceLineForm, PurchaseReturnLineForm
    content = content.replace(
        'initial_balance = forms.DecimalField(',
        'initial_balance = forms.DecimalField(min_value=0, '
    )
    content = content.replace(
        'unit_cost = forms.DecimalField(',
        'unit_cost = forms.DecimalField(min_value=0, '
    )
    content = content.replace(
        'discount_percent = forms.DecimalField(',
        'discount_percent = forms.DecimalField(min_value=0, max_value=100, '
    )
    content = content.replace(
        'tax_percent = forms.DecimalField(',
        'tax_percent = forms.DecimalField(min_value=0, max_value=100, '
    )

    # 4. Bank account is_active=True filter in PurchaseInvoiceForm and SupplierPaymentForm
    # And CostCenter is_leaf=True in PurchaseReturnForm
    old_pi_init = """        if 'bank_account' in self.fields:
            self.fields['bank_account'].required = False"""
    new_pi_init = """        if 'bank_account' in self.fields:
            self.fields['bank_account'].required = False
            from apps.treasury.models import BankAccount
            self.fields['bank_account'].queryset = BankAccount.objects.filter(is_active=True)"""
    content = content.replace(old_pi_init, new_pi_init)

    old_sp_init = """        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'"""
    new_sp_init = """        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
        if 'bank_account' in self.fields:
            from apps.treasury.models import BankAccount
            self.fields['bank_account'].queryset = BankAccount.objects.filter(is_active=True)"""
    content = content.replace(old_sp_init, new_sp_init)
    
    # 5. PurchaseReturnForm Add __init__ and clean logic
    old_pr_class = """class PurchaseReturnForm(forms.ModelForm):
    class Meta:
        model = PurchaseReturn"""
    new_pr_class = """class PurchaseReturnForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
        if 'cost_center' in self.fields:
            from apps.core.models import CostCenter
            self.fields['cost_center'].queryset = CostCenter.objects.filter(is_active=True, is_leaf=True)
            
    class Meta:
        model = PurchaseReturn"""
    content = content.replace(old_pr_class, new_pr_class)
    
    old_pr_clean = """    def clean(self):
        cleaned = super().clean()
        invoice = cleaned.get('invoice')
        supplier = cleaned.get('supplier')
        
        if invoice and supplier and invoice.supplier != supplier:
            self.add_error('supplier', 'المورد يجب أن يطابق مورد الفاتورة')
            
        return cleaned"""
    new_pr_clean = """    def clean(self):
        cleaned = super().clean()
        invoice = cleaned.get('invoice')
        supplier = cleaned.get('supplier')
        date_val = cleaned.get('date')
        
        if invoice and supplier and invoice.supplier != supplier:
            self.add_error('supplier', 'المورد يجب أن يطابق مورد الفاتورة')
            
        if date_val and invoice and date_val < invoice.date:
            raise forms.ValidationError('تاريخ المرتجع لا يمكن أن يسبق تاريخ الفاتورة الأصلية')
            
        return cleaned"""
    content = content.replace(old_pr_clean, new_pr_clean)
    
    # 6. SupplierPaymentForm clean method fix
    # Because of the size of the clean method, it's safer to just rewrite the whole method via regex or replace block.
    # I'll just use a direct replace if it matches exactly.
    old_sp_clean = """    def clean(self):
        cleaned = super().clean()
        method = cleaned.get('payment_method')
        
        if method == 'cheque':
            if not cleaned.get('cheque_number'):
                self.add_error('cheque_number', 'يجب إدخال رقم الشيك')
            if not cleaned.get('cheque_due_date'):
                self.add_error('cheque_due_date', 'يجب إدخال تاريخ استحقاق الشيك')

        amount = cleaned.get('amount')
        supplier = cleaned.get('supplier')
        
        # Validate that the payment amount doesn't exceed the total unpaid invoices for this supplier
        if supplier and amount:
            invoices = PurchaseInvoice.objects.filter(
                supplier=supplier, 
                status=PurchaseInvoice.Status.POSTED
            )
            remaining_total = sum(inv.total - inv.paid_amount for inv in invoices)
            
            if amount > remaining_total:
                self.add_error('amount', f'المبلغ أكبر من إجمالي المديونية للمورد ({remaining_total})')
                
        return cleaned"""
        
    new_sp_clean = """    def clean(self):
        cleaned = super().clean()
        method = cleaned.get('payment_method')
        
        if method == 'cheque':
            if not cleaned.get('cheque_number'):
                self.add_error('cheque_number', 'يجب إدخال رقم الشيك')
            if not cleaned.get('cheque_due_date'):
                self.add_error('cheque_due_date', 'يجب إدخال تاريخ استحقاق الشيك')
        elif method == 'cash' and not cleaned.get('cash_box'):
            self.add_error('cash_box', 'يجب اختيار الخزنة')
        elif method == 'bank' and not cleaned.get('bank_account'):
            self.add_error('bank_account', 'يجب اختيار الحساب البنكي')

        amount = cleaned.get('amount')
        supplier = cleaned.get('supplier')
        
        # Validate that the payment amount doesn't exceed the total unpaid invoices for this supplier
        if supplier and amount:
            invoices = PurchaseInvoice.objects.filter(
                supplier=supplier, 
                status=PurchaseInvoice.Status.POSTED
            )
            remaining_total = sum(inv.total - inv.paid_amount for inv in invoices)
            if self.instance and self.instance.pk:
                remaining_total += self.instance.amount
            
            if amount > remaining_total:
                self.add_error('amount', f'المبلغ أكبر من إجمالي المديونية للمورد ({remaining_total})')
                
        return cleaned"""
    content = content.replace(old_sp_clean, new_sp_clean)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
    print("Forms updated successfully.")

if __name__ == '__main__':
    main()
