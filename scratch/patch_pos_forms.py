import re

def main():
    file_path = 'apps/pos/forms.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    # Add missing imports if needed
    if 'from apps.inventory.models import Warehouse' not in content:
        content = content.replace("from django import forms", "from django import forms\nfrom apps.inventory.models import Warehouse\nfrom apps.treasury.models import BankAccount, MobileWallet")

    old_init = """    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user and 'cash_box' in self.fields:
            self.fields['cash_box'].queryset = get_available_cash_boxes(user)"""
    new_init = """    def __init__(self, *args, **kwargs):
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
            self.fields['mobile_wallet'].queryset = qs.distinct()"""
    content = content.replace(old_init, new_init)

    old_clean = """    def clean(self):
        cleaned_data = super().clean()
        warehouse = cleaned_data.get('warehouse')
        cash_box = cleaned_data.get('cash_box')
        if not warehouse:
            raise ValidationError("يجب اختيار المخزن المرتبط بنقطة البيع.")
        if warehouse and not warehouse.is_active:
            raise ValidationError("المخزن المختار غير نشط.")
        if not cash_box:
            raise ValidationError("يجب اختيار درج النقدية.")
        if cash_box and not cash_box.is_active:
            raise ValidationError("درج النقدية المختار غير نشط.")
        return cleaned_data"""
    new_clean = """    def clean(self):
        cleaned_data = super().clean()
        warehouse = cleaned_data.get('warehouse')
        cash_box = cleaned_data.get('cash_box')
        bank_account = cleaned_data.get('bank_account')
        mobile_wallet = cleaned_data.get('mobile_wallet')

        if warehouse and not warehouse.is_active and warehouse != getattr(self.instance, 'warehouse', None):
            self.add_error('warehouse', f"المخزن '{warehouse.name}' غير نشط.")
            
        if cash_box and not cash_box.is_active and cash_box != getattr(self.instance, 'cash_box', None):
            self.add_error('cash_box', f"درج النقدية '{cash_box.name}' غير نشط.")

        if bank_account and getattr(bank_account, 'is_active', None) is False and bank_account != getattr(self.instance, 'bank_account', None):
            self.add_error('bank_account', f"حساب البنك '{bank_account.name}' غير نشط.")

        if mobile_wallet and getattr(mobile_wallet, 'is_active', None) is False and mobile_wallet != getattr(self.instance, 'mobile_wallet', None):
            self.add_error('mobile_wallet', f"المحفظة الإلكترونية '{mobile_wallet.name}' غير نشطة.")

        return cleaned_data"""
    content = content.replace(old_clean, new_clean)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Forms patched.")

if __name__ == '__main__':
    main()
