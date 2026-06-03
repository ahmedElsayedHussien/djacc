from django import forms
from django.conf import settings
from django.utils import timezone
from django.forms import inlineformset_factory
from decimal import Decimal
from apps.core.models import Account
from apps.sales.models import SalesRepresentative
from .models import (
    Warehouse, ItemCategory, Item, WarehouseTransfer, WarehouseTransferLine,
    LoadingOrder, LoadingOrderLine, UnitOfMeasure, StockVoucher, StockVoucherLine,
    ItemLedger,
)

class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ['code', 'name', 'location', 'is_active']
        labels = {
            'code': 'كود المستودع',
            'name': 'اسم المستودع',
            'location': 'الموقع',
            'is_active': 'نشط',
        }
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class ItemCategoryForm(forms.ModelForm):
    code = forms.CharField(required=False, widget=forms.HiddenInput())
    class Meta:
        model = ItemCategory
        fields = ['code', 'name', 'parent']
        labels = {
            'name': 'اسم التصنيف',
            'parent': 'التصنيف الأب',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
        }

class UnitOfMeasureForm(forms.ModelForm):
    code = forms.CharField(required=False, widget=forms.HiddenInput())
    class Meta:
        model = UnitOfMeasure
        fields = ['code', 'name']
        labels = {
            'name': 'اسم الوحدة',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
        }

class ItemForm(forms.ModelForm):
    code = forms.CharField(required=False, widget=forms.HiddenInput())
    conversion_factor = forms.DecimalField(required=False, initial=1, widget=forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}))
    purchase_conversion_factor = forms.DecimalField(required=False, initial=1, widget=forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}))

    class Meta:
        model = Item
        fields = [
            'code', 'name', 'category', 'base_unit', 'sales_unit', 'conversion_factor',
            'purchase_unit', 'purchase_conversion_factor',
            'inventory_account', 'cogs_account', 'sales_account',
            'minimum_stock', 'standard_price', 'barcode',
        ]
        labels = {
            'name': 'اسم الصنف',
            'category': 'التصنيف',
            'base_unit': 'وحدة القياس الأساسية',
            'sales_unit': 'وحدة البيع',
            'conversion_factor': 'معامل التحويل (البيع → الأساسية)',
            'purchase_unit': 'وحدة الشراء',
            'purchase_conversion_factor': 'معامل تحويل الشراء',
            'inventory_account': 'حساب المخزون',
            'cogs_account': 'حساب تكلفة المبيعات',
            'sales_account': 'حساب الإيراد',
            'minimum_stock': 'الحد الأدنى للمخزون',
            'standard_price': 'سعر البيع القياسي',
            'barcode': 'الباركود',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'base_unit': forms.Select(attrs={'class': 'form-select'}),
            'sales_unit': forms.Select(attrs={'class': 'form-select'}),
            'purchase_unit': forms.Select(attrs={'class': 'form-select'}),
            'inventory_account': forms.Select(attrs={'class': 'form-select', 'style': 'pointer-events: none; background-color: #f8f9fa;'}),
            'cogs_account': forms.Select(attrs={'class': 'form-select', 'style': 'pointer-events: none; background-color: #f8f9fa;'}),
            'sales_account': forms.Select(attrs={'class': 'form-select', 'style': 'pointer-events: none; background-color: #f8f9fa;'}),
            'minimum_stock': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'standard_price': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
            'barcode': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.instance.pk:
            self.fields['code'].widget = forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'})
        
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
            
            # Resolve inventory account (if the parent account itself is not a leaf, fallback to leaf child)
            inv_acc = leaf_accounts.filter(code=inventory_code).first()
            if not inv_acc:
                inv_acc = leaf_accounts.filter(code=inventory_code + '01').first()
                if not inv_acc:
                    inv_acc = leaf_accounts.filter(parent__code=inventory_code).first()
            
            self.fields['inventory_account'].initial = inv_acc
            self.fields['cogs_account'].initial = leaf_accounts.filter(code=cogs_code).first()
            self.fields['sales_account'].initial = leaf_accounts.filter(code=sales_code).first()

        # Prevent manual changes to structural accounting fields via POST
        self.fields['inventory_account'].disabled = True
        self.fields['cogs_account'].disabled = True
        self.fields['sales_account'].disabled = True

class WarehouseTransferForm(forms.ModelForm):
    class Meta:
        model = WarehouseTransfer
        fields = ['date', 'from_warehouse', 'to_warehouse', 'notes']
        labels = {
            'date': 'تاريخ التحويل',
            'from_warehouse': 'من مستودع',
            'to_warehouse': 'إلى مستودع',
            'notes': 'ملاحظات',
        }
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'from_warehouse': forms.Select(attrs={'class': 'form-select'}),
            'to_warehouse': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['date'].initial = timezone.now().date()
        self.fields['from_warehouse'].queryset = Warehouse.objects.filter(is_active=True).order_by('name')
        self.fields['to_warehouse'].queryset = Warehouse.objects.filter(is_active=True).order_by('name')

    def clean_date(self):
        d = self.cleaned_data.get('date')
        if d and d > timezone.now().date():
            raise forms.ValidationError('تاريخ التحويل لا يمكن أن يكون في المستقبل')
        return d

    def clean(self):
        cleaned_data = super().clean()
        from_warehouse = cleaned_data.get('from_warehouse')
        to_warehouse = cleaned_data.get('to_warehouse')

        if from_warehouse and to_warehouse and from_warehouse == to_warehouse:
            raise forms.ValidationError("المستودع المصدر والوجهة يجب أن يكونا مختلفين.")
        return cleaned_data

class WarehouseTransferLineForm(forms.ModelForm):
    class Meta:
        model = WarehouseTransferLine
        fields = ['item', 'unit', 'quantity', 'notes']
        labels = {
            'item': 'الصنف',
            'unit': 'الوحدة',
            'quantity': 'الكمية',
            'notes': 'ملاحظات',
        }
        widgets = {
            'item': forms.Select(attrs={'class': 'form-select'}),
            'unit': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '0.0001', 'step': 'any'}),
            'notes': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_quantity(self):
        qty = self.cleaned_data.get('quantity')
        if qty is not None and qty <= 0:
            raise forms.ValidationError('الكمية يجب أن تكون أكبر من صفر')
        return qty

class BaseWarehouseTransferLineFormSet(forms.BaseInlineFormSet):
    def clean(self):
        items = []
        for form in self.forms:
            if self.can_delete and self._should_delete_form(form):
                continue
            item = form.cleaned_data.get('item')
            if item:
                if item in items:
                    form.add_error('item', 'هذا الصنف مكرر في الأسطر. يرجى تجميع الكميات في سطر واحد.')
                items.append(item)

        super().clean()
        if any(self.errors):
            return

WarehouseTransferLineFormSet = inlineformset_factory(
    WarehouseTransfer, WarehouseTransferLine,
    form=WarehouseTransferLineForm,
    formset=BaseWarehouseTransferLineFormSet,
    extra=1,
    can_delete=True
)



class LoadingOrderForm(forms.ModelForm):
    number = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'class': 'form-control', 
        'readonly': 'readonly', 
        'placeholder': 'سيتم توليده تلقائياً'
    }))
    class Meta:
        model = LoadingOrder
        fields = ['number', 'date', 'sales_rep', 'from_warehouse', 'to_warehouse', 'notes']
        labels = {
            'date': 'تاريخ الطلب',
            'sales_rep': 'المندوب',
            'from_warehouse': 'من مستودع',
            'to_warehouse': 'إلى مستودع',
            'notes': 'ملاحظات',
        }
        widgets = {
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

    def clean_date(self):
        d = self.cleaned_data.get('date')
        if d and d > timezone.now().date():
            raise forms.ValidationError('تاريخ الطلب لا يمكن أن يكون في المستقبل')
        return d

    def clean(self):
        cleaned_data = super().clean()
        from_warehouse = cleaned_data.get('from_warehouse')
        to_warehouse = cleaned_data.get('to_warehouse')

        if from_warehouse and to_warehouse and from_warehouse == to_warehouse:
            raise forms.ValidationError('المستودع المصدر والوجهة يجب أن يكونا مختلفين.')
        
        if from_warehouse:
            if not from_warehouse.is_active:
                raise forms.ValidationError({'from_warehouse': 'المستودع المصدر غير نشط.'})
            if SalesRepresentative.objects.filter(warehouse=from_warehouse).exists():
                raise forms.ValidationError({'from_warehouse': 'المستودع المصدر يجب أن يكون مستودعاً رئيسياً، ولا يمكن الصرف من مستودع (سيارة) مندوب.'})
        return cleaned_data

class LoadingOrderLineForm(forms.ModelForm):
    class Meta:
        model = LoadingOrderLine
        fields = ['item', 'unit', 'requested_qty', 'approved_qty', 'notes']
        labels = {
            'item': 'الصنف',
            'unit': 'الوحدة',
            'requested_qty': 'الكمية المطلوبة',
            'approved_qty': 'الكمية المعتمدة',
            'notes': 'ملاحظات',
        }
        widgets = {
            'item': forms.Select(attrs={'class': 'form-select'}),
            'unit': forms.Select(attrs={'class': 'form-select'}),
            'requested_qty': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'approved_qty': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'يترك فارغاً حالياً'}),
            'notes': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_requested_qty(self):
        qty = self.cleaned_data.get('requested_qty')
        if qty is not None and qty <= 0:
            raise forms.ValidationError('الكمية المطلوبة يجب أن تكون أكبر من صفر')
        return qty

    def clean_approved_qty(self):
        qty = self.cleaned_data.get('approved_qty')
        if qty is not None:
            if qty < 0:
                raise forms.ValidationError('الكمية المعتمدة لا يمكن أن تكون سالبة')
            requested = self.cleaned_data.get('requested_qty')
            if requested is not None and qty > requested:
                raise forms.ValidationError(f'الكمية المعتمدة ({qty}) لا يمكن أن تتجاوز الكمية المطلوبة ({requested})')
        return qty

class BaseLoadingOrderLineFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
            
        items = []
        for form in self.forms:
            if self.can_delete and self._should_delete_form(form):
                continue
            item = form.cleaned_data.get('item')
            if item:
                if item in items:
                    form.add_error('item', "هذا الصنف مكرر في طلب التحويل")
                items.append(item)
        
        items = []
        from_warehouse = self.instance.from_warehouse
        
        for form in self.forms:
            if self.can_delete and self._should_delete_form(form):
                continue
            item = form.cleaned_data.get('item')
            requested_qty = form.cleaned_data.get('requested_qty')
            
            if item:
                if item in items:
                    form.add_error('item', 'هذا الصنف مكرر في الأسطر. يرجى تجميع الكميات في سطر واحد.')
                items.append(item)
                
                # Check available stock early in the form
                if from_warehouse and requested_qty:
                    ledger = ItemLedger.objects.filter(item=item, warehouse=from_warehouse).first()
                    on_hand = ledger.quantity_on_hand if ledger else Decimal('0')
                    if requested_qty > on_hand:
                        form.add_error('requested_qty', f'الكمية المطلوبة ({requested_qty}) تتجاوز المخزون المتاح في المستودع الرئيسي ({on_hand}).')

LoadingOrderLineFormSet = inlineformset_factory(
    LoadingOrder, LoadingOrderLine,
    form=LoadingOrderLineForm,
    formset=BaseLoadingOrderLineFormSet,
    extra=1,
    can_delete=True
)

class StockVoucherForm(forms.ModelForm):
    class Meta:
        model = StockVoucher
        fields = ['date', 'voucher_type', 'warehouse', 'offset_account', 'notes']
        labels = {
            'date': 'تاريخ الإذن',
            'voucher_type': 'نوع الإذن',
            'warehouse': 'المستودع',
            'offset_account': 'الحساب المقابل',
            'notes': 'ملاحظات',
        }
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'voucher_type': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'offset_account': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        exact_codes = [
            getattr(settings, 'INVENTORY_OPENING_BALANCE_ACCOUNT', '35'),
            getattr(settings, 'INVENTORY_ADJUSTMENT_IN_ACCOUNT', '424'),
            getattr(settings, 'INVENTORY_ADJUSTMENT_OUT_ACCOUNT', '542'),
            getattr(settings, 'INVENTORY_INTERNAL_CONSUMPTION_ACCOUNT', '524'),
            getattr(settings, 'INVENTORY_GIFTS_ACCOUNT', '525'),
        ]
        allowed_accounts = Account.objects.filter(
            code__in=exact_codes,
            is_active=True,
            is_leaf=True
        ).order_by('code')
        self.fields['offset_account'].queryset = allowed_accounts
        self.fields['offset_account'].required = True
        
        rep_warehouses = SalesRepresentative.objects.values_list('warehouse_id', flat=True)
        self.fields['warehouse'].queryset = Warehouse.objects.filter(
            is_active=True
        ).exclude(
            id__in=rep_warehouses
        ).order_by('name')

    def clean_date(self):
        d = self.cleaned_data.get('date')
        if d and d > timezone.now().date():
            raise forms.ValidationError('تاريخ الإذن لا يمكن أن يكون في المستقبل')
        return d

    def clean(self):
        cleaned_data = super().clean()
        voucher_type = cleaned_data.get('voucher_type')
        offset_account = cleaned_data.get('offset_account')
        
        if voucher_type == 'issue' and not offset_account:
            raise forms.ValidationError({'offset_account': 'إذن الصرف يتطلب حساباً مقابلاً'})
            
        if offset_account:
            # 1. حساب الأرصدة الافتتاحية (كود 35) يظهر فقط مع إذن الإضافة
            if offset_account.code == '35' and voucher_type == 'issue':
                raise forms.ValidationError({'offset_account': 'لا يمكن استخدام حساب الأرصدة الافتتاحية مع إذن الصرف. يرجى اختيار حساب آخر.'})
                

                    
        return cleaned_data

class StockVoucherLineForm(forms.ModelForm):
    class Meta:
        model = StockVoucherLine
        fields = ['item', 'unit', 'quantity', 'unit_cost', 'notes']
        labels = {
            'item': 'الصنف',
            'unit': 'الوحدة',
            'quantity': 'الكمية',
            'unit_cost': 'تكلفة الوحدة',
            'notes': 'ملاحظات',
        }
        widgets = {
            'item': forms.Select(attrs={'class': 'form-select'}),
            'unit': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'notes': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_quantity(self):
        qty = self.cleaned_data.get('quantity')
        if qty is not None and qty <= 0:
            raise forms.ValidationError('الكمية يجب أن تكون أكبر من صفر')
        return qty

    def clean_unit_cost(self):
        cost = self.cleaned_data.get('unit_cost')
        if cost is not None and cost < 0:
            raise forms.ValidationError('تكلفة الوحدة لا يمكن أن تكون سالبة')
        return cost

class BaseStockVoucherLineFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
            
        items = []
        for form in self.forms:
            if self.can_delete and self._should_delete_form(form):
                continue
            item = form.cleaned_data.get('item')
            if item:
                if item in items:
                    form.add_error('item', "هذا الصنف مكرر في طلب التحويل")
                items.append(item)
        
        items = []
        voucher_type = self.data.get('voucher_type') or (self.instance.voucher_type if self.instance else '')
        
        offset_account_id = self.data.get('offset_account')
        is_opening = False
        if offset_account_id:
            from apps.core.models import Account
            acc = Account.objects.filter(id=offset_account_id).first()
            if acc and acc.code == '35':
                is_opening = True
        
        for form in self.forms:
            if self.can_delete and self._should_delete_form(form):
                continue
            item = form.cleaned_data.get('item')
            unit_cost = form.cleaned_data.get('unit_cost')
            quantity = form.cleaned_data.get('quantity', 0)
            
            if item:
                if item in items:
                    form.add_error('item', 'هذا الصنف مكرر في الأسطر. يرجى تجميع الكميات في سطر واحد.')
                items.append(item)
                
                # Check positive unit_cost for receipt vouchers if it is an opening balance
                if voucher_type == 'receipt' and is_opening:
                    if unit_cost is None or unit_cost <= 0:
                        form.add_error('unit_cost', 'يجب إدخال تكلفة وحدة أكبر من الصفر لإذن إضافة الرصيد الافتتاحي.')
                
                # Proactive stock check for issue vouchers
                if voucher_type == 'issue':
                    if quantity > 0:
                        warehouse_id = self.data.get('warehouse')
                        if warehouse_id:
                            from .models import ItemLedger
                            ledger = ItemLedger.objects.filter(item=item, warehouse_id=warehouse_id).first()
                            available = ledger.quantity_on_hand if ledger else 0
                            if quantity > available:
                                form.add_error('quantity', f'الكمية المطلوبة ({quantity}) تتجاوز الرصيد المتاح ({available}).')

StockVoucherLineFormSet = inlineformset_factory(
    StockVoucher, StockVoucherLine,
    form=StockVoucherLineForm,
    formset=BaseStockVoucherLineFormSet,
    extra=1,
    can_delete=True
)
