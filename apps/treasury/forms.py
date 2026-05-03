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
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
