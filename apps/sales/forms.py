from django import forms
from django.forms import inlineformset_factory
from .models import (
    Customer, SalesInvoice, SalesInvoiceLine, CustomerReceipt, 
    SalesRepresentative, IntermediaryCompany, PriceList, PriceListItem,
    Quotation, QuotationLine, CustomerSector, SalesReturn, SalesReturnLine
)
from apps.inventory.models import Item, Warehouse

class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            'code', 'name', 'tax_number',
            'credit_limit', 'payment_terms_days',
            'address', 'phone', 'email', 'customer_type', 'price_list',
            'is_taxable', 'default_tax1', 'default_tax2'
        ]
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'tax_number': forms.TextInput(attrs={'class': 'form-control'}),
            'credit_limit': forms.NumberInput(attrs={'class': 'form-control'}),
            'payment_terms_days': forms.NumberInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'customer_type': forms.Select(attrs={'class': 'form-select'}),
            'price_list': forms.Select(attrs={'class': 'form-select'}),
            'is_taxable': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'default_tax1': forms.Select(attrs={'class': 'form-select'}),
            'default_tax2': forms.Select(attrs={'class': 'form-select'}),
        }

    initial_balance = forms.DecimalField(
        max_digits=18, decimal_places=2, required=False, initial=0,
        label='الرصيد الافتتاحي',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    initial_balance_type = forms.ChoiceField(
        choices=[('debit', 'مدين (عليه)'), ('credit', 'دائن (له)')],
        required=False, initial='debit',
        label='طبيعة الرصيد',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.account_id:
            self.fields['initial_balance'].initial = self.instance.account.initial_balance
            self.fields['initial_balance_type'].initial = self.instance.account.initial_balance_type

class SalesRepresentativeForm(forms.ModelForm):
    class Meta:
        model = SalesRepresentative
        fields = ['employee', 'code', 'commission_rate', 'territory', 'supervisor', 'is_active']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'كود المندوب'}),
            'commission_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'territory': forms.TextInput(attrs={'class': 'form-control'}),
            'supervisor': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.hr.models import Employee
        # Show only employees who don't have a sales profile yet, or the current one
        reps = SalesRepresentative.objects.exclude(employee__isnull=True)
        if self.instance and self.instance.pk and self.instance.employee:
            reps = reps.exclude(pk=self.instance.pk)
        
        assigned_emp_ids = reps.values_list('employee_id', flat=True)
        self.fields['employee'].queryset = Employee.objects.exclude(id__in=assigned_emp_ids)

class SalesInvoiceForm(forms.ModelForm):
    class Meta:
        model = SalesInvoice
        fields = ['date', 'customer', 'payment_type', 'sales_rep', 'cash_box', 'cost_center', 'due_date', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'payment_type': forms.Select(attrs={'class': 'form-select'}),
            'sales_rep': forms.Select(attrs={'class': 'form-select'}),
            'cash_box': forms.Select(attrs={'class': 'form-select'}),
            'cost_center': forms.Select(attrs={'class': 'form-select'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

class SalesInvoiceLineForm(forms.ModelForm):
    class Meta:
        model = SalesInvoiceLine
        fields = ['item', 'warehouse', 'unit', 'quantity', 'unit_price', 'discount_percent', 'tax_type', 'tax_percent', 'tax_type2', 'tax_percent2', 'total']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-select item-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'unit': forms.Select(attrs={'class': 'form-select unit-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control qty-input', 'step': 'any'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control price-input', 'step': 'any'}),
            'discount_percent': forms.NumberInput(attrs={'class': 'form-control discount-input', 'step': 'any'}),
            'tax_type': forms.Select(attrs={'class': 'form-select tax-select'}),
            'tax_percent': forms.HiddenInput(attrs={'class': 'tax-rate'}),
            'tax_type2': forms.Select(attrs={'class': 'form-select tax-select2'}),
            'tax_percent2': forms.HiddenInput(attrs={'class': 'tax-rate2'}),
            'total': forms.HiddenInput(attrs={'class': 'total-input'}),
        }

SalesInvoiceLineFormSet = inlineformset_factory(
    SalesInvoice, SalesInvoiceLine,
    form=SalesInvoiceLineForm,
    extra=1,
    can_delete=True
)

class CustomerReceiptForm(forms.ModelForm):
    class Meta:
        model = CustomerReceipt
        fields = [
            'date', 'customer', 'amount', 'payment_method', 
            'bank_account', 'cash_box', 'intermediary_company',
            'cheque_number', 'cheque_due_date', 'reference'
        ]
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'bank_account': forms.Select(attrs={'class': 'form-select'}),
            'cash_box': forms.Select(attrs={'class': 'form-select'}),
            'intermediary_company': forms.Select(attrs={'class': 'form-select'}),
            'cheque_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'رقم الشيك'}),
            'cheque_due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reference': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get('payment_method')
        
        if method == 'bank' and not cleaned.get('bank_account'):
            raise forms.ValidationError('يجب تحديد الحساب البنكي عند الدفع بالبنك')
        
        if method == 'intermediary' and not cleaned.get('intermediary_company'):
            raise forms.ValidationError('يجب تحديد الشركة الوسيطة')

        if method == 'cash' and not cleaned.get('cash_box'):
            raise forms.ValidationError('يجب تحديد الخزنة المستلمة')

        if method == 'cheque':
            if not cleaned.get('cheque_number'):
                raise forms.ValidationError('يجب إدخال رقم الشيك')
            if not cleaned.get('cheque_due_date'):
                raise forms.ValidationError('يجب إدخال تاريخ استحقاق الشيك')
                
        return cleaned



class QuotationForm(forms.ModelForm):
    class Meta:
        model = Quotation
        fields = ['name', 'customer', 'sector', 'sales_rep', 'start_date', 'end_date', 'status', 'is_active', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'sector': forms.Select(attrs={'class': 'form-select'}),
            'sales_rep': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

class QuotationLineForm(forms.ModelForm):
    class Meta:
        model = QuotationLine
        fields = ['item', 'unit', 'quantity', 'unit_price', 'discount_percent', 'extra_discount_percent', 'tax_type', 'total']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-select'}),
            'unit': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'discount_percent': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'extra_discount_percent': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'tax_type': forms.Select(attrs={'class': 'form-select'}),
            'total': forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
        }

class QuotationLineFormSet(forms.BaseInlineFormSet):
    pass

QuotationLineFormSet = inlineformset_factory(
    Quotation, QuotationLine,
    form=QuotationLineForm,
    extra=1,
    can_delete=True
)

class PriceListForm(forms.ModelForm):
    class Meta:
        model = PriceList
        fields = ['name', 'is_default', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class PriceListItemForm(forms.ModelForm):
    class Meta:
        model = PriceListItem
        fields = ['item', 'unit_price', 'min_qty']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-select'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'min_qty': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001'}),
        }

PriceListItemFormSet = inlineformset_factory(
    PriceList, PriceListItem,
    form=PriceListItemForm,
    extra=1,
    can_delete=True
)

class SalesReturnLineForm(forms.ModelForm):
    class Meta:
        model = SalesReturnLine
        fields = ['item', 'warehouse', 'unit', 'quantity', 'unit_price', 'discount_percent', 'tax_type', 'tax_percent', 'tax_type2', 'tax_percent2', 'total', 'return_account', 'cogs_account']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-select item-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'unit': forms.Select(attrs={'class': 'form-select unit-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control qty-input', 'step': 'any'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'discount_percent': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'tax_type': forms.Select(attrs={'class': 'form-select'}),
            'total': forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
            'return_account': forms.Select(attrs={'class': 'form-select'}),
            'cogs_account': forms.Select(attrs={'class': 'form-select'}),
        }

SalesReturnLineFormSet = inlineformset_factory(
    SalesReturn, SalesReturnLine,
    form=SalesReturnLineForm,
    extra=1,
    can_delete=True
)
