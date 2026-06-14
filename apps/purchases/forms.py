import logging
from datetime import date
from django import forms
from django.forms import inlineformset_factory
from django.forms.models import BaseInlineFormSet
from django.db.models import Q, F
from .models import Supplier, PurchaseInvoice, PurchaseInvoiceLine, SupplierPayment, PurchaseReturn, PurchaseReturnLine
from apps.inventory.models import Item, Warehouse
from apps.core.models import CostCenter, TaxType
from apps.sales.models import SalesRepresentative
from apps.treasury.utils import get_available_cash_boxes
from apps.treasury.models import CashBox

logger = logging.getLogger(__name__)

class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['name', 'commercial_register', 'tax_number', 'payment_type', 'is_active', 'phone', 'email', 'payment_terms_days', 'address']
        labels = {
            'name': 'اسم المورد',
            'commercial_register': 'السجل التجاري',
            'tax_number': 'الرقم الضريبي',
            'payment_type': 'طريقة السداد المعتادة',
            'is_active': 'نشط',
            'phone': 'الهاتف',
            'email': 'البريد الإلكتروني',
            'payment_terms_days': 'مدة السداد (يوم)',
            'address': 'العنوان',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'commercial_register': forms.TextInput(attrs={'class': 'form-control'}),
            'tax_number': forms.TextInput(attrs={'class': 'form-control'}),
            'payment_type': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'payment_terms_days': forms.NumberInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    initial_balance = forms.DecimalField(min_value=0, 
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
        required=False, label='رقم فاتورة المورد',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اتركه فارغاً لاستخدام رقم النظام'})
    )
    class Meta:
        model = PurchaseInvoice
        fields = ['number', 'supplier_invoice_number', 'date', 'supplier', 'payment_type', 'payment_method', 'cash_box', 'bank_account', 'cost_center', 'due_date']
        labels = {
            'date': 'تاريخ الفاتورة',
            'supplier': 'المورد',
            'payment_type': 'نوع الدفع',
            'payment_method': 'طريقة الدفع',
            'cash_box': 'الخزينة',
            'bank_account': 'الحساب البنكي',
            'cost_center': 'مركز التكلفة',
            'due_date': 'تاريخ الاستحقاق',
            'supplier_invoice_number': 'رقم فاتورة المورد',
        }
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

    def clean_date(self):
        d = self.cleaned_data.get('date')
        if d and d > date.today():
            raise forms.ValidationError('تاريخ الفاتورة لا يمكن أن يكون في المستقبل')
        return d

    def clean_due_date(self):
        due = self.cleaned_data.get('due_date')
        inv_date = self.cleaned_data.get('date')
        if due and inv_date and due < inv_date:
            raise forms.ValidationError('تاريخ الاستحقاق يجب أن يكون بعد تاريخ الفاتورة')
        return due

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
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if 'cash_box' in self.fields:
            from apps.sales.models import SalesRepresentative
            rep_boxes = SalesRepresentative.objects.exclude(cash_box__isnull=True).values_list('cash_box_id', flat=True)
            if user:
                qs = get_available_cash_boxes(user)
            else:
                qs = CashBox.objects.filter(is_active=True)
            self.fields['cash_box'].queryset = qs.exclude(id__in=rep_boxes)
        if 'cost_center' in self.fields:
            self.fields['cost_center'].queryset = CostCenter.objects.filter(is_active=True, is_leaf=True).order_by('code')
            cc_80 = CostCenter.objects.filter(code='80').first()
            if cc_80:
                self.fields['cost_center'].initial = cc_80.id
            self.fields['cost_center'].widget.attrs['readonly'] = 'readonly'
            self.fields['cost_center'].widget.attrs['style'] = 'pointer-events: none; background-color: #e9ecef;'
            self.fields['cost_center'].required = False
        if 'supplier' in self.fields:
            qs = Supplier.objects.filter(is_active=True)
            if self.instance and self.instance.pk and self.instance.supplier_id:
                qs = qs | Supplier.objects.filter(id=self.instance.supplier_id)
            self.fields['supplier'].queryset = qs.distinct().order_by('name')

class PurchaseInvoiceLineForm(forms.ModelForm):
    class Meta:
        model = PurchaseInvoiceLine
        fields = ['item', 'warehouse', 'unit', 'quantity', 'unit_cost', 'discount_percent', 'tax_type', 'tax_percent', 'tax_type2', 'tax_percent2']
        labels = {
            'item': 'الصنف',
            'warehouse': 'المستودع',
            'unit': 'الوحدة',
            'quantity': 'الكمية',
            'unit_cost': 'تكلفة الوحدة',
            'discount_percent': 'نسبة الخصم %',
            'tax_type': 'نوع الضريبة 1',
            'tax_percent': 'نسبة الضريبة 1 %',
            'tax_type2': 'نوع الضريبة 2',
            'tax_percent2': 'نسبة الضريبة 2 %',
        }
        widgets = {
            'item': forms.Select(attrs={'class': 'form-select item-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'unit': forms.Select(attrs={'class': 'form-select unit-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control qty-input', 'step': 'any'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-control price-input', 'step': 'any'}),
            'discount_percent': forms.NumberInput(attrs={'class': 'form-control discount-input', 'step': 'any'}),
            'tax_type': forms.Select(attrs={'class': 'form-select tax-select'}),
            'tax_type2': forms.Select(attrs={'class': 'form-select tax-select2'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        rep_warehouses = SalesRepresentative.objects.values_list('warehouse_id', flat=True)
        if 'warehouse' in self.fields:
            self.fields['warehouse'].queryset = Warehouse.objects.filter(is_active=True).exclude(id__in=rep_warehouses)
        allowed_taxes = ['vat', 'wht', 'table', 'customs']
        from django.db.models import Q
        tax_qs = TaxType.objects.filter(
            appear_in_invoices=True, 
            is_active=True, 
            category__in=allowed_taxes
        ).filter(
            Q(name__icontains='مدخلات') | 
            Q(name__icontains='مشتريات') |
            Q(name__icontains='جمرك')
        )
        self.fields['tax_type'].queryset = tax_qs
        self.fields['tax_type2'].queryset = tax_qs

    def clean_quantity(self):
        qty = self.cleaned_data.get('quantity')
        if qty is not None and qty <= 0:
            raise forms.ValidationError('يجب أن تكون الكمية أكبر من صفر')
        return qty

    def clean(self):
        cleaned_data = super().clean()
        tax_type = cleaned_data.get('tax_type')
        tax_type2 = cleaned_data.get('tax_type2')
        if tax_type and tax_type2 and tax_type == tax_type2:
            self.add_error('tax_type2', 'لا يمكن اختيار نفس الضريبة مرتين.')
        return cleaned_data


class BasePurchaseLineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        valid_forms = [f for f in self.forms if not self.can_delete or not f.cleaned_data.get('DELETE')]
        if not valid_forms:
            raise forms.ValidationError("يجب إضافة صنف واحد على الأقل.")

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
    invoices = forms.ModelMultipleChoiceField(
        queryset=None, required=False,
        label='الفواتير المسددة',
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'size': 6})
    )
    class Meta:
        model = SupplierPayment
        fields = ['number', 'date', 'supplier', 'amount', 'payment_method', 'bank_account', 'cash_box', 'cheque_number', 'cheque_due_date']
        labels = {
            'date': 'تاريخ السداد',
            'supplier': 'المورد',
            'amount': 'المبلغ',
            'payment_method': 'طريقة الدفع',
            'bank_account': 'الحساب البنكي',
            'cash_box': 'الخزينة',
            'cheque_number': 'رقم الشيك',
            'cheque_due_date': 'تاريخ استحقاق الشيك',
        }
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'bank_account': forms.Select(attrs={'class': 'form-select'}),
            'cash_box': forms.Select(attrs={'class': 'form-select'}),
            'cheque_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'رقم الشيك'}),
            'cheque_due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is not None and amount <= 0:
            raise forms.ValidationError('يجب أن يكون المبلغ أكبر من صفر')
        return amount

    def clean_date(self):
        d = self.cleaned_data.get('date')
        if d and d > date.today():
            raise forms.ValidationError('تاريخ السداد لا يمكن أن يكون في المستقبل')
        return d

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get('payment_method')
        supplier = cleaned.get('supplier')
        invoices = cleaned.get('invoices')
        amount = cleaned.get('amount')

        if method == 'cheque':
            if not cleaned.get('cheque_number'):
                raise forms.ValidationError('يجب إدخال رقم الشيك')
            if not cleaned.get('cheque_due_date'):
                raise forms.ValidationError('يجب إدخال تاريخ استحقاق الشيك')

        if supplier and invoices:
            for inv in invoices:
                if inv.supplier != supplier:
                    raise forms.ValidationError(f'الفاتورة {inv.number} لا تتبع المورد المحدد')

        if supplier and invoices and amount:
            remaining_total = sum(inv.total - inv.paid_amount for inv in invoices)
            if amount > remaining_total:
                raise forms.ValidationError(f'المبلغ ({amount}) يتجاوز إجمالي المبالغ المستحقة ({remaining_total})')

        return cleaned

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if 'cash_box' in self.fields:
            from apps.sales.models import SalesRepresentative
            rep_boxes = SalesRepresentative.objects.exclude(cash_box__isnull=True).values_list('cash_box_id', flat=True)
            if user:
                qs = get_available_cash_boxes(user)
            else:
                qs = CashBox.objects.filter(is_active=True)
            self.fields['cash_box'].queryset = qs.exclude(id__in=rep_boxes)
        if 'invoices' in self.fields:
            supplier = self.instance.supplier_id if self.instance and self.instance.pk else None
            self.fields['invoices'].queryset = PurchaseInvoice.objects.filter(
                supplier=supplier,
                status=PurchaseInvoice.Status.POSTED,
                paid_amount__lt=F('total')
            ) if supplier else PurchaseInvoice.objects.none()
        if 'supplier' in self.fields:
            qs = Supplier.objects.filter(is_active=True)
            if self.instance and self.instance.pk and self.instance.supplier_id:
                qs = qs | Supplier.objects.filter(id=self.instance.supplier_id)
            self.fields['supplier'].queryset = qs.distinct().order_by('name')

class PurchaseReturnForm(forms.ModelForm):
    number = forms.CharField(
        required=False,
        widget=forms.HiddenInput()
    )
    class Meta:
        model = PurchaseReturn
        fields = ['number', 'date', 'invoice', 'supplier', 'payment_type', 'cash_box', 'cost_center', 'notes']
        labels = {
            'date': 'تاريخ المرتجع',
            'invoice': 'الفاتورة الأصلية',
            'supplier': 'المورد',
            'payment_type': 'طريقة الدفع',
            'cash_box': 'الخزينة (للنقدي)',
            'cost_center': 'مركز التكلفة',
            'notes': 'ملاحظات',
        }
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'invoice': forms.Select(attrs={'class': 'form-select'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'payment_type': forms.Select(attrs={'class': 'form-select'}),
            'cash_box': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean_date(self):
        d = self.cleaned_data.get('date')
        if d and d > date.today():
            raise forms.ValidationError('تاريخ المرتجع لا يمكن أن يكون في المستقبل')
        return d

    def clean(self):
        cleaned = super().clean()
        invoice = cleaned.get('invoice')
        supplier = cleaned.get('supplier')
        if invoice and supplier and invoice.supplier != supplier:
            raise forms.ValidationError('الفاتورة الأصلية لا تتبع هذا المورد')
        if invoice and invoice.status != PurchaseInvoice.Status.POSTED:
            raise forms.ValidationError('يمكن فقط إرجاع فواتير مرحّلة')
        return cleaned

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if 'supplier' in self.fields:
            qs = Supplier.objects.filter(is_active=True)
            if self.instance and self.instance.pk and self.instance.supplier_id:
                qs = qs | Supplier.objects.filter(id=self.instance.supplier_id)
            self.fields['supplier'].queryset = qs.distinct().order_by('name')
        
        if 'cash_box' in self.fields:
            from apps.sales.models import SalesRepresentative
            rep_boxes = SalesRepresentative.objects.exclude(cash_box__isnull=True).values_list('cash_box_id', flat=True)
            if user:
                from apps.treasury.utils import get_available_cash_boxes
                qs = get_available_cash_boxes(user)
            else:
                qs = CashBox.objects.filter(is_active=True)
            self.fields['cash_box'].queryset = qs.exclude(id__in=rep_boxes)

class PurchaseReturnLineForm(forms.ModelForm):
    class Meta:
        model = PurchaseReturnLine
        fields = ['item', 'warehouse', 'unit', 'quantity', 'unit_cost', 'discount_percent', 'tax_type', 'tax_percent', 'tax_type2', 'tax_percent2']
        labels = {
            'item': 'الصنف',
            'warehouse': 'المستودع',
            'unit': 'الوحدة',
            'quantity': 'الكمية',
            'unit_cost': 'تكلفة الوحدة',
            'discount_percent': 'نسبة الخصم %',
            'tax_type': 'نوع الضريبة 1',
            'tax_percent': 'نسبة الضريبة 1 %',
            'tax_type2': 'نوع الضريبة 2',
            'tax_percent2': 'نسبة الضريبة 2 %',
        }
        widgets = {
            'item': forms.Select(attrs={'class': 'form-select item-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'unit': forms.Select(attrs={'class': 'form-select unit-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control qty-input', 'step': 'any'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-control price-input', 'step': 'any'}),
            'discount_percent': forms.NumberInput(attrs={'class': 'form-control discount-input', 'step': 'any'}),
            'tax_type': forms.Select(attrs={'class': 'form-select tax-select'}),
            'tax_percent': forms.HiddenInput(attrs={'class': 'tax-rate'}),
            'tax_type2': forms.Select(attrs={'class': 'form-select tax-select2'}),
            'tax_percent2': forms.HiddenInput(attrs={'class': 'tax-rate2'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        rep_warehouses = SalesRepresentative.objects.values_list('warehouse_id', flat=True)
        if 'warehouse' in self.fields:
            self.fields['warehouse'].queryset = Warehouse.objects.filter(is_active=True).exclude(id__in=rep_warehouses)
        self.fields['tax_type'].queryset = TaxType.objects.filter(appear_in_invoices=True, is_active=True)
        self.fields['tax_type2'].queryset = TaxType.objects.filter(appear_in_invoices=True, is_active=True)

    def clean_quantity(self):
        qty = self.cleaned_data.get('quantity')
        if qty is not None and qty <= 0:
            raise forms.ValidationError('يجب أن تكون الكمية أكبر من صفر')
        return qty

    def clean(self):
        cleaned_data = super().clean()
        tax_type = cleaned_data.get('tax_type')
        tax_type2 = cleaned_data.get('tax_type2')
        if tax_type and tax_type2 and tax_type == tax_type2:
            self.add_error('tax_type2', 'لا يمكن اختيار نفس الضريبة مرتين.')
        return cleaned_data

PurchaseReturnLineFormSet = inlineformset_factory(
    PurchaseReturn, PurchaseReturnLine,
    form=PurchaseReturnLineForm,
    extra=1,
    can_delete=True
)
