import re

def main():
    file_path = 'apps/core/models.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    # 1. SystemNotification import fix
    content = content.replace(
        'from django.contrib.auth.models import User',
        'from django.contrib.auth import get_user_model'
    )
    content = content.replace(
        '        accountants = User.objects.filter(',
        '        User = get_user_model()\n        accountants = User.objects.filter('
    )

    # 2. ConcurrencyModel is_dirty
    old_dirty = """    @property
    def is_dirty(self):
        for field in self._meta.fields:
            if field.name == 'updated_at' or field.name == 'version':
                continue
            if getattr(self, field.name) != self._original_state.get(field.name):
                return True
        return False"""
    new_dirty = """    @property
    def is_dirty(self):
        for field in self._meta.fields:
            if field.name in ['updated_at', 'version']:
                continue
            if getattr(self, field.attname) != self._original_state.get(field.attname):
                return True
        return False"""
    content = content.replace(old_dirty, new_dirty)

    # 3. CostCenter clean method
    old_cc_clean = """    def clean(self):
        if self.parent:
            if self.pk:
                def _check_cycle(node, target):
                    if node is None:
                        return False
                    if node.pk == target.pk:
                        return True
                    return any(_check_cycle(c, target) for c in node.children.all())
                if _check_cycle(self.parent, self):
                    raise ValidationError({'parent': 'تسلسل هرمي دائري غير مسموح به'})
            if not self.parent.is_active:
                raise ValidationError({'parent': 'لا يمكن ربط مركز تكلفة بمركز غير نشط'})"""
    new_cc_clean = """    def clean(self):
        if self.is_leaf and self.pk and self.children.exists():
            raise ValidationError('لا يمكن جعل المركز طرفي (leaf) وله مراكز فرعية')
        if self.parent:
            if self.pk:
                current = self.parent
                while current:
                    if current.pk == self.pk:
                        raise ValidationError({'parent': 'تسلسل هرمي دائري غير مسموح به'})
                    current = current.parent
            if not self.parent.is_active:
                raise ValidationError({'parent': 'لا يمكن ربط مركز تكلفة بمركز غير نشط'})"""
    content = content.replace(old_cc_clean, new_cc_clean)

    # 4. JournalEntry multi-currency
    old_tot = """    @property
    def total_debit(self):
        return self.lines.aggregate(t=models.Sum('debit'))['t'] or 0

    @property
    def total_credit(self):
        return self.lines.aggregate(t=models.Sum('credit'))['t'] or 0"""
    new_tot = """    @property
    def total_debit(self):
        return self.lines.aggregate(t=models.Sum(models.F('debit') * models.F('exchange_rate')))['t'] or 0

    @property
    def total_credit(self):
        return self.lines.aggregate(t=models.Sum(models.F('credit') * models.F('exchange_rate')))['t'] or 0"""
    content = content.replace(old_tot, new_tot)

    # 5. JournalEntry clean, save, delete
    # First, let's locate the existing clean method of JournalEntry
    old_je_clean = """    def clean(self):
        if self.date and self.date > timezone.now().date():
            raise ValidationError({'date': 'تاريخ القيد لا يمكن أن يكون في المستقبل'})
        
        if self.fiscal_year:
            if self.date and (self.date < self.fiscal_year.start_date or self.date > self.fiscal_year.end_date):
                raise ValidationError({'date': f'تاريخ القيد يجب أن يقع ضمن السنة المالية ({self.fiscal_year.start_date} إلى {self.fiscal_year.end_date})'})
            
            if self.fiscal_year.is_closed:
                raise ValidationError({'fiscal_year': 'لا يمكن إضافة قيود في سنة مالية مقفلة'})"""
                
    new_je_clean = """    def save(self, *args, **kwargs):
        if not self.number:
            last_id = JournalEntry.objects.order_by('-id').first()
            self.number = f"JE-{(last_id.id + 1) if last_id else 1}"
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.is_posted:
            raise ValidationError("لا يمكن حذف قيد مُرحّل. قم بإنشاء قيد عكسي بدلاً من ذلك.")
        super().delete(*args, **kwargs)

    def clean(self):
        if self.date and self.date > timezone.now().date():
            raise ValidationError({'date': 'تاريخ القيد لا يمكن أن يكون في المستقبل'})
        
        if self.fiscal_year:
            if self.date and (self.date < self.fiscal_year.start_date or self.date > self.fiscal_year.end_date):
                raise ValidationError({'date': f'تاريخ القيد يجب أن يقع ضمن السنة المالية ({self.fiscal_year.start_date} إلى {self.fiscal_year.end_date})'})
            
            if self.fiscal_year.is_closed:
                raise ValidationError({'fiscal_year': 'لا يمكن إضافة قيود في سنة مالية مقفلة'})

        if self.is_posted:
            if self.total_debit != self.total_credit:
                raise ValidationError("القيد غير متزن: إجمالي المدين لا يساوي إجمالي الدائن")
            if self.total_debit == 0:
                raise ValidationError("لا يمكن ترحيل قيد بقيمة صفر")

        if self.pk:
            old = JournalEntry.objects.filter(pk=self.pk).first()
            if old and old.is_posted and not self.is_reversed:
                if any(getattr(self, f) != getattr(old, f) for f in ['date', 'entry_type', 'fiscal_year_id', 'description']):
                    raise ValidationError("لا يمكن تعديل بيانات القيد الأساسية بعد الترحيل")"""
    content = content.replace(old_je_clean, new_je_clean)

    # 6. JournalLine clean and delete
    old_jl_clean = """    def clean(self):
        if getattr(self, 'debit', 0) > 0 and getattr(self, 'credit', 0) > 0:
            raise ValidationError('لا يمكن أن يكون السطر مدين ودائن في نفس الوقت')
        if getattr(self, 'debit', 0) == 0 and getattr(self, 'credit', 0) == 0:
            raise ValidationError('يجب إدخال قيمة في الجانب المدين أو الدائن')
            
        if self.account:
            if not self.account.is_leaf:
                raise ValidationError({'account': 'لا يمكن التسجيل على حساب رئيسي (غير ورقي)'})
            if not self.account.is_active:
                raise ValidationError({'account': 'هذا الحساب غير نشط'})"""
                
    new_jl_clean = """    def delete(self, *args, **kwargs):
        if self.entry_id and self.entry.is_posted:
            raise ValidationError("لا يمكن حذف سطر من قيد مُرحّل")
        super().delete(*args, **kwargs)

    def clean(self):
        if self.entry_id:
            if self.entry.is_posted:
                raise ValidationError('لا يمكن إضافة أو تعديل سطور لقيد مُرحّل')
            if self.entry.fiscal_year and self.entry.fiscal_year.is_closed:
                raise ValidationError('لا يمكن تعديل سطور في سنة مالية مقفلة')

        if getattr(self, 'debit', 0) > 0 and getattr(self, 'credit', 0) > 0:
            raise ValidationError('لا يمكن أن يكون السطر مدين ودائن في نفس الوقت')
        if getattr(self, 'debit', 0) == 0 and getattr(self, 'credit', 0) == 0:
            raise ValidationError('يجب إدخال قيمة في الجانب المدين أو الدائن')
            
        if self.account:
            if not self.account.is_leaf:
                raise ValidationError({'account': 'لا يمكن التسجيل على حساب رئيسي (غير ورقي)'})
            if not self.account.is_active:
                raise ValidationError({'account': 'هذا الحساب غير نشط'})"""
    content = content.replace(old_jl_clean, new_jl_clean)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
    print("Models updated successfully.")

if __name__ == '__main__':
    main()
