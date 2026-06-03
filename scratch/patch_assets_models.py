import re

def main():
    file_path = 'apps/assets/models.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    # 1. AssetCategory save
    old_cat_str = "    def __str__(self):\n        return self.name"
    new_cat_str = """    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name"""
    content = content.replace(old_cat_str, new_cat_str)
    
    # 2. Asset clean & save
    old_asset_clean = """    def clean(self):
        if self.salvage_value is not None and self.purchase_value is not None and self.salvage_value >= self.purchase_value:
            raise ValidationError({'salvage_value': 'القيمة التخريدية يجب أن تكون أقل من قيمة الشراء'})
            
        if self.initial_accumulated_depreciation is not None and self.purchase_value is not None and self.initial_accumulated_depreciation >= self.purchase_value:
            raise ValidationError({'initial_accumulated_depreciation': 'مجمع الإهلاك الافتتاحي يجب أن يكون أقل من قيمة الشراء'})"""
    new_asset_clean = """    def clean(self):
        if self.salvage_value is not None and self.purchase_value is not None and self.salvage_value >= self.purchase_value:
            raise ValidationError({'salvage_value': 'القيمة التخريدية يجب أن تكون أقل من قيمة الشراء'})
            
        if self.initial_accumulated_depreciation is not None and self.purchase_value is not None and self.salvage_value is not None:
            max_initial = self.purchase_value - self.salvage_value
            if self.initial_accumulated_depreciation > max_initial:
                raise ValidationError({'initial_accumulated_depreciation': 'مجمع الإهلاك الافتتاحي يجب ألا يتجاوز (قيمة الشراء - القيمة التخريدية)'})"""
    content = content.replace(old_asset_clean, new_asset_clean)

    old_asset_str = "    def __str__(self):\n        return f\"{self.code} - {self.name}\""
    new_asset_str = """    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} - {self.name}\""""
    content = content.replace(old_asset_str, new_asset_str)

    # 3. DepreciationLog clean & save
    old_dep_clean = """    def clean(self):
        if self.amount <= 0:
            raise ValidationError({'amount': 'قيمة الإهلاك يجب أن تكون أكبر من الصفر'})"""
    new_dep_clean = """    def clean(self):
        if self.amount <= 0:
            raise ValidationError({'amount': 'قيمة الإهلاك يجب أن تكون أكبر من الصفر'})
            
        if self.asset_id and self.amount is not None:
            from django.db.models import Sum
            other_logs = self.asset.depreciation_logs.exclude(pk=self.pk).aggregate(total=Sum('amount'))['total'] or 0
            max_allowed = self.asset.purchase_value - self.asset.salvage_value - self.asset.initial_accumulated_depreciation - other_logs
            if self.amount > max_allowed:
                raise ValidationError({'amount': f'مبلغ الإهلاك يتجاوز القيمة القابلة للإهلاك المتبقية ({max_allowed})'})"""
    content = content.replace(old_dep_clean, new_dep_clean)
    
    old_dep_str = "    def __str__(self):\n        return f\"إهلاك {self.asset} - {self.date}\""
    new_dep_str = """    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"إهلاك {self.asset} - {self.date}\""""
    content = content.replace(old_dep_str, new_dep_str)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Models patched.")

if __name__ == '__main__':
    main()
