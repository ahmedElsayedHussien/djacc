import re

with open('apps/inventory/forms.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: AttributeError in WarehouseTransferForm.clean
old_clean = """    def clean(self):
        cleaned = super().clean()
        from_wh = cleaned.get('from_warehouse')
        to_wh = cleaned.get('to_warehouse')"""

new_clean = """    def clean(self):
        cleaned = super().clean()
        if cleaned is None:
            cleaned = self.cleaned_data
        from_wh = cleaned.get('from_warehouse')
        to_wh = cleaned.get('to_warehouse')"""

content = content.replace(old_clean, new_clean)

# Fix 2: Float formatting in WarehouseTransferLineFormSet
old_val = """                if base_qty > balance:
                    raise forms.ValidationError(
                        f"الكمية المطلوبة للتحويل ({base_qty}) أكبر من الرصيد المتاح ({balance})"
                    )"""
                    
new_val = """                if base_qty > balance:
                    raise forms.ValidationError(
                        f"الكمية المطلوبة للتحويل ({base_qty:.2f}) أكبر من الرصيد المتاح ({balance:.2f})"
                    )"""

content = content.replace(old_val, new_val)

with open('apps/inventory/forms.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Done!")
