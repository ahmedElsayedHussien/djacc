from django.db import models
from django.conf import settings

class ExpenseCategory(models.Model):
    name = models.CharField(max_length=200)
    account = models.ForeignKey('core.Account', on_delete=models.PROTECT)

    def __str__(self):
        return self.name

class Expense(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        APPROVED = 'approved', 'معتمد'
        POSTED = 'posted', 'مرحّل'
        REJECTED = 'rejected', 'مرفوض'

    number = models.CharField(max_length=50, unique=True)
    date = models.DateField()
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT)
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    tax_type = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT, related_name='expenses1')
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_type2 = models.ForeignKey('core.TaxType', null=True, blank=True, on_delete=models.PROTECT, related_name='expenses2')
    tax_percent2 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=18, decimal_places=2, help_text="المبلغ المدفوع فعلياً (الصافي)")
    description = models.TextField()
    cost_center = models.ForeignKey('core.CostCenter', null=True, blank=True, on_delete=models.PROTECT)
    payment_method = models.CharField(max_length=20, choices=[('cash','نقدي'),('bank','بنك'),('custody','عهدة')])
    bank_account = models.ForeignKey('treasury.BankAccount', null=True, blank=True, on_delete=models.PROTECT)
    cash_box = models.ForeignKey('treasury.CashBox', null=True, blank=True, on_delete=models.PROTECT)
    custody = models.ForeignKey('Custody', null=True, blank=True, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_expenses')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='approved_expenses')
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL)
    attachment = models.FileField(upload_to='expenses/', blank=True)
    settlement = models.ForeignKey('CustodySettlement', null=True, blank=True, on_delete=models.SET_NULL, related_name='expenses')

    def __str__(self):
        return self.number

class Custody(models.Model):
    """
    عهدة — Cash advance given to an employee to cover expenses.
    """
    class Status(models.TextChoices):
        OPEN = 'open', 'مفتوحة'
        PARTIALLY_SETTLED = 'partial', 'مسواة جزئياً'
        SETTLED = 'settled', 'مسواة'

    number = models.CharField(max_length=50, unique=True)
    date = models.DateField()
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    purpose = models.TextField()
    account = models.ForeignKey('core.Account', on_delete=models.PROTECT)   # Employee advance account
    cash_box = models.ForeignKey('treasury.CashBox', on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    settled_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f"{self.number} - {self.employee.username}"

class CustodySettlement(models.Model):
    """تسوية عهدة"""
    custody = models.ForeignKey(Custody, on_delete=models.PROTECT, related_name='settlements')
    date = models.DateField()
    expenses_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)    # Spent amount with receipts
    returned_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)    # Cash returned
    cash_box = models.ForeignKey('treasury.CashBox', on_delete=models.PROTECT, null=True, blank=True)
    notes = models.TextField(blank=True)
    is_posted = models.BooleanField(default=False)
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL)
