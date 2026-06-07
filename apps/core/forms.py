from django import forms
from django.db.models import Q
from django.utils import timezone
from .models import Account, FiscalYear, CostCenter

class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ['code', 'name', 'account_type', 'parent', 'is_leaf', 'currency', 'initial_balance', 'initial_balance_type', 'notes']
        labels = {
            'code': 'كود الحساب',
            'name': 'اسم الحساب',
            'account_type': 'نوع الحساب',
            'parent': 'الحساب الأب',
            'is_leaf': 'حساب ورقي (نهائي)',
            'currency': 'العملة',
            'initial_balance': 'الرصيد الافتتاحي',
            'initial_balance_type': 'طبيعة الرصيد الافتتاحي',
            'notes': 'ملاحظات',
        }
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

    def clean_initial_balance(self):
        bal = self.cleaned_data.get('initial_balance')
        if bal is not None and bal < 0:
            raise forms.ValidationError('الرصيد الافتتاحي لا يمكن أن يكون سالباً')
        return bal

    def clean(self):
        cleaned = super().clean()
        parent = cleaned.get('parent')
        code = cleaned.get('code')
        acc_type = cleaned.get('account_type')
        is_leaf = cleaned.get('is_leaf')
        initial_balance = cleaned.get('initial_balance')

        if parent and code and not code.startswith(parent.code):
            raise forms.ValidationError(
                f'كود الحساب ({code}) يجب أن يبدأ بكود الأب ({parent.code})'
            )
        if parent and parent.account_type != acc_type:
            raise forms.ValidationError(
                'نوع الحساب يجب أن يطابق نوع الحساب الأب'
            )
        if parent and parent.is_leaf:
            raise forms.ValidationError(
                'لا يمكن إضافة حساب فرعي لحساب ورقي (leaf)'
            )
        if is_leaf and self.instance.pk and self.instance.children.exists():
            raise forms.ValidationError(
                'لا يمكن تحويل الحساب لورقي لأن له حسابات فرعية'
            )
        if not is_leaf and initial_balance and initial_balance > 0:
            self.add_error('initial_balance', 'الحساب غير الورقي (غير leaf) لا يمكن أن يكون له رصيد افتتاحي')
        return cleaned

class FiscalYearForm(forms.ModelForm):
    class Meta:
        model = FiscalYear
        fields = ['name', 'start_date', 'end_date']
        labels = {
            'name': 'اسم السنة المالية',
            'start_date': 'تاريخ البداية',
            'end_date': 'تاريخ النهاية',
        }
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
        labels = {
            'code': 'كود المركز',
            'name': 'اسم مركز التكلفة',
            'center_type': 'نوع المركز',
            'parent': 'المركز الأب',
            'is_leaf': 'مركز نهائي (leaf)',
            'description': 'وصف',
            'is_active': 'نشط',
        }
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
        self.fields['parent'].queryset = CostCenter.objects.filter(is_leaf=False, is_active=True).order_by('code')
        self.fields['parent'].empty_label = '--- لا يوجد (مركز رئيسي) ---'
        self.fields['parent'].required = False

    def clean_code(self):
        code = self.cleaned_data.get('code')
        qs = CostCenter.objects.filter(code=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('كود مركز التكلفة مستخدم من قبل')
        return code

    def clean(self):
        cleaned = super().clean()
        parent = cleaned.get('parent')
        center_type = cleaned.get('center_type')
        is_leaf = cleaned.get('is_leaf')

        if parent and parent.is_leaf:
            raise forms.ValidationError('لا يمكن إضافة مركز فرعي لمركز طرفي (leaf)')
        if parent and center_type and parent.center_type and center_type != parent.center_type:
            raise forms.ValidationError('نوع المركز يجب أن يطابق نوع المركز الأب')
        if is_leaf and self.instance.pk and self.instance.children.exists():
            raise forms.ValidationError('لا يمكن تحويل المركز لطرفي (leaf) وله مراكز فرعية')
        return cleaned

from .models import JournalEntry, JournalLine

from .models import JournalEntry, JournalLine, TaxType

class TaxTypeForm(forms.ModelForm):
    class Meta:
        model = TaxType
        fields = ['name', 'category', 'rate', 'account']
        labels = {
            'name': 'اسم الضريبة',
            'category': 'تصنيف الضريبة',
            'rate': 'النسبة (%)',
            'account': 'الحساب المحاسبي',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'account': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Show only leaf accounts that are related to taxes (Asset-side 1122 or Liability-side 212)
        self.fields['account'].queryset = Account.objects.filter(
            is_leaf=True, is_active=True
        ).order_by('code')

    def clean_rate(self):
        rate = self.cleaned_data.get('rate')
        if rate is not None and (rate < 0 or rate > 100):
            raise forms.ValidationError('نسبة الضريبة يجب أن تكون بين 0 و 100')
        return rate

class JournalEntryForm(forms.ModelForm):
    class Meta:
        model = JournalEntry
        fields = ['date', 'entry_type', 'description', 'reference']
        labels = {
            'date': 'تاريخ القيد',
            'entry_type': 'نوع القيد',
            'description': 'البيان',
            'reference': 'رقم المستند المرجعي',
        }
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'entry_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'reference': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['entry_type'].choices = [
            (JournalEntry.EntryType.MANUAL.value, JournalEntry.EntryType.MANUAL.label),
        ]

    def clean_date(self):
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
        return d

class JournalLineForm(forms.ModelForm):
    class Meta:
        model = JournalLine
        fields = ['account', 'cost_center', 'debit', 'credit', 'description']
        labels = {
            'account': 'الحساب',
            'cost_center': 'مركز التكلفة',
            'debit': 'مدين',
            'credit': 'دائن',
            'description': 'بيان السطر',
        }
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

    def clean_debit(self):
        d = self.cleaned_data.get('debit')
        if d is not None and d < 0:
            raise forms.ValidationError('قيمة المدين لا يمكن أن تكون سالبة')
        return d

    def clean_credit(self):
        c = self.cleaned_data.get('credit')
        if c is not None and c < 0:
            raise forms.ValidationError('قيمة الدائن لا يمكن أن تكون سالبة')
        return c

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        debit = cleaned.get('debit')
        credit = cleaned.get('credit')
        if debit and credit and debit > 0 and credit > 0:
            raise forms.ValidationError('السطر لا يمكن أن يكون مدين ودائن في نفس الوقت')
        if (debit is None or debit == 0) and (credit is None or credit == 0):
            raise forms.ValidationError('يجب إدخال قيمة مدين أو دائن')
        account = cleaned.get('account')
        if account:
            if not account.is_leaf:
                raise forms.ValidationError({'account': 'لا يمكن الترحيل لحساب غير ورقي (non-leaf)'})
            if not account.is_active:
                raise forms.ValidationError({'account': 'الحساب غير نشط'})
        cost_center = cleaned.get('cost_center')
        if cost_center:
            if not cost_center.is_leaf:
                raise forms.ValidationError({'cost_center': 'مركز التكلفة يجب أن يكون طرفياً (leaf)'})
            if not cost_center.is_active:
                raise forms.ValidationError({'cost_center': 'مركز التكلفة غير نشط'})
        return cleaned

from decimal import Decimal

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
            
        # Prevent same account and cost center from appearing on both debit and credit sides
        debit_keys = set()
        credit_keys = set()
        for f in self.forms:
            if not self._should_delete_form(f) and f.cleaned_data:
                acc = f.cleaned_data.get('account')
                cc = f.cleaned_data.get('cost_center')
                debit_val = f.cleaned_data.get('debit') or 0
                credit_val = f.cleaned_data.get('credit') or 0
                
                if acc:
                    key = (acc.pk, cc.pk if cc else None)
                    if debit_val > 0:
                        debit_keys.add(key)
                    if credit_val > 0:
                        credit_keys.add(key)
                        
        overlap = debit_keys.intersection(credit_keys)
        if overlap:
            raise forms.ValidationError('ثغرة مرفوضة: لا يمكن استخدام نفس الحساب ونفس مركز التكلفة كمدين ودائن معاً في نفس القيد.')

JournalLineFormSet = forms.inlineformset_factory(
    JournalEntry, JournalLine, form=JournalLineForm,
    formset=BaseJournalLineFormSet,
    extra=4, can_delete=True
)
