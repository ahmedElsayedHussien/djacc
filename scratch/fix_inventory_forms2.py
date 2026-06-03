import re

with open('apps/inventory/forms.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: loading order primary warehouse error target
old_clean = """        if hasattr(self.Meta.model, 'is_loading_order') and getattr(self.instance, 'is_loading_order', False):
            if from_wh and hasattr(from_wh, 'is_rep_warehouse') and from_wh.is_rep_warehouse:
                raise forms.ValidationError("مستودع المصدر لأمر التحميل لا يمكن أن يكون مستودع مندوب.")"""

new_clean = """        if hasattr(self.Meta.model, 'is_loading_order') and getattr(self.instance, 'is_loading_order', False):
            if from_wh and hasattr(from_wh, 'is_rep_warehouse') and from_wh.is_rep_warehouse:
                self.add_error('from_warehouse', "مستودع المصدر لأمر التحميل لا يمكن أن يكون مستودع مندوب.")"""

content = content.replace(old_clean, new_clean)

# Fix 2: duplicate items validation in WarehouseTransferLineFormSet
old_fs_clean = """    def clean(self):
        super().clean()
        if any(self.errors):
            return"""
            
new_fs_clean = """    def clean(self):
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
                items.append(item)"""

content = content.replace(old_fs_clean, new_fs_clean)

with open('apps/inventory/forms.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Done inventory forms!")
