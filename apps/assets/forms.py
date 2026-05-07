from django import forms
from .models import Asset, AssetCategory

class AssetForm(forms.ModelForm):
    class Meta:
        model = Asset
        fields = ['code', 'name', 'category', 'purchase_date', 'purchase_value', 'salvage_value', 'initial_accumulated_depreciation', 'depreciation_rate', 'department', 'location', 'notes']
        widgets = {
            'purchase_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
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
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'default_depreciation_rate': forms.NumberInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
