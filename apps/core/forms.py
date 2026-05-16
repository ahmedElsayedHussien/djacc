from django import forms
from .models import Account, FiscalYear, CostCenter

class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ['code', 'name', 'account_type', 'parent', 'is_leaf', 'currency', 'initial_balance', 'initial_balance_type', 'notes']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: 1121001'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'account_type': forms.Select(attrs={'class': 'form-select'}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
            'is_leaf': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'currency': forms.TextInput(attrs={'class': 'form-control', 'value': 'EGP'}),
            'initial_balance': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'initial_balance_type': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Show only non-leaf accounts as parent options (can't nest under a leaf)
        self.fields['parent'].queryset = Account.objects.filter(
            is_leaf=False, is_active=True
        ).order_by('code')
        self.fields['parent'].empty_label = '--- لا يوجد أب (حساب جذر) ---'
        self.fields['parent'].required = False

    def clean_code(self):
        code = self.cleaned_data['code']
        qs = Account.objects.filter(code=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('كود الحساب مستخدم من قبل')
        return code

    def clean(self):
        cleaned = super().clean()
        parent = cleaned.get('parent')
        acc_type = cleaned.get('account_type')
        if parent and parent.account_type != acc_type:
            raise forms.ValidationError(
                'نوع الحساب يجب أن يطابق نوع الحساب الأب'
            )
        
        # Validation for leaf account transformation
        if cleaned.get('is_leaf') and self.instance.pk:
            if self.instance.children.exists():
                raise forms.ValidationError(
                    'لا يمكن تحويل الحساب لورقي لأن له حسابات فرعية'
                )
        return cleaned

class FiscalYearForm(forms.ModelForm):
    class Meta:
        model = FiscalYear
        fields = ['name', 'start_date', 'end_date']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: السنة المالية 2025'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if start and end:
            if end <= start:
                raise forms.ValidationError('تاريخ النهاية يجب أن يكون بعد تاريخ البداية')
            # Check no overlap with existing years
            overlapping = FiscalYear.objects.filter(
                start_date__lte=end, end_date__gte=start
            )
            if self.instance.pk:
                overlapping = overlapping.exclude(pk=self.instance.pk)
            if overlapping.exists():
                raise forms.ValidationError('هذه الفترة تتداخل مع سنة مالية موجودة')
        return cleaned

class CostCenterForm(forms.ModelForm):
    class Meta:
        model = CostCenter
        fields = ['code', 'name', 'center_type', 'parent', 'is_leaf', 'description', 'is_active']
        widgets = {
            'code':        forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: 101'}),
            'name':        forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: فرع القاهرة / قسم المبيعات'}),
            'center_type': forms.Select(attrs={'class': 'form-select'}),
            'parent':      forms.Select(attrs={'class': 'form-select'}),
            'is_leaf':     forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'is_active':   forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        help_texts = {
            'name': 'أجب عن سؤال: "مَن الذي استفاد بهذا الصرف؟" (فرع، قسم، إدارة).',
            'is_leaf': 'يجب تفعيل هذا الخيار إذا كنت تريد تحميل مصروفات أو إيرادات مباشرة على هذا المركز.',
            'center_type': 'يستخدم لتجميع مراكز التكلفة المتشابهة في تقارير الأرباح والخسائر.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parent'].queryset = CostCenter.objects.all().order_by('code')
        self.fields['parent'].empty_label = '--- لا يوجد (مركز رئيسي) ---'
        self.fields['parent'].required = False

from .models import JournalEntry, JournalLine

from .models import JournalEntry, JournalLine, TaxType

class TaxTypeForm(forms.ModelForm):
    class Meta:
        model = TaxType
        fields = ['name', 'category', 'rate', 'account']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'account': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Show only leaf accounts that are related to taxes (Asset-side 1122 or Liability-side 212)
        from django.db.models import Q
        self.fields['account'].queryset = Account.objects.filter(
            Q(code__startswith='1122') | Q(code__startswith='212'),
            is_leaf=True
        ).order_by('code')

class JournalEntryForm(forms.ModelForm):
    class Meta:
        model = JournalEntry
        fields = ['date', 'entry_type', 'description', 'reference']
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'entry_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'reference': forms.TextInput(attrs={'class': 'form-control'}),
        }

class JournalLineForm(forms.ModelForm):
    class Meta:
        model = JournalLine
        fields = ['account', 'cost_center', 'debit', 'credit', 'description']
        widgets = {
            'account': forms.Select(attrs={'class': 'form-select select2'}),
            'cost_center': forms.Select(attrs={'class': 'form-select'}),
            'debit': forms.NumberInput(attrs={'class': 'form-control debit-input', 'step': '0.01'}),
            'credit': forms.NumberInput(attrs={'class': 'form-control credit-input', 'step': '0.01'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['account'].queryset = Account.objects.filter(
            is_leaf=True, is_active=True
        ).order_by('code')
        self.fields['cost_center'].queryset = CostCenter.objects.filter(
            is_active=True, is_leaf=True
        ).order_by('code')

JournalLineFormSet = forms.inlineformset_factory(
    JournalEntry, JournalLine, form=JournalLineForm,
    extra=4, can_delete=True
)
