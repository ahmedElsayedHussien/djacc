import re

def main():
    file_path = 'apps/treasury/forms.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    # 1. IntermediaryCompanyForm is_leaf constraint
    old_comp_init = """        self.fields['account'].queryset = Account.objects.filter(
            is_active=True, account_type='asset', is_leaf=True
        ).order_by('code')"""
    new_comp_init = """        self.fields['account'].queryset = Account.objects.filter(
            is_active=True, account_type='asset'
        ).order_by('code')"""
    content = content.replace(old_comp_init, new_comp_init)

    # 2. CashBoxForm, BankAccountForm, MobileWalletForm min_value=0
    # Note: These forms might use django forms.DecimalField without min_value.
    # We can inject min_value=0 via regex or replace. Let's try replace first.
    old_initial_bal = "initial_balance = forms.DecimalField(label='رصيد أول المدة', initial=0, widget=forms.NumberInput(attrs={'class': 'form-control'}))"
    new_initial_bal = "initial_balance = forms.DecimalField(label='رصيد أول المدة', initial=0, min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}))"
    content = content.replace(old_initial_bal, new_initial_bal)

    # 3. BankTransactionForm and BankReconciliationForm active banks and clean
    old_trans_init = """        super().__init__(*args, **kwargs)
        if 'date' in self.initial:"""
    new_trans_init = """        super().__init__(*args, **kwargs)
        self.fields['bank_account'].queryset = BankAccount.objects.filter(is_active=True)
        if 'date' in self.initial:"""
    content = content.replace(old_trans_init, new_trans_init)
    
    old_recon_init = """        super().__init__(*args, **kwargs)
        if 'statement_date' in self.initial:"""
    new_recon_init = """        super().__init__(*args, **kwargs)
        self.fields['bank_account'].queryset = BankAccount.objects.filter(is_active=True)
        if 'statement_date' in self.initial:"""
    content = content.replace(old_recon_init, new_recon_init)

    # BankTransactionForm clean_transaction_type
    old_btrans_meta = "    class Meta:\n        model = BankTransaction"
    new_btrans_meta = """    def clean_transaction_type(self):
        t_type = self.cleaned_data.get('transaction_type')
        if t_type in ['deposit', 'withdrawal']:
            raise forms.ValidationError('الإيداع والسحب النقدي يجب أن يتم عبر نظام التحويلات أو المقبوضات/المدفوعات')
        return t_type

    class Meta:
        model = BankTransaction"""
    content = content.replace(old_btrans_meta, new_btrans_meta)

    # BankReconciliationForm clean overlapping
    old_recon_clean = """    def clean(self):
        cleaned_data = super().clean()
        stmt_bal = cleaned_data.get('statement_balance')
        bk_bal = cleaned_data.get('book_balance')
        
        if stmt_bal is not None and bk_bal is not None:
            cleaned_data['difference'] = stmt_bal - bk_bal
            
        return cleaned_data"""
    new_recon_clean = """    def clean(self):
        cleaned_data = super().clean()
        stmt_bal = cleaned_data.get('statement_balance')
        bk_bal = cleaned_data.get('book_balance')
        
        if stmt_bal is not None and bk_bal is not None:
            cleaned_data['difference'] = stmt_bal - bk_bal
            
        bank_account = cleaned_data.get('bank_account')
        statement_date = cleaned_data.get('statement_date')
        if bank_account and statement_date:
            from .models import BankReconciliation
            if BankReconciliation.objects.filter(
                bank_account=bank_account, 
                statement_date__gte=statement_date,
                status=BankReconciliation.Status.COMPLETED
            ).exists():
                self.add_error('statement_date', 'يوجد تسوية بنكية منتهية في هذا التاريخ أو تاريخ أحدث')
                
        return cleaned_data"""
    content = content.replace(old_recon_clean, new_recon_clean)

    # 4. CashTransferForm active banks and circular/currency checks
    old_xfer_init = """        if user:
            qs = get_available_cash_boxes(user)
            if 'from_cash_box' in self.fields:
                self.fields['from_cash_box'].queryset = qs
            if 'to_cash_box' in self.fields:
                self.fields['to_cash_box'].queryset = qs"""
    new_xfer_init = """        if user:
            qs = get_available_cash_boxes(user)
            if 'from_cash_box' in self.fields:
                self.fields['from_cash_box'].queryset = qs
            if 'to_cash_box' in self.fields:
                self.fields['to_cash_box'].queryset = qs
                
        active_banks = BankAccount.objects.filter(is_active=True)
        if 'from_bank' in self.fields:
            self.fields['from_bank'].queryset = active_banks
        if 'to_bank' in self.fields:
            self.fields['to_bank'].queryset = active_banks"""
    content = content.replace(old_xfer_init, new_xfer_init)

    old_xfer_clean = """        # If transfer by cash box, ensure user has access
        if from_cash:
            # Additional logic can be placed here if needed
            pass
            
        if to_cash:
            pass"""
    new_xfer_clean = """        if from_cash and to_cash and from_cash == to_cash:
            self.add_error('to_cash_box', 'لا يمكن التحويل لنفس الخزنة')
        if from_bank and to_bank and from_bank == to_bank:
            self.add_error('to_bank', 'لا يمكن التحويل لنفس الحساب البنكي')
            
        source_currency = getattr(from_cash, 'currency', None) or getattr(from_bank, 'currency', None)
        dest_currency = getattr(to_cash, 'currency', None) or getattr(to_bank, 'currency', None)
        if source_currency and dest_currency and source_currency != dest_currency:
            self.add_error(None, 'لا يمكن التحويل بين عملات مختلفة مباشرة')"""
    content = content.replace(old_xfer_clean, new_xfer_clean)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Forms patched.")

if __name__ == '__main__':
    main()
