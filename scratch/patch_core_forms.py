import re

def main():
    file_path = 'apps/core/forms.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    # 1. AccountForm clean method
    old_account_clean = """    def clean(self):
        cleaned = super().clean()
        is_leaf = cleaned.get('is_leaf')
        initial_balance_type = cleaned.get('initial_balance_type')
        initial_balance = cleaned.get('initial_balance')"""
    new_account_clean = """    def clean(self):
        cleaned = super().clean()
        is_leaf = cleaned.get('is_leaf')
        acc_type = cleaned.get('account_type')
        initial_balance_type = cleaned.get('initial_balance_type')
        initial_balance = cleaned.get('initial_balance')
        
        if self.instance.pk:
            if not is_leaf and self.instance.is_leaf:
                if self.instance.journalline_set.exists():
                    raise forms.ValidationError('لا يمكن تحويل الحساب إلى حساب رئيسي (غير ورقي) لوجود قيود يومية مسجلة عليه')
            if acc_type != self.instance.account_type:
                if self.instance.journalline_set.exists():
                    raise forms.ValidationError('لا يمكن تغيير نوع الحساب لوجود قيود يومية مسجلة عليه')"""
    content = content.replace(old_account_clean, new_account_clean)

    # 2. CostCenterForm clean method and __init__
    old_cc_init = """        self.fields['parent'].queryset = CostCenter.objects.all().order_by('code')"""
    new_cc_init = """        self.fields['parent'].queryset = CostCenter.objects.filter(is_leaf=False, is_active=True).order_by('code')"""
    content = content.replace(old_cc_init, new_cc_init)
    
    old_cc_clean = """    def clean(self):
        cleaned = super().clean()
        is_leaf = cleaned.get('is_leaf')
        parent = cleaned.get('parent')"""
    new_cc_clean = """    def clean(self):
        cleaned = super().clean()
        is_leaf = cleaned.get('is_leaf')
        parent = cleaned.get('parent')
        
        if self.instance.pk:
            if not is_leaf and self.instance.is_leaf:
                if self.instance.journalline_set.exists():
                    raise forms.ValidationError('لا يمكن تحويل المركز إلى رئيسي لوجود حركات مسجلة عليه')"""
    content = content.replace(old_cc_clean, new_cc_clean)

    # 3. TaxTypeForm __init__
    old_tax_init = """        self.fields['account'].queryset = Account.objects.filter(
            Q(code__startswith='1122') | Q(code__startswith='212'),
            is_leaf=True
        ).order_by('code')"""
    new_tax_init = """        self.fields['account'].queryset = Account.objects.filter(
            is_leaf=True, is_active=True
        ).order_by('code')"""
    content = content.replace(old_tax_init, new_tax_init)

    # 4. JournalEntryForm clean_date and entry_type choices crash
    old_je_init = """        self.fields['entry_type'].choices = [
            JournalEntry.EntryType.MANUAL,
        ]"""
    new_je_init = """        self.fields['entry_type'].choices = [
            (JournalEntry.EntryType.MANUAL.value, JournalEntry.EntryType.MANUAL.label),
        ]"""
    content = content.replace(old_je_init, new_je_init)
    
    old_clean_date = """    def clean_date(self):
        d = self.cleaned_data.get('date')
        if d and d > timezone.now().date():
            raise forms.ValidationError('تاريخ القيد لا يمكن أن يكون في المستقبل')
        return d"""
    new_clean_date = """    def clean_date(self):
        d = self.cleaned_data.get('date')
        if d:
            if d > timezone.now().date():
                raise forms.ValidationError('تاريخ القيد لا يمكن أن يكون في المستقبل')
            
            from .models import FiscalYear
            fiscal_year = FiscalYear.objects.filter(
                start_date__lte=d, end_date__gte=d, is_closed=False
            ).first()
            if not fiscal_year:
                raise forms.ValidationError('لا توجد سنة مالية مفتوحة تتوافق مع هذا التاريخ')
            self.instance.fiscal_year = fiscal_year
        return d"""
    content = content.replace(old_clean_date, new_clean_date)

    # 5. JournalLineForm clean method
    old_jl_clean = """    def clean(self):
        cleaned = super().clean()
        debit = cleaned.get('debit')"""
    new_jl_clean = """    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        debit = cleaned.get('debit')"""
    content = content.replace(old_jl_clean, new_jl_clean)

    # 6. JournalLineFormSet double entry validation
    old_formset_def = """JournalLineFormSet = forms.inlineformset_factory(
    JournalEntry, JournalLine, form=JournalLineForm,
    extra=4, can_delete=True
)"""
    new_formset_def = """from decimal import Decimal

class BaseJournalLineFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        total_debit = sum(Decimal(str(f.cleaned_data.get('debit') or 0)) for f in self.forms if not self._should_delete_form(f))
        total_credit = sum(Decimal(str(f.cleaned_data.get('credit') or 0)) for f in self.forms if not self._should_delete_form(f))
        
        if total_debit != total_credit:
            raise forms.ValidationError(f'القيد غير متزن. إجمالي المدين: {total_debit}، إجمالي الدائن: {total_credit}')
        if total_debit == 0:
            raise forms.ValidationError('القيد صفري ولا يحتوي على مبالغ')

JournalLineFormSet = forms.inlineformset_factory(
    JournalEntry, JournalLine, form=JournalLineForm,
    formset=BaseJournalLineFormSet,
    extra=4, can_delete=True
)"""
    content = content.replace(old_formset_def, new_formset_def)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
    print("Forms updated successfully.")

if __name__ == '__main__':
    main()
