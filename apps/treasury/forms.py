from django import forms
from .models import CashBox, BankAccount, CashTransfer

class CashBoxForm(forms.ModelForm):
    class Meta:
        model = CashBox
        fields = ['code', 'name', 'currency', 'responsible_user']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'كود الخزنة'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'currency': forms.TextInput(attrs={'class': 'form-control', 'value': 'EGP'}),
            'responsible_user': forms.Select(attrs={'class': 'form-select'}),
        }
    
    initial_balance = forms.DecimalField(label='رصيد أول المدة', initial=0, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    initial_balance_type = forms.ChoiceField(label='نوع الرصيد', choices=[('debit', 'مدين'), ('credit', 'دائن')], initial='debit', widget=forms.Select(attrs={'class': 'form-select'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.fields['responsible_user'].queryset = User.objects.filter(is_active=True)
        if self.instance and self.instance.pk and self.instance.account:
            self.fields['initial_balance'].initial = self.instance.account.initial_balance
            self.fields['initial_balance_type'].initial = self.instance.account.initial_balance_type

class BankAccountForm(forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = ['code', 'name', 'bank_name', 'account_number', 'iban', 'currency']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم وصفي للحساب مثل: حساب رواتب'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'account_number': forms.TextInput(attrs={'class': 'form-control'}),
            'iban': forms.TextInput(attrs={'class': 'form-control'}),
            'currency': forms.TextInput(attrs={'class': 'form-control', 'value': 'EGP'}),
        }

    initial_balance = forms.DecimalField(label='رصيد أول المدة', initial=0, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    initial_balance_type = forms.ChoiceField(label='نوع الرصيد', choices=[('debit', 'مدين'), ('credit', 'دائن')], initial='debit', widget=forms.Select(attrs={'class': 'form-select'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.account:
            self.fields['initial_balance'].initial = self.instance.account.initial_balance
            self.fields['initial_balance_type'].initial = self.instance.account.initial_balance_type

class CashTransferForm(forms.ModelForm):
    class Meta:
        model = CashTransfer
        fields = ['date', 'from_cash_box', 'from_bank', 'to_cash_box', 'to_bank', 'amount', 'description']
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'from_cash_box': forms.Select(attrs={'class': 'form-select'}),
            'from_bank': forms.Select(attrs={'class': 'form-select'}),
            'to_cash_box': forms.Select(attrs={'class': 'form-select'}),
            'to_bank': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean(self):
        cleaned_data = super().clean()
        # Trigger model clean for source/destination validation
        instance = CashTransfer(**cleaned_data)
        try:
            instance.clean()
        except forms.ValidationError as e:
            raise forms.ValidationError(e.message)
        
        amount = cleaned_data.get('amount')
        if amount and amount <= 0:
            self.add_error('amount', 'يجب أن يكون المبلغ أكبر من صفر')
            
        return cleaned_data

from .models import BankTransaction, BankReconciliation

class BankTransactionForm(forms.ModelForm):
    class Meta:
        model = BankTransaction
        fields = ['date', 'bank_account', 'transaction_type', 'amount', 'description', 'reference']
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'bank_account': forms.Select(attrs={'class': 'form-select'}),
            'transaction_type': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'reference': forms.TextInput(attrs={'class': 'form-control'}),
        }

class BankReconciliationForm(forms.ModelForm):
    class Meta:
        model = BankReconciliation
        fields = ['bank_account', 'statement_date', 'statement_balance', 'book_balance', 'notes']
        widgets = {
            'bank_account': forms.Select(attrs={'class': 'form-select'}),
            'statement_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'statement_balance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'book_balance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
