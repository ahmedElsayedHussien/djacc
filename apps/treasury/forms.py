import re
from datetime import date
from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from apps.core.models import Account
from apps.sales.models import IntermediaryCompany
from .models import CashBox, BankAccount, CashTransfer, MobileWallet, BankReconciliation, BankTransaction
from .utils import get_available_cash_boxes

User = get_user_model()

class CashBoxForm(forms.ModelForm):
    class Meta:
        model = CashBox
        fields = ['code', 'name', 'currency', 'responsible_user', 'is_active']
        labels = {
            'code': 'كود الخزنة',
            'name': 'اسم الخزنة',
            'currency': 'العملة',
            'responsible_user': 'المستخدم المسؤول',
            'is_active': 'نشطة',
        }
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'كود الخزنة'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'currency': forms.TextInput(attrs={'class': 'form-control', 'value': 'EGP'}),
            'responsible_user': forms.Select(attrs={'class': 'form-select'}),
        }
    
    initial_balance = forms.DecimalField(label='رصيد أول المدة', initial=0, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}))
    initial_balance_type = forms.ChoiceField(label='نوع الرصيد', choices=[('debit', 'مدين'), ('credit', 'دائن')], initial='debit', widget=forms.Select(attrs={'class': 'form-select'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['responsible_user'].queryset = User.objects.filter(is_active=True)
        if self.instance and self.instance.pk and self.instance.account:
            self.fields['initial_balance'].initial = self.instance.account.initial_balance
            self.fields['initial_balance_type'].initial = self.instance.account.initial_balance_type

class BankAccountForm(forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = ['code', 'name', 'bank_name', 'account_number', 'iban', 'currency', 'is_active']
        labels = {
            'code': 'كود الحساب',
            'name': 'اسم الحساب',
            'bank_name': 'اسم البنك',
            'account_number': 'رقم الحساب',
            'iban': 'رقم IBAN',
            'currency': 'العملة',
            'is_active': 'نشط',
        }
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم وصفي للحساب مثل: حساب رواتب'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'account_number': forms.TextInput(attrs={'class': 'form-control'}),
            'iban': forms.TextInput(attrs={'class': 'form-control'}),
            'currency': forms.TextInput(attrs={'class': 'form-control', 'value': 'EGP'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'checked': 'checked'}),
        }

    initial_balance = forms.DecimalField(label='رصيد أول المدة', initial=0, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}))
    initial_balance_type = forms.ChoiceField(label='نوع الرصيد', choices=[('debit', 'مدين'), ('credit', 'دائن')], initial='debit', widget=forms.Select(attrs={'class': 'form-select'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.account:
            self.fields['initial_balance'].initial = self.instance.account.initial_balance
            self.fields['initial_balance_type'].initial = self.instance.account.initial_balance_type

class CashTransferForm(forms.ModelForm):
    class Meta:
        model = CashTransfer
        fields = ['date', 'from_cash_box', 'from_bank', 'from_intermediary', 'to_cash_box', 'to_bank', 'amount', 'description']
        labels = {
            'date': 'تاريخ التحويل',
            'from_cash_box': 'من خزنة',
            'from_bank': 'من حساب بنكي',
            'from_intermediary': 'من شركة وسيطة',
            'to_cash_box': 'إلى خزنة',
            'to_bank': 'إلى حساب بنكي',
            'amount': 'المبلغ',
            'description': 'البيان',
        }
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'from_cash_box': forms.Select(attrs={'class': 'form-select'}),
            'from_bank': forms.Select(attrs={'class': 'form-select'}),
            'from_intermediary': forms.Select(attrs={'class': 'form-select'}),
            'to_cash_box': forms.Select(attrs={'class': 'form-select'}),
            'to_bank': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            qs = get_available_cash_boxes(user)
            if 'from_cash_box' in self.fields:
                self.fields['from_cash_box'].queryset = qs
            if 'to_cash_box' in self.fields:
                self.fields['to_cash_box'].queryset = qs
                
        active_banks = BankAccount.objects.filter(is_active=True)
        active_intermediaries = IntermediaryCompany.objects.filter(is_active=True)
        if 'from_bank' in self.fields:
            self.fields['from_bank'].queryset = active_banks
        if 'to_bank' in self.fields:
            self.fields['to_bank'].queryset = active_banks
        if 'from_intermediary' in self.fields:
            self.fields['from_intermediary'].queryset = active_intermediaries

    def clean_date(self):
        d = self.cleaned_data.get('date')
        if d and d > date.today():
            raise forms.ValidationError('تاريخ التحويل لا يمكن أن يكون في المستقبل')
        return d

    def clean(self):
        cleaned_data = super().clean()
        from_cash = cleaned_data.get('from_cash_box')
        from_bank = cleaned_data.get('from_bank')
        from_intermediary = cleaned_data.get('from_intermediary')
        to_cash = cleaned_data.get('to_cash_box')
        to_bank = cleaned_data.get('to_bank')

        sources = [from_cash, from_bank, from_intermediary]
        active_sources = [s for s in sources if s is not None]

        if len(active_sources) > 1:
            self.add_error(None, 'لا يمكن تحديد أكثر من مصدر للتحويل')
        elif len(active_sources) == 0:
            self.add_error(None, 'يجب تحديد مصدر التحويل')
            
        if to_cash and to_bank:
            self.add_error('to_cash_box', 'لا يمكن تحديد وجهتين للتحويل')
            self.add_error('to_bank', 'لا يمكن تحديد وجهتين للتحويل')
        if not to_cash and not to_bank:
            self.add_error('to_cash_box', 'يجب تحديد وجهة التحويل')

        amount = cleaned_data.get('amount')
        if amount is not None and amount <= 0:
            self.add_error('amount', 'يجب أن يكون المبلغ أكبر من صفر')
        return cleaned_data

from .models import BankTransaction, BankReconciliation

class BankTransactionForm(forms.ModelForm):
    def clean_transaction_type(self):
        t_type = self.cleaned_data.get('transaction_type')
        if t_type in ['deposit', 'withdrawal']:
            raise forms.ValidationError('الإيداع والسحب النقدي يجب أن يتم عبر نظام التحويلات أو المقبوضات/المدفوعات')
        return t_type

    class Meta:
        model = BankTransaction
        fields = ['date', 'bank_account', 'transaction_type', 'amount', 'description', 'reference']
        labels = {
            'date': 'تاريخ العملية',
            'bank_account': 'الحساب البنكي',
            'transaction_type': 'نوع العملية',
            'amount': 'المبلغ',
            'description': 'البيان',
            'reference': 'رقم المرجع',
        }
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'bank_account': forms.Select(attrs={'class': 'form-select'}),
            'transaction_type': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'reference': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_date(self):
        d = self.cleaned_data.get('date')
        if d and d > date.today():
            raise forms.ValidationError('تاريخ العملية لا يمكن أن يكون في المستقبل')
        return d

    def clean_amount(self):
        amt = self.cleaned_data.get('amount')
        if amt is not None and amt <= 0:
            raise forms.ValidationError('المبلغ يجب أن يكون أكبر من صفر')
        return amt

class BankReconciliationForm(forms.ModelForm):
    class Meta:
        model = BankReconciliation
        fields = ['bank_account', 'statement_date', 'statement_balance', 'notes']
        labels = {
            'bank_account': 'الحساب البنكي',
            'statement_date': 'تاريخ كشف الحساب',
            'statement_balance': 'رصيد كشف الحساب',
            'notes': 'ملاحظات',
        }
        widgets = {
            'bank_account': forms.Select(attrs={'class': 'form-select'}),
            'statement_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'statement_balance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean_statement_date(self):
        d = self.cleaned_data.get('statement_date')
        if d and d > date.today():
            raise forms.ValidationError('تاريخ كشف الحساب لا يمكن أن يكون في المستقبل')
        return d

from .models import MobileWallet

class MobileWalletForm(forms.ModelForm):
    class Meta:
        model = MobileWallet
        fields = ['code', 'name', 'provider', 'mobile_number', 'currency', 'is_active']
        labels = {
            'code': 'كود المحفظة',
            'name': 'اسم المحفظة',
            'provider': 'مزود الخدمة',
            'mobile_number': 'رقم المحمول',
            'currency': 'العملة',
            'is_active': 'نشطة',
        }
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'كود المحفظة'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: محفظة الكاشير الأساسي'}),
            'provider': forms.Select(attrs={'class': 'form-select'}),
            'mobile_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: 01012345678'}),
            'currency': forms.TextInput(attrs={'class': 'form-control', 'value': 'EGP'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    initial_balance = forms.DecimalField(label='رصيد أول المدة', initial=0, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}))
    initial_balance_type = forms.ChoiceField(label='نوع الرصيد', choices=[('debit', 'مدين'), ('credit', 'دائن')], initial='debit', widget=forms.Select(attrs={'class': 'form-select'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.account:
            self.fields['initial_balance'].initial = self.instance.account.initial_balance
            self.fields['initial_balance_type'].initial = self.instance.account.initial_balance_type

    def clean_mobile_number(self):
        mobile = self.cleaned_data.get('mobile_number')
        if mobile and not re.match(r'^01[0-9]{9}$', mobile):
            raise ValidationError('رقم المحمول يجب أن يكون 11 رقم ويبدأ بـ 01 (مثال: 01012345678)')
        return mobile

class IntermediaryCompanyForm(forms.ModelForm):
    class Meta:
        model = IntermediaryCompany
        fields = ['name', 'account', 'commission_percent', 'is_active']
        labels = {
            'name': 'اسم الشركة الوسيطة',
            'account': 'الحساب المحاسبي',
            'commission_percent': 'نسبة العمولة (%)',
            'is_active': 'نشطة',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: شركة فوري'}),
            'account': forms.Select(attrs={'class': 'form-select'}),
            'commission_percent': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Find default account 1123
        default_acc = Account.objects.filter(code='1123').first()
        if default_acc:
            self.fields['account'].initial = default_acc
        
        self.fields['account'].queryset = Account.objects.filter(
            is_active=True, account_type='asset'
        ).order_by('code')

    def save(self, commit=True):
        with transaction.atomic():
            instance = super().save(commit=False)
            account = self.cleaned_data.get('account')
            
            if account and not account.is_leaf:
                parent = Account.objects.select_for_update().get(pk=account.pk)
                # Find next sequence code
                last_account = Account.objects.filter(parent=parent).order_by('-code').first()
                if last_account:
                    try:
                        last_seq = int(last_account.code[len(parent.code):])
                        next_seq = last_seq + 1
                    except (ValueError, IndexError):
                        next_seq = Account.objects.filter(parent=parent).count() + 1
                else:
                    next_seq = 1
                    
                account_code = f'{parent.code}{next_seq:02d}'
                
                # Create the leaf sub-account with the company's name
                company_name = self.cleaned_data.get('name')
                new_account = Account.objects.create(
                    code=account_code,
                    name=f'{parent.name} — {company_name}',
                    account_type=parent.account_type,
                    parent=parent,
                    is_leaf=True,
                    currency='EGP'
                )
                instance.account = new_account
            else:
                instance.account = account

            if commit:
                instance.save()
        return instance

