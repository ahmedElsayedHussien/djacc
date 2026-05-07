from django import forms
from .models import Warehouse, ItemCategory, Item, WarehouseTransfer, LoadingOrder, LoadingOrderLine
from django.forms import inlineformset_factory
from apps.core.models import Account

class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ['code', 'name', 'gl_account', 'location']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'gl_account': forms.Select(attrs={'class': 'form-select'}),
            'location': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

class ItemCategoryForm(forms.ModelForm):
    class Meta:
        model = ItemCategory
        fields = ['code', 'name', 'parent']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
        }

class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = [
            'code', 'name', 'category', 'base_unit', 'sales_unit', 'conversion_factor',
            'purchase_unit', 'purchase_conversion_factor',
            'inventory_account', 'cogs_account', 'sales_account',
            'minimum_stock', 'barcode',
        ]
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'base_unit': forms.Select(attrs={'class': 'form-select'}),
            'sales_unit': forms.Select(attrs={'class': 'form-select'}),
            'conversion_factor': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'purchase_unit': forms.Select(attrs={'class': 'form-select'}),
            'purchase_conversion_factor': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'inventory_account': forms.Select(attrs={'class': 'form-select', 'style': 'pointer-events: none; background-color: #f8f9fa;'}),
            'cogs_account': forms.Select(attrs={'class': 'form-select', 'style': 'pointer-events: none; background-color: #f8f9fa;'}),
            'sales_account': forms.Select(attrs={'class': 'form-select', 'style': 'pointer-events: none; background-color: #f8f9fa;'}),
            'minimum_stock': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'barcode': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.conf import settings
        
        # Only show leaf accounts for accounting fields
        leaf_accounts = Account.objects.filter(is_leaf=True, is_active=True).order_by('code')
        self.fields['inventory_account'].queryset = leaf_accounts.filter(account_type='asset')
        self.fields['cogs_account'].queryset = leaf_accounts.filter(account_type='expense')
        self.fields['sales_account'].queryset = leaf_accounts.filter(account_type='revenue')
        self.fields['category'].queryset = ItemCategory.objects.all()

        # Set default values from settings if creating new item
        if not self.instance.pk:
            inventory_code = getattr(settings, 'DEFAULT_INVENTORY_ACCOUNT', '1131')
            cogs_code = getattr(settings, 'DEFAULT_COGS_ACCOUNT', '511')
            sales_code = getattr(settings, 'DEFAULT_SALES_ACCOUNT', '411')
            
            self.fields['inventory_account'].initial = leaf_accounts.filter(code=inventory_code).first()
            self.fields['cogs_account'].initial = leaf_accounts.filter(code=cogs_code).first()
            self.fields['sales_account'].initial = leaf_accounts.filter(code=sales_code).first()

class WarehouseTransferForm(forms.ModelForm):
    class Meta:
        model = WarehouseTransfer
        fields = ['date', 'from_warehouse', 'to_warehouse', 'item', 'quantity', 'notes']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': 'any'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        from_warehouse = cleaned_data.get('from_warehouse')
        to_warehouse = cleaned_data.get('to_warehouse')

        if from_warehouse and to_warehouse and from_warehouse == to_warehouse:
            raise forms.ValidationError("المستودع المصدر والوجهة يجب أن يكونا مختلفين.")
        return cleaned_data


class LoadingOrderForm(forms.ModelForm):
    class Meta:
        model = LoadingOrder
        fields = ['number', 'date', 'sales_rep', 'from_warehouse', 'to_warehouse', 'notes']
        widgets = {
            'number': forms.TextInput(attrs={
                'class': 'form-control', 
                'readonly': 'readonly', 
                'placeholder': 'سيتم توليده تلقائياً'
            }),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'sales_rep': forms.Select(attrs={'class': 'form-select'}),
            'from_warehouse': forms.Select(attrs={'class': 'form-select'}),
            'to_warehouse': forms.Select(attrs={
                'class': 'form-select', 
                'style': 'pointer-events: none; background-color: #f8f9fa;',
                'tabindex': '-1'
            }),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

class LoadingOrderLineForm(forms.ModelForm):
    class Meta:
        model = LoadingOrderLine
        fields = ['item', 'requested_qty', 'approved_qty', 'notes']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-select'}),
            'requested_qty': forms.NumberInput(attrs={'class': 'form-control'}),
            'approved_qty': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'يترك فارغاً حالياً'}),
            'notes': forms.TextInput(attrs={'class': 'form-control'}),
        }

LoadingOrderLineFormSet = inlineformset_factory(
    LoadingOrder, LoadingOrderLine,
    form=LoadingOrderLineForm,
    extra=1,
    can_delete=True
)

from .models import StockVoucher, StockVoucherLine

class StockVoucherForm(forms.ModelForm):
    class Meta:
        model = StockVoucher
        fields = ['date', 'voucher_type', 'warehouse', 'offset_account', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'voucher_type': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'offset_account': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.db.models import Q
        # قصر الحسابات المقابلة على قائمة دقيقة جداً ومحددة لحالات الأذون المخزنية فقط:
        # 35: أرصدة افتتاحية، 424: إيراد زيادة جرد، 542: خسائر عجز وتوالف، 524: مصاريف إدارية (للاستهلاك الداخلي)
        exact_codes = ['35', '424', '542', '524']
        allowed_accounts = Account.objects.filter(
            code__in=exact_codes,
            is_active=True,
            is_leaf=True  # ✅ Fix #5: التأكد من اختيار حسابات ورقية فقط للقيود
        ).order_by('code')
        self.fields['offset_account'].queryset = allowed_accounts

class StockVoucherLineForm(forms.ModelForm):
    class Meta:
        model = StockVoucherLine
        fields = ['item', 'quantity', 'unit_cost', 'notes']
        widgets = {
            'item': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'notes': forms.TextInput(attrs={'class': 'form-control'}),
        }

StockVoucherLineFormSet = inlineformset_factory(
    StockVoucher, StockVoucherLine,
    form=StockVoucherLineForm,
    extra=1,
    can_delete=True
)
