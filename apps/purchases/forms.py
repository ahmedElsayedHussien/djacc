from django import forms
from django.forms import inlineformset_factory
from .models import Supplier, PurchaseInvoice, PurchaseInvoiceLine, SupplierPayment
from apps.inventory.models import Item, Warehouse

class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['name', 'tax_number', 'phone', 'email', 'payment_terms_days', 'address']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'tax_number': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'payment_terms_days': forms.NumberInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    initial_balance = forms.DecimalField(
        max_digits=18, decimal_places=2, required=False, initial=0,
        label='الرصيد الافتتاحي',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    initial_balance_type = forms.ChoiceField(
        choices=[('credit', 'دائن (له)'), ('debit', 'مدين (عليه)')],
        required=False, initial='credit',
        label='طبيعة الرصيد',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.account_id:
            self.fields['initial_balance'].initial = self.instance.account.initial_balance
            self.fields['initial_balance_type'].initial = self.instance.account.initial_balance_type

class PurchaseInvoiceForm(forms.ModelForm):
    number = forms.CharField(
        required=False,
        widget=forms.HiddenInput()
    )
    supplier_invoice_number = forms.CharField(
        required=False,
        widget=forms.HiddenInput()
    )
    class Meta:
        model = PurchaseInvoice
        fields = ['number', 'supplier_invoice_number', 'date', 'supplier', 'payment_type', 'payment_method', 'cash_box', 'bank_account', 'cost_center', 'due_date']
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'payment_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_payment_type'}),
            'payment_method': forms.Select(attrs={'class': 'form-select', 'id': 'id_payment_method'}),
            'cash_box': forms.Select(attrs={'class': 'form-select'}),
            'bank_account': forms.Select(attrs={'class': 'form-select'}),
            'cost_center': forms.Select(attrs={'class': 'form-select'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        payment_type = cleaned_data.get('payment_type')
        payment_method = cleaned_data.get('payment_method')
        cash_box = cleaned_data.get('cash_box')
        bank_account = cleaned_data.get('bank_account')

        if payment_type == 'cash':
            if payment_method == 'cash' and not cash_box:
                self.add_error('cash_box', 'يجب اختيار الخزنة للمشتريات النقدية')
            elif payment_method == 'bank' and not bank_account:
                self.add_error('bank_account', 'يجب اختيار الحساب البنكي للمشتريات عبر البنك')
        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.treasury.models import CashBox
        from apps.sales.models import SalesRepresentative
        
        # Exclude cash boxes assigned to sales representatives
        rep_cash_boxes = SalesRepresentative.objects.values_list('cash_box_id', flat=True)
        if 'cash_box' in self.fields:
            self.fields['cash_box'].queryset = CashBox.objects.filter(is_active=True).exclude(id__in=rep_cash_boxes)
        
        from apps.core.models import CostCenter
        if 'cost_center' in self.fields:
            self.fields['cost_center'].queryset = CostCenter.objects.filter(is_active=True, is_leaf=True).order_by('code')

class PurchaseInvoiceLineForm(forms.ModelForm):
    class Meta:
        model = PurchaseInvoiceLine
        fields = ['item', 'warehouse', 'unit', 'quantity', 'unit_cost', 'tax_type', 'tax_percent', 'tax_type2', 'tax_percent2']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-select item-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'unit': forms.Select(attrs={'class': 'form-select unit-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control qty-input', 'step': 'any'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-control price-input', 'step': 'any'}),
            'tax_type': forms.Select(attrs={'class': 'form-select tax-select'}),
            'tax_type2': forms.Select(attrs={'class': 'form-select tax-select2'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.inventory.models import Warehouse
        from apps.sales.models import SalesRepresentative
        
        # Exclude warehouses assigned to sales representatives
        rep_warehouses = SalesRepresentative.objects.values_list('warehouse_id', flat=True)
        if 'warehouse' in self.fields:
            self.fields['warehouse'].queryset = Warehouse.objects.filter(is_active=True).exclude(id__in=rep_warehouses)
        
        from apps.core.models import TaxType
        self.fields['tax_type'].queryset = TaxType.objects.filter(appear_in_invoices=True, is_active=True)
        self.fields['tax_type2'].queryset = TaxType.objects.filter(appear_in_invoices=True, is_active=True)

PurchaseInvoiceLineFormSet = inlineformset_factory(
    PurchaseInvoice, PurchaseInvoiceLine,
    form=PurchaseInvoiceLineForm,
    extra=1,
    can_delete=True
)


class SupplierPaymentForm(forms.ModelForm):
    number = forms.CharField(
        required=False,
        widget=forms.HiddenInput()
    )
    class Meta:
        model = SupplierPayment
        fields = ['number', 'date', 'supplier', 'amount', 'payment_method', 'bank_account', 'cash_box']
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'bank_account': forms.Select(attrs={'class': 'form-select'}),
            'cash_box': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.treasury.models import CashBox
        from apps.sales.models import SalesRepresentative
        rep_cash_boxes = SalesRepresentative.objects.values_list('cash_box_id', flat=True)
        if 'cash_box' in self.fields:
            self.fields['cash_box'].queryset = CashBox.objects.filter(is_active=True).exclude(id__in=rep_cash_boxes)

from .models import PurchaseReturn, PurchaseReturnLine

class PurchaseReturnForm(forms.ModelForm):
    number = forms.CharField(
        required=False,
        widget=forms.HiddenInput()
    )
    class Meta:
        model = PurchaseReturn
        fields = ['number', 'date', 'invoice', 'supplier', 'cost_center', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'invoice': forms.Select(attrs={'class': 'form-select'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

class PurchaseReturnLineForm(forms.ModelForm):
    class Meta:
        model = PurchaseReturnLine
        fields = ['item', 'warehouse', 'unit', 'quantity', 'unit_cost', 'tax_type', 'tax_percent', 'tax_type2', 'tax_percent2']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'unit': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'tax_type': forms.Select(attrs={'class': 'form-select'}),
            'tax_type2': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.inventory.models import Warehouse
        from apps.sales.models import SalesRepresentative
        rep_warehouses = SalesRepresentative.objects.values_list('warehouse_id', flat=True)
        if 'warehouse' in self.fields:
            self.fields['warehouse'].queryset = Warehouse.objects.filter(is_active=True).exclude(id__in=rep_warehouses)
        
        from apps.core.models import TaxType
        self.fields['tax_type'].queryset = TaxType.objects.filter(appear_in_invoices=True, is_active=True)
        self.fields['tax_type2'].queryset = TaxType.objects.filter(appear_in_invoices=True, is_active=True)

PurchaseReturnLineFormSet = inlineformset_factory(
    PurchaseReturn, PurchaseReturnLine,
    form=PurchaseReturnLineForm,
    extra=1,
    can_delete=True
)
