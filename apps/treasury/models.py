from datetime import date
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
from apps.core.models import ConcurrencyModel
from apps.core.utils import get_account_balance

class CashBox(ConcurrencyModel):
    code = models.CharField(max_length=20, unique=True, verbose_name="كود الخزينة")
    name = models.CharField(max_length=200, verbose_name="اسم الخزينة")
    account = models.OneToOneField('core.Account', on_delete=models.PROTECT, verbose_name="الحساب المحاسبي")
    currency = models.CharField(max_length=3, default='EGP', verbose_name="العملة")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    responsible_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="المسؤول عنها")
    
    @property
    def current_balance(self):
        return get_account_balance(self.account, as_of_date=date.today())

    class Meta:
        ordering = ['code']

    def __str__(self):
        return self.name

    def clean(self):
        if not self.code:
            raise ValidationError({'code': 'كود الخزينة مطلوب'})
        if not self.name:
            raise ValidationError({'name': 'اسم الخزينة مطلوب'})

class BankAccount(ConcurrencyModel):
    code = models.CharField(max_length=20, unique=True, verbose_name="كود الحساب")
    name = models.CharField(max_length=200, verbose_name="اسم الحساب (داخلي)")
    account = models.OneToOneField('core.Account', on_delete=models.PROTECT, verbose_name="الحساب المحاسبي")
    bank_name = models.CharField(max_length=200, verbose_name="اسم البنك")
    account_number = models.CharField(max_length=50, verbose_name="رقم الحساب البنكي")
    iban = models.CharField(max_length=50, blank=True, verbose_name="IBAN")
    currency = models.CharField(max_length=3, default='EGP', verbose_name="العملة")
    is_active = models.BooleanField(default=True, verbose_name="نشط")

    @property
    def current_balance(self):
        return get_account_balance(self.account, as_of_date=date.today())

    class Meta:
        ordering = ['bank_name', 'name']

    def __str__(self):
        return f"{self.bank_name} - {self.name}"

    def clean(self):
        if not self.code:
            raise ValidationError({'code': 'كود الحساب مطلوب'})
        if not self.account_number:
            raise ValidationError({'account_number': 'رقم الحساب البنكي مطلوب'})

class BankTransaction(ConcurrencyModel):
    class TransactionType(models.TextChoices):
        DEPOSIT = 'deposit', 'إيداع'
        WITHDRAWAL = 'withdrawal', 'سحب'
        TRANSFER_IN = 'transfer_in', 'تحويل وارد'
        TRANSFER_OUT = 'transfer_out', 'تحويل صادر'
        BANK_CHARGE = 'charge', 'عمولة بنكية'
        INTEREST = 'interest', 'فائدة'

    number = models.CharField(max_length=50, unique=True, verbose_name="رقم العملية")
    date = models.DateField(verbose_name="تاريخ العملية")
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, verbose_name="الحساب البنكي")
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices, verbose_name="نوع العملية")
    amount = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))], verbose_name="المبلغ")
    description = models.TextField(verbose_name="الوصف/البيان")
    reference = models.CharField(max_length=100, blank=True, verbose_name="المرجع (رقم الحركة)")
    is_reconciled = models.BooleanField(default=False, verbose_name="تمت التسوية")
    reconciled_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ التسوية")
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="قيد اليومية")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, verbose_name="أنشئ بواسطة")

    class Meta:
        ordering = ['-date', '-id']

    def __str__(self):
        return self.number

class BankReconciliation(ConcurrencyModel):
    """تسوية بنكية"""
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        COMPLETED = 'completed', 'مكتملة (مطابقة)'

    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, verbose_name="الحساب البنكي")
    statement_date = models.DateField(verbose_name="تاريخ كشف الحساب")
    statement_balance = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="الرصيد في الكشف")
    book_balance = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="الرصيد في الدفاتر")
    difference = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="الفارق")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, verbose_name="الحالة")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    transactions = models.ManyToManyField(BankTransaction, blank=True, verbose_name="العمليات المتضمنة")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, verbose_name="أنشئ بواسطة")

    class Meta:
        ordering = ['-statement_date', '-id']

    @property
    def is_reconciled(self):
        return self.status == self.Status.COMPLETED

    def clean(self):
        super().clean()
        if self.statement_date and self.statement_date > date.today():
            raise ValidationError({'statement_date': 'تاريخ كشف الحساب لا يمكن أن يكون في المستقبل'})
        if self.statement_balance is not None and self.book_balance is not None:
            self.difference = self.statement_balance - self.book_balance

    def save(self, *args, **kwargs):
        self.full_clean()
        self.difference = self.statement_balance - self.book_balance
        super().save(*args, **kwargs)

class CashTransfer(ConcurrencyModel):
    """تحويل بين خزن أو بين حسابات"""
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        PENDING = 'pending', 'قيد التحويل (صادر)'
        COMPLETED = 'completed', 'مكتمل (مستلم)'
        CANCELLED = 'cancelled', 'ملغي'

    number = models.CharField(max_length=50, unique=True, verbose_name="رقم التحويل")
    date = models.DateField(verbose_name="تاريخ التحويل")
    from_cash_box = models.ForeignKey(CashBox, null=True, blank=True, on_delete=models.PROTECT, related_name='transfers_out', verbose_name="من خزينة")
    from_bank = models.ForeignKey(BankAccount, null=True, blank=True, on_delete=models.PROTECT, related_name='transfers_out', verbose_name="من بنك")
    to_cash_box = models.ForeignKey(CashBox, null=True, blank=True, on_delete=models.PROTECT, related_name='transfers_in', verbose_name="إلى خزينة")
    to_bank = models.ForeignKey(BankAccount, null=True, blank=True, on_delete=models.PROTECT, related_name='transfers_in', verbose_name="إلى بنك")
    amount = models.DecimalField(
        max_digits=18, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name="المبلغ"
    )
    description = models.TextField(verbose_name="الوصف")
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, verbose_name="الحالة")
    
    # القيود المحاسبية
    issue_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, related_name='transfer_issue', verbose_name="قيد الصرف")
    receive_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, related_name='transfer_receive', verbose_name="قيد الاستلام")
    
    # بيانات الاستلام
    received_at = models.DateTimeField(null=True, blank=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='received_transfers')

    def clean(self):
        if self.date and self.date > date.today():
            raise ValidationError({'date': 'تاريخ التحويل لا يمكن أن يكون في المستقبل'})

        if self.from_cash_box and self.from_bank:
            raise ValidationError('لا يمكن تحديد مصدرين للتحويل (خزنة وبنك معاً)')
        if self.to_cash_box and self.to_bank:
            raise ValidationError('لا يمكن تحديد وجهتين للتحويل (خزنة وبنك معاً)')

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

    @property
    def from_source(self):
        return str(self.from_cash_box or self.from_bank or '')

    @property
    def to_destination(self):
        return str(self.to_cash_box or self.to_bank or '')

    class Meta:
        ordering = ['-date', '-id']

    def __str__(self):
        return self.number

class MobileWallet(ConcurrencyModel):
    class ProviderChoices(models.TextChoices):
        VODAFONE = 'vodafone', 'فودافون كاش (Vodafone Cash)'
        INSTAPAY = 'instapay', 'إنستاباي (InstaPay)'
        FAWRY = 'fawry', 'فوري (Fawry)'
        ORANGE = 'orange', 'أورنج كاش (Orange Cash)'
        ETISALAT = 'etisalat', 'اتصالات كاش (Etisalat Cash)'
        WEPAY = 'wepay', 'وي كاش (WE Pay)'
        OTHER = 'other', 'أخرى / محفظة بنكية'

    code = models.CharField(max_length=20, unique=True, verbose_name="كود المحفظة")
    name = models.CharField(max_length=200, verbose_name="اسم المحفظة (الداخلي)")
    account = models.OneToOneField('core.Account', on_delete=models.PROTECT, verbose_name="الحساب المحاسبي")
    provider = models.CharField(
        max_length=100, 
        choices=ProviderChoices.choices, 
        default=ProviderChoices.VODAFONE, 
        verbose_name="مزود الخدمة"
    )
    mobile_number = models.CharField(max_length=20, verbose_name="رقم الهاتف المرتبط")
    currency = models.CharField(max_length=3, default='EGP', verbose_name="العملة")
    is_active = models.BooleanField(default=True, verbose_name="نشط")

    class Meta:
        verbose_name = "محفظة إلكترونية"
        verbose_name_plural = "المحافظ الإلكترونية"

    @property
    def current_balance(self):
        return get_account_balance(self.account, as_of_date=date.today())

    def __str__(self):
        return f"{self.provider} - {self.name} ({self.mobile_number})"
