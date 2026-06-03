import re

def main():
    file_path = 'apps/assets/forms.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    # Add missing imports if needed
    if 'from apps.core.models import Account' not in content:
        content = content.replace("from .models import Asset, AssetCategory", "from .models import Asset, AssetCategory\nfrom apps.core.models import Account")

    # AssetForm class
    old_asset_meta = """class AssetForm(forms.ModelForm):
    class Meta:
        model = Asset
        fields = ['name', 'category', 'purchase_date', 'purchase_value', 'salvage_value', 
                  'initial_accumulated_depreciation', 'depreciation_rate', 'department', 'location', 'notes']"""
    new_asset_meta = """class AssetForm(forms.ModelForm):
    offset_account = forms.ModelChoiceField(
        queryset=Account.objects.filter(is_leaf=True, is_active=True),
        required=False,
        label='حساب المقابل (للقيد المحاسبي)',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Asset
        fields = ['name', 'category', 'purchase_date', 'purchase_value', 'salvage_value', 
                  'initial_accumulated_depreciation', 'depreciation_rate', 'department', 'location', 'notes']"""
    content = content.replace(old_asset_meta, new_asset_meta)

    old_asset_init = """        self.fields['category'].widget.attrs.update({'class': 'form-select'})"""
    new_asset_init = """        self.fields['category'].widget.attrs.update({'class': 'form-select'})
        if not self.instance.pk:
            self.fields['offset_account'].required = True"""
    content = content.replace(old_asset_init, new_asset_init)

    old_asset_clean = """    def clean(self):
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

        return cleaned_data"""
    new_asset_clean = """    def clean_purchase_value(self):
        val = self.cleaned_data.get('purchase_value')
        if val is not None and val <= 0:
            raise forms.ValidationError('قيمة الشراء يجب أن تكون أكبر من صفر')
        return val

    def clean(self):
        cleaned_data = super().clean()
        purchase_value = cleaned_data.get('purchase_value')
        salvage_value = cleaned_data.get('salvage_value')
        initial_acc_dep = cleaned_data.get('initial_accumulated_depreciation')

        if purchase_value is not None and salvage_value is not None:
            if salvage_value >= purchase_value:
                self.add_error('salvage_value', 'القيمة التخريدية يجب أن تكون أقل من قيمة الشراء.')

        if purchase_value is not None and initial_acc_dep is not None:
            if initial_acc_dep >= purchase_value:
                self.add_error('initial_accumulated_depreciation', 'مجمع الإهلاك الافتتاحي يجب أن يكون أقل من قيمة الشراء.')
                
        if purchase_value is not None and salvage_value is not None and initial_acc_dep is not None:
            if initial_acc_dep + salvage_value > purchase_value:
                self.add_error(
                    'initial_accumulated_depreciation', 
                    'مجمع الإهلاك الافتتاحي مع القيمة التخريدية يتجاوز قيمة الشراء (الأصل مُهلك أكثر من المسموح).'
                )

        return cleaned_data"""
    content = content.replace(old_asset_clean, new_asset_clean)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Forms patched.")

if __name__ == '__main__':
    main()
