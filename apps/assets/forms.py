from django import forms
from django.utils import timezone
from .models import Asset, AssetCategory
from apps.core.models import Account

class AssetForm(forms.ModelForm):
    class Meta:
        model = Asset
        fields = ['name', 'category', 'purchase_date', 'purchase_value', 'salvage_value', 'initial_accumulated_depreciation', 'depreciation_rate', 'department', 'location', 'notes']
        labels = {
            'name': 'اسم الأصل',
            'category': 'تصنيف الأصل',
            'purchase_date': 'تاريخ الشراء',
            'purchase_value': 'قيمة الشراء',
            'salvage_value': 'القيمة التخريدية',
            'initial_accumulated_depreciation': 'مجمع الإهلاك الافتتاحي',
            'depreciation_rate': 'نسبة الإهلاك السنوي (%)',
            'department': 'الإدارة / القسم',
            'location': 'الموقع',
            'notes': 'ملاحظات',
        }
        widgets = {
            'purchase_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'purchase_value': forms.NumberInput(attrs={'class': 'form-control'}),
            'salvage_value': forms.NumberInput(attrs={'class': 'form-control'}),
            'initial_accumulated_depreciation': forms.NumberInput(attrs={'class': 'form-control'}),
            'depreciation_rate': forms.NumberInput(attrs={'class': 'form-control'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean_purchase_date(self):
        d = self.cleaned_data.get('purchase_date')
        if d and d > timezone.now().date():
            raise forms.ValidationError('تاريخ الشراء لا يمكن أن يكون في المستقبل')
        return d

    def clean_salvage_value(self):
        val = self.cleaned_data.get('salvage_value')
        if val is not None and val < 0:
            raise forms.ValidationError('القيمة التخريدية لا يمكن أن تكون سالبة')
        return val

    def clean_initial_accumulated_depreciation(self):
        val = self.cleaned_data.get('initial_accumulated_depreciation')
        if val is not None and val < 0:
            raise forms.ValidationError('مجمع الإهلاك الافتتاحي لا يمكن أن يكون سالباً')
        return val

    def clean_depreciation_rate(self):
        rate = self.cleaned_data.get('depreciation_rate')
        if rate is not None and (rate < 0 or rate > 100):
            raise forms.ValidationError('نسبة الإهلاك السنوية يجب أن تكون بين 0 و 100')
        return rate

    def clean(self):
        cleaned_data = super().clean()
        purchase_value = cleaned_data.get('purchase_value')
        salvage_value = cleaned_data.get('salvage_value')
        initial_acc_dep = cleaned_data.get('initial_accumulated_depreciation')

        if purchase_value and salvage_value:
            if salvage_value >= purchase_value:
                self.add_error('salvage_value', 'القيمة التخريدية يجب أن تكون أقل من قيمة الشراء.')

        if purchase_value and initial_acc_dep:
            if initial_acc_dep >= purchase_value:
                self.add_error('initial_accumulated_depreciation', 'مجمع الإهلاك الافتتاحي يجب أن يكون أقل من قيمة الشراء.')
        
        return cleaned_data

class AssetCategoryForm(forms.ModelForm):
    class Meta:
        model = AssetCategory
        fields = ['name', 'default_depreciation_rate', 'description']
        labels = {
            'name': 'اسم التصنيف',
            'default_depreciation_rate': 'نسبة الإهلاك الافتراضية (%)',
            'description': 'وصف',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'default_depreciation_rate': forms.NumberInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean_default_depreciation_rate(self):
        rate = self.cleaned_data.get('default_depreciation_rate')
        if rate is not None and (rate < 0 or rate > 100):
            raise forms.ValidationError('نسبة الإهلاك الافتراضية يجب أن تكون بين 0 و 100')
        return rate
