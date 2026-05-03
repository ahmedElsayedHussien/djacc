from django.db import models
from django.conf import settings

class CashBox(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    account = models.OneToOneField('core.Account', on_delete=models.PROTECT)
    currency = models.CharField(max_length=3, default='EGP')
    is_active = models.BooleanField(default=True)
    responsible_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    def __str__(self):
        return self.name

class BankAccount(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    account = models.OneToOneField('core.Account', on_delete=models.PROTECT)
    bank_name = models.CharField(max_length=200)
    account_number = models.CharField(max_length=50)
    iban = models.CharField(max_length=50, blank=True)
    currency = models.CharField(max_length=3, default='EGP')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.bank_name} - {self.name}"

class BankTransaction(models.Model):
    class TransactionType(models.TextChoices):
        DEPOSIT = 'deposit', 'إيداع'
        WITHDRAWAL = 'withdrawal', 'سحب'
        TRANSFER_IN = 'transfer_in', 'تحويل وارد'
        TRANSFER_OUT = 'transfer_out', 'تحويل صادر'
        BANK_CHARGE = 'charge', 'عمولة بنكية'
        INTEREST = 'interest', 'فائدة'

    number = models.CharField(max_length=50, unique=True)
    date = models.DateField()
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT)
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    description = models.TextField()
    reference = models.CharField(max_length=100, blank=True)
    is_reconciled = models.BooleanField(default=False)
    reconciled_at = models.DateTimeField(null=True, blank=True)
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return self.number

class BankReconciliation(models.Model):
    """تسوية بنكية"""
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT)
    statement_date = models.DateField()
    statement_balance = models.DecimalField(max_digits=18, decimal_places=2)
    book_balance = models.DecimalField(max_digits=18, decimal_places=2)
    difference = models.DecimalField(max_digits=18, decimal_places=2)
    is_reconciled = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    transactions = models.ManyToManyField(BankTransaction, blank=True)

class CashTransfer(models.Model):
    """تحويل بين خزن أو بين حسابات"""
    number = models.CharField(max_length=50, unique=True)
    date = models.DateField()
    from_cash_box = models.ForeignKey(CashBox, null=True, blank=True, on_delete=models.PROTECT, related_name='transfers_out')
    from_bank = models.ForeignKey(BankAccount, null=True, blank=True, on_delete=models.PROTECT, related_name='transfers_out')
    to_cash_box = models.ForeignKey(CashBox, null=True, blank=True, on_delete=models.PROTECT, related_name='transfers_in')
    to_bank = models.ForeignKey(BankAccount, null=True, blank=True, on_delete=models.PROTECT, related_name='transfers_in')
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    description = models.TextField()
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL)

    def clean(self):
        from django.core.exceptions import ValidationError
        source = self.from_cash_box or self.from_bank
        dest = self.to_cash_box or self.to_bank
        if not source:
            raise ValidationError('يجب تحديد مصدر التحويل (خزنة أو بنك)')
        if not dest:
            raise ValidationError('يجب تحديد وجهة التحويل (خزنة أو بنك)')
        
        # Prevent same source and destination
        if self.from_cash_box and self.from_cash_box == self.to_cash_box:
            raise ValidationError('لا يمكن التحويل من وإلى نفس الخزنة')
        if self.from_bank and self.from_bank == self.to_bank:
            raise ValidationError('لا يمكن التحويل من وإلى نفس الحساب البنكي')

    def __str__(self):
        return self.number
