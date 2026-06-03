from django import forms
from django.core.exceptions import ValidationError
from .models import POSStation
from apps.inventory.models import Warehouse
from apps.treasury.models import CashBox, BankAccount, MobileWallet
from apps.treasury.utils import get_available_cash_boxes

class POSStationForm(forms.ModelForm):
    class Meta:
        model = POSStation
        fields = ['code', 'name', 'warehouse', 'cash_box', 'bank_account', 'mobile_wallet', 'is_active']
        labels = {
            'code': 'كود نقطة البيع',
            'name': 'اسم نقطة البيع',
            'warehouse': 'المخزن المرتبط',
            'cash_box': 'درج النقدية (الخزينة)',
            'bank_account': 'حساب البنك (للفيزا)',
            'mobile_wallet': 'المحفظة الإلكترونية',
            'is_active': 'نشطة',
        }
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: POS-01'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: كاشير الصيدلية'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'cash_box': forms.Select(attrs={'class': 'form-select'}),
            'bank_account': forms.Select(attrs={'class': 'form-select'}),
            'mobile_wallet': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if 'cash_box' in self.fields:
            if user:
                self.fields['cash_box'].queryset = get_available_cash_boxes(user)
            else:
                self.fields['cash_box'].queryset = self.fields['cash_box'].queryset.none()
        
        if 'warehouse' in self.fields:
            qs = Warehouse.objects.filter(is_active=True)
            if self.instance and getattr(self.instance, 'warehouse_id', None):
                qs = qs | Warehouse.objects.filter(id=self.instance.warehouse_id)
            self.fields['warehouse'].queryset = qs.distinct()
            
        if 'bank_account' in self.fields:
            qs = BankAccount.objects.filter(is_active=True)
            if self.instance and getattr(self.instance, 'bank_account_id', None):
                qs = qs | BankAccount.objects.filter(id=self.instance.bank_account_id)
            self.fields['bank_account'].queryset = qs.distinct()

        if 'mobile_wallet' in self.fields:
            qs = MobileWallet.objects.filter(is_active=True)
            if self.instance and getattr(self.instance, 'mobile_wallet_id', None):
                qs = qs | MobileWallet.objects.filter(id=self.instance.mobile_wallet_id)
            self.fields['mobile_wallet'].queryset = qs.distinct()

    def clean(self):
        cleaned_data = super().clean()
        warehouse = cleaned_data.get('warehouse')
        cash_box = cleaned_data.get('cash_box')
        if not warehouse:
            raise ValidationError("يجب اختيار المخزن المرتبط بنقطة البيع.")
        if warehouse and not warehouse.is_active:
            raise ValidationError(f"المخزن '{warehouse.name}' غير نشط.")
        if not cash_box:
            raise ValidationError("يجب اختيار درج النقدية (الخزينة) لنقطة البيع.")
        if cash_box and not cash_box.is_active:
            raise ValidationError(f"درج النقدية '{cash_box.name}' غير نشط.")
        return cleaned_data
