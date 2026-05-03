# Django Accounting System — Comprehensive Project Plan

## Project Overview

Build a full-featured, multi-activity web-based accounting system using Django. The system must serve all financial aspects of a multi-activity company including sales, purchases, inventory, custody (عهدة), expenses, banks, and treasury. All financial transactions must comply with **double-entry bookkeeping** (القيد المزدوج).

---

## Technology Stack

| Layer | Technology |
|---|---|
| Backend Framework | Django 5.x |
| Database | mysql | but we will use sqlite for now and later we will migrate to mysql  
| API Layer | Django REST Framework (DRF) |
| Task Queue | Celery + Redis |
| Frontend | Bootstrap 5 + HTMX (no separate SPA framework) |
| PDF Export | WeasyPrint |
| Authentication | Django Allauth + custom permission system |
| Testing | pytest-django |
| Deployment | Docker + Nginx + Gunicorn |

---

## Project Structure

```
accounting_project/
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── urls.py
│   ├── wsgi.py
│   └── celery.py
├── apps/
│   ├── core/            # Chart of accounts, journal entries, fiscal year
│   ├── sales/           # Invoices, customers, receipts
│   ├── purchases/       # Purchase orders, suppliers, payments
│   ├── inventory/       # Items, warehouses, stock movements
│   ├── expenses/        # General expenses, custody (عهدة)
│   ├── treasury/        # Cash boxes, bank accounts
│   ├── reports/         # Financial statements
│   └── api/             # REST API endpoints
├── templates/
├── static/
├── media/
├── requirements/
│   ├── base.txt
│   ├── development.txt
│   └── production.txt
└── manage.py
```

---

## App 1: `core` — Accounting Engine

### Purpose
The foundation of the entire system. Every financial transaction in every other app must create a `JournalEntry` through this app.

### Models

```python
# apps/core/models.py

class AccountType(models.TextChoices):
    ASSET = 'asset', 'أصول'
    LIABILITY = 'liability', 'خصوم'
    EQUITY = 'equity', 'حقوق ملكية'
    REVENUE = 'revenue', 'إيرادات'
    EXPENSE = 'expense', 'مصروفات'

class Account(models.Model):
    """
    Chart of Accounts (دليل الحسابات)
    Supports multi-level hierarchy via parent FK (self-referential).
    """
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    account_type = models.CharField(max_length=20, choices=AccountType.choices)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='children')
    is_leaf = models.BooleanField(default=True)          # Only leaf accounts accept journal lines
    currency = models.CharField(max_length=3, default='EGP')
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class FiscalYear(models.Model):
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    is_closed = models.BooleanField(default=False)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    closed_at = models.DateTimeField(null=True, blank=True)

class CostCenter(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT)
    is_active = models.BooleanField(default=True)

class JournalEntry(models.Model):
    """
    القيد اليومي — header record.
    Lines must always balance: sum(debit) == sum(credit).
    """
    class EntryType(models.TextChoices):
        MANUAL = 'manual', 'يدوي'
        SALE = 'sale', 'مبيعات'
        PURCHASE = 'purchase', 'مشتريات'
        RECEIPT = 'receipt', 'تحصيل'
        PAYMENT = 'payment', 'سداد'
        EXPENSE = 'expense', 'مصروف'
        BANK = 'bank', 'بنك'
        CUSTODY = 'custody', 'عهدة'
        INVENTORY = 'inventory', 'مخزون'
        OPENING = 'opening', 'افتتاحي'
        CLOSING = 'closing', 'إقفال'

    number = models.CharField(max_length=50, unique=True)  # Auto-generated
    date = models.DateField()
    fiscal_year = models.ForeignKey(FiscalYear, on_delete=models.PROTECT)
    entry_type = models.CharField(max_length=20, choices=EntryType.choices)
    description = models.TextField()
    reference = models.CharField(max_length=100, blank=True)   # Source document number
    content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    source_document = GenericForeignKey('content_type', 'object_id')  # Link back to invoice/payment etc.
    is_posted = models.BooleanField(default=False)
    is_reversed = models.BooleanField(default=False)
    reversed_by = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        total_debit = self.lines.aggregate(total=Sum('debit'))['total'] or 0
        total_credit = self.lines.aggregate(total=Sum('credit'))['total'] or 0
        if total_debit != total_credit:
            raise ValidationError('القيد غير متوازن: المدين لا يساوي الدائن')

class JournalLine(models.Model):
    """
    سطر القيد — always created in pairs (debit + credit).
    Either debit > 0 OR credit > 0, never both.
    """
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    cost_center = models.ForeignKey(CostCenter, null=True, blank=True, on_delete=models.SET_NULL)
    description = models.CharField(max_length=300, blank=True)
    debit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='EGP')
    exchange_rate = models.DecimalField(max_digits=12, decimal_places=6, default=1)

    def clean(self):
        if self.debit > 0 and self.credit > 0:
            raise ValidationError('السطر لا يمكن أن يكون مدين ودائن في نفس الوقت')
        if self.debit == 0 and self.credit == 0:
            raise ValidationError('يجب إدخال قيمة مدين أو دائن')
```

### Core Service: `JournalService`

```python
# apps/core/services.py

class JournalService:
    """
    Central service for creating journal entries.
    All apps must use this service — never create JournalEntry directly.
    Wraps everything in atomic transactions.
    """

    @staticmethod
    @transaction.atomic
    def create_entry(
        date: date,
        entry_type: str,
        description: str,
        lines: list[dict],          # [{'account': Account, 'debit': Decimal, 'credit': Decimal, 'description': str}]
        source_document=None,
        reference: str = '',
        created_by=None,
    ) -> JournalEntry:
        fiscal_year = FiscalYear.objects.get(start_date__lte=date, end_date__gte=date, is_closed=False)
        entry = JournalEntry.objects.create(
            number=JournalService._generate_number(entry_type),
            date=date,
            fiscal_year=fiscal_year,
            entry_type=entry_type,
            description=description,
            reference=reference,
            created_by=created_by,
        )
        if source_document:
            entry.content_type = ContentType.objects.get_for_model(source_document)
            entry.object_id = source_document.pk
            entry.save()

        for line_data in lines:
            JournalLine.objects.create(entry=entry, **line_data)

        entry.clean()   # Validates debit == credit
        entry.is_posted = True
        entry.save()
        return entry

    @staticmethod
    @transaction.atomic
    def reverse_entry(entry: JournalEntry, date: date, created_by) -> JournalEntry:
        reversal_lines = []
        for line in entry.lines.all():
            reversal_lines.append({
                'account': line.account,
                'debit': line.credit,    # Swap debit/credit
                'credit': line.debit,
                'description': f'عكس قيد: {line.description}',
            })
        return JournalService.create_entry(
            date=date,
            entry_type=entry.entry_type,
            description=f'عكس قيد رقم {entry.number}',
            lines=reversal_lines,
            created_by=created_by,
        )
```

### Account Balance Logic

```python
# apps/core/utils.py

def get_account_balance(account: Account, as_of_date: date = None) -> Decimal:
    """
    Returns the balance of an account as of a given date.
    For debit-normal accounts (assets, expenses): balance = debit - credit
    For credit-normal accounts (liabilities, equity, revenue): balance = credit - debit
    """
    qs = JournalLine.objects.filter(account=account, entry__is_posted=True)
    if as_of_date:
        qs = qs.filter(entry__date__lte=as_of_date)

    totals = qs.aggregate(total_debit=Sum('debit'), total_credit=Sum('credit'))
    debit = totals['total_debit'] or Decimal('0')
    credit = totals['total_credit'] or Decimal('0')

    if account.account_type in ['asset', 'expense']:
        return debit - credit
    else:
        return credit - debit
```

---

## App 2: `sales` — المبيعات

### Models

```python
class Customer(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    account = models.OneToOneField('core.Account', on_delete=models.PROTECT)  # Receivable account
    tax_number = models.CharField(max_length=50, blank=True)
    credit_limit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    payment_terms_days = models.IntegerField(default=30)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)

class SalesInvoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        POSTED = 'posted', 'مرحّل'
        PARTIALLY_PAID = 'partial', 'مدفوع جزئياً'
        PAID = 'paid', 'مدفوع'
        CANCELLED = 'cancelled', 'ملغي'

    number = models.CharField(max_length=50, unique=True)
    date = models.DateField()
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    subtotal = models.DecimalField(max_digits=18, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=18, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    due_date = models.DateField()
    notes = models.TextField(blank=True)
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

class SalesInvoiceLine(models.Model):
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey('inventory.Item', on_delete=models.PROTECT)
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit_price = models.DecimalField(max_digits=18, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=18, decimal_places=2)
    revenue_account = models.ForeignKey('core.Account', on_delete=models.PROTECT)
    cost_of_goods_account = models.ForeignKey('core.Account', on_delete=models.PROTECT, related_name='+')

class CustomerReceipt(models.Model):
    """تحصيل من عميل"""
    number = models.CharField(max_length=50, unique=True)
    date = models.DateField()
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=[('cash','نقدي'),('bank','بنك'),('cheque','شيك')])
    bank_account = models.ForeignKey('treasury.BankAccount', null=True, blank=True, on_delete=models.PROTECT)
    cash_box = models.ForeignKey('treasury.CashBox', null=True, blank=True, on_delete=models.PROTECT)
    reference = models.CharField(max_length=100, blank=True)
    invoices = models.ManyToManyField(SalesInvoice, through='ReceiptAllocation')
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL)

class ReceiptAllocation(models.Model):
    receipt = models.ForeignKey(CustomerReceipt, on_delete=models.CASCADE)
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
```

### Double-Entry Logic for Sales

```python
# apps/sales/services.py

class SalesService:

    @staticmethod
    @transaction.atomic
    def post_invoice(invoice: SalesInvoice, posted_by) -> JournalEntry:
        """
        Sales Invoice Journal Entry:
        DR  Customer (Receivable)           → invoice.total
        CR  Revenue Account (per line)      → line.total - line.tax
        CR  Tax Payable                     → invoice.tax_amount
        DR  Cost of Goods Sold              → item.cost * quantity
        CR  Inventory                       → item.cost * quantity
        """
        lines = []

        # Debit customer receivable
        lines.append({'account': invoice.customer.account, 'debit': invoice.total, 'credit': 0,
                       'description': f'فاتورة مبيعات {invoice.number}'})

        # Credit revenue per line
        for line in invoice.lines.all():
            net = line.total / (1 + line.tax_percent / 100)
            lines.append({'account': line.revenue_account, 'debit': 0, 'credit': net,
                           'description': f'إيراد مبيعات - {line.item.name}'})
            # COGS entry
            cost = InventoryService.get_item_cost(line.item, line.warehouse)
            lines.append({'account': line.cost_of_goods_account, 'debit': cost * line.quantity, 'credit': 0,
                           'description': f'تكلفة مبيعات - {line.item.name}'})
            lines.append({'account': line.item.inventory_account, 'debit': 0, 'credit': cost * line.quantity,
                           'description': f'صرف مخزون - {line.item.name}'})

        # Credit tax payable
        if invoice.tax_amount > 0:
            tax_account = Account.objects.get(code=settings.TAX_PAYABLE_ACCOUNT)
            lines.append({'account': tax_account, 'debit': 0, 'credit': invoice.tax_amount,
                           'description': 'ضريبة مبيعات'})

        entry = JournalService.create_entry(
            date=invoice.date,
            entry_type=JournalEntry.EntryType.SALE,
            description=f'فاتورة مبيعات رقم {invoice.number}',
            lines=lines,
            source_document=invoice,
            created_by=posted_by,
        )
        invoice.journal_entry = entry
        invoice.status = SalesInvoice.Status.POSTED
        invoice.save()
        InventoryService.reduce_stock(invoice)
        return entry
```

---

## App 3: `purchases` — المشتريات

### Models

```python
class Supplier(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    account = models.OneToOneField('core.Account', on_delete=models.PROTECT)  # Payable account
    tax_number = models.CharField(max_length=50, blank=True)
    payment_terms_days = models.IntegerField(default=30)
    address = models.TextField(blank=True)

class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        APPROVED = 'approved', 'معتمد'
        RECEIVED = 'received', 'مستلم'
        INVOICED = 'invoiced', 'مفوتر'
        CANCELLED = 'cancelled', 'ملغي'

    number = models.CharField(max_length=50, unique=True)
    date = models.DateField()
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    expected_delivery_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

class PurchaseInvoice(models.Model):
    """فاتورة شراء من مورد"""
    number = models.CharField(max_length=50, unique=True)
    supplier_invoice_number = models.CharField(max_length=100)     # Supplier's invoice number
    date = models.DateField()
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    purchase_order = models.ForeignKey(PurchaseOrder, null=True, blank=True, on_delete=models.SET_NULL)
    subtotal = models.DecimalField(max_digits=18, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=18, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    due_date = models.DateField()
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL)

class PurchaseInvoiceLine(models.Model):
    invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey('inventory.Item', on_delete=models.PROTECT)
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=2)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=18, decimal_places=2)

class SupplierPayment(models.Model):
    """سداد لمورد"""
    number = models.CharField(max_length=50, unique=True)
    date = models.DateField()
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=[('cash','نقدي'),('bank','بنك'),('cheque','شيك')])
    bank_account = models.ForeignKey('treasury.BankAccount', null=True, blank=True, on_delete=models.PROTECT)
    cash_box = models.ForeignKey('treasury.CashBox', null=True, blank=True, on_delete=models.PROTECT)
    invoices = models.ManyToManyField(PurchaseInvoice, through='PaymentAllocation')
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL)
```

### Double-Entry Logic for Purchases

```python
# Purchase Invoice Journal Entry:
# DR  Inventory Account (per line)     → quantity * unit_cost
# DR  Tax Deductible (if applicable)   → tax_amount
# CR  Supplier (Payable)               → invoice.total

# Supplier Payment Journal Entry:
# DR  Supplier (Payable)               → payment.amount
# CR  Bank/Cash Account                → payment.amount
```

---

## App 4: `inventory` — المخزون

### Models

```python
class ItemCategory(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT)

class UnitOfMeasure(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=50)

class Item(models.Model):
    class CostingMethod(models.TextChoices):
        FIFO = 'fifo', 'FIFO أول دخول أول خروج'
        WEIGHTED_AVG = 'weighted_avg', 'المتوسط المرجح'
        STANDARD = 'standard', 'التكلفة المعيارية'

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=300)
    category = models.ForeignKey(ItemCategory, on_delete=models.PROTECT)
    unit = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT)
    costing_method = models.CharField(max_length=20, choices=CostingMethod.choices, default=CostingMethod.WEIGHTED_AVG)
    inventory_account = models.ForeignKey('core.Account', on_delete=models.PROTECT, related_name='inventory_items')
    cogs_account = models.ForeignKey('core.Account', on_delete=models.PROTECT, related_name='cogs_items')
    minimum_stock = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    barcode = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

class Warehouse(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    location = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

class StockMovement(models.Model):
    """
    Every inventory change is recorded as a StockMovement.
    Positive quantity = stock in. Negative = stock out.
    """
    class MovementType(models.TextChoices):
        PURCHASE_RECEIPT = 'purchase_in', 'استلام مشتريات'
        SALES_ISSUE = 'sales_out', 'صرف مبيعات'
        TRANSFER_IN = 'transfer_in', 'تحويل وارد'
        TRANSFER_OUT = 'transfer_out', 'تحويل صادر'
        ADJUSTMENT_IN = 'adj_in', 'تسوية زيادة'
        ADJUSTMENT_OUT = 'adj_out', 'تسوية نقص'
        OPENING = 'opening', 'رصيد افتتاحي'

    date = models.DateField()
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=2)
    total_cost = models.DecimalField(max_digits=18, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True)
    content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    source = GenericForeignKey('content_type', 'object_id')
    running_quantity = models.DecimalField(max_digits=14, decimal_places=4)    # Computed running balance
    running_value = models.DecimalField(max_digits=18, decimal_places=2)       # Computed running value

class ItemLedger(models.Model):
    """Per-item, per-warehouse balance snapshot for fast queries"""
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE)
    quantity_on_hand = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    total_value = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('item', 'warehouse')]

    @property
    def average_cost(self):
        if self.quantity_on_hand == 0:
            return Decimal('0')
        return self.total_value / self.quantity_on_hand
```

---

## App 5: `expenses` — المصروفات والعهدة

### Models

```python
class ExpenseCategory(models.Model):
    name = models.CharField(max_length=200)
    account = models.ForeignKey('core.Account', on_delete=models.PROTECT)

class Expense(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        APPROVED = 'approved', 'معتمد'
        POSTED = 'posted', 'مرحّل'
        REJECTED = 'rejected', 'مرفوض'

    number = models.CharField(max_length=50, unique=True)
    date = models.DateField()
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    description = models.TextField()
    payment_method = models.CharField(max_length=20, choices=[('cash','نقدي'),('bank','بنك'),('custody','عهدة')])
    bank_account = models.ForeignKey('treasury.BankAccount', null=True, blank=True, on_delete=models.PROTECT)
    cash_box = models.ForeignKey('treasury.CashBox', null=True, blank=True, on_delete=models.PROTECT)
    custody = models.ForeignKey('Custody', null=True, blank=True, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='approved_expenses')
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL)
    attachment = models.FileField(upload_to='expenses/', blank=True)

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

class CustodySettlement(models.Model):
    """تسوية عهدة"""
    custody = models.ForeignKey(Custody, on_delete=models.PROTECT, related_name='settlements')
    date = models.DateField()
    expenses_amount = models.DecimalField(max_digits=18, decimal_places=2)    # Spent amount with receipts
    returned_amount = models.DecimalField(max_digits=18, decimal_places=2)    # Cash returned
    notes = models.TextField(blank=True)
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL)
```

### Double-Entry Logic for Custody

```python
# Issuing custody (عهدة صادرة):
# DR  Employee Advance Account          → custody.amount
# CR  Cash Box                          → custody.amount

# Settling custody (تسوية عهدة):
# DR  Expense Account                   → expenses_amount
# DR  Cash Box (returned cash)          → returned_amount
# CR  Employee Advance Account          → custody.amount  (expenses + returned = custody)
```

---

## App 6: `treasury` — الخزينة والبنوك

### Models

```python
class CashBox(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    account = models.OneToOneField('core.Account', on_delete=models.PROTECT)
    currency = models.CharField(max_length=3, default='EGP')
    is_active = models.BooleanField(default=True)
    responsible_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

class BankAccount(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    account = models.OneToOneField('core.Account', on_delete=models.PROTECT)
    bank_name = models.CharField(max_length=200)
    account_number = models.CharField(max_length=50)
    iban = models.CharField(max_length=50, blank=True)
    currency = models.CharField(max_length=3, default='EGP')
    is_active = models.BooleanField(default=True)

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
```

---

## App 7: `reports` — التقارير المالية

### Report Types

```python
# apps/reports/services.py

class ReportService:

    @staticmethod
    def trial_balance(as_of_date: date, fiscal_year: FiscalYear) -> list[dict]:
        """
        ميزان المراجعة
        Returns all accounts with opening balance, period movements, closing balance.
        """
        accounts = Account.objects.filter(is_leaf=True, is_active=True)
        rows = []
        for account in accounts:
            debit = JournalLine.objects.filter(
                account=account, entry__is_posted=True,
                entry__fiscal_year=fiscal_year, entry__date__lte=as_of_date
            ).aggregate(total=Sum('debit'))['total'] or 0
            credit = JournalLine.objects.filter(
                account=account, entry__is_posted=True,
                entry__fiscal_year=fiscal_year, entry__date__lte=as_of_date
            ).aggregate(total=Sum('credit'))['total'] or 0
            if debit or credit:
                rows.append({'account': account, 'debit': debit, 'credit': credit,
                              'balance': debit - credit if account.account_type in ['asset','expense'] else credit - debit})
        return rows

    @staticmethod
    def income_statement(from_date: date, to_date: date) -> dict:
        """
        قائمة الدخل (Income Statement / P&L)
        Revenue - COGS = Gross Profit
        Gross Profit - Operating Expenses = Net Income
        """
        ...

    @staticmethod
    def balance_sheet(as_of_date: date) -> dict:
        """
        المركز المالي (Balance Sheet)
        Assets = Liabilities + Equity
        """
        ...

    @staticmethod
    def cash_flow(from_date: date, to_date: date) -> dict:
        """
        قائمة التدفقات النقدية (Cash Flow Statement)
        Operating + Investing + Financing activities
        """
        ...

    @staticmethod
    def account_statement(account: Account, from_date: date, to_date: date) -> list[dict]:
        """
        كشف حساب — full ledger for any account with running balance
        """
        ...
```

### Report URLs

```
GET /reports/trial-balance/?date=2024-12-31
GET /reports/income-statement/?from=2024-01-01&to=2024-12-31
GET /reports/balance-sheet/?date=2024-12-31
GET /reports/cash-flow/?from=2024-01-01&to=2024-12-31
GET /reports/account-statement/?account_id=5&from=2024-01-01&to=2024-12-31
GET /reports/customer-aging/
GET /reports/supplier-aging/
GET /reports/inventory-valuation/?date=2024-12-31
GET /reports/stock-movement/?item_id=10&from=2024-01-01&to=2024-12-31
```

---

## Permissions & Authorization

```python
# Use Django's built-in permission system + custom groups

ACCOUNTING_GROUPS = {
    'accountant': [
        'core.view_journalentry', 'core.add_journalentry',
        'sales.add_salesinvoice', 'sales.view_salesinvoice',
        'purchases.add_purchaseinvoice', 'purchases.view_purchaseinvoice',
        'expenses.add_expense', 'treasury.add_banktransaction',
    ],
    'sales_manager': [
        'sales.*',
        'inventory.view_item', 'inventory.view_stockmovement',
    ],
    'warehouse_manager': [
        'inventory.*',
    ],
    'finance_manager': [
        '*',  # Full access including reports and fiscal year closing
    ],
    'auditor': [
        '*.view_*',  # Read-only across all apps
    ],
}
```

---

## Double-Entry Summary Table

| Transaction | Debit (مدين) | Credit (دائن) |
|---|---|---|
| فاتورة مبيعات | العميل (مدينون) | إيرادات المبيعات |
| تكلفة المبيعات | تكلفة البضاعة المباعة | المخزون |
| تحصيل من عميل | الخزينة / البنك | العميل |
| فاتورة مشتريات | المخزون | المورد (دائنون) |
| سداد لمورد | المورد (دائنون) | الخزينة / البنك |
| مصروف نقدي | حساب المصروف | الخزينة |
| إصدار عهدة | سلفة الموظف | الخزينة |
| تسوية عهدة | المصروف + الخزينة (مرتجع) | سلفة الموظف |
| إيداع بنكي | البنك | الخزينة |
| سحب بنكي | الخزينة | البنك |
| ضريبة مبيعات | العميل (ضمن الإجمالي) | ضريبة مستحقة |

---

## Key Business Rules

1. **لا قيد بغير توازن**: `sum(debit) == sum(credit)` مطلوب دائماً — يُرفض القيد إذا كانت القيمتان مختلفتين.
2. **لا حذف بعد الترحيل**: أي مستند مُرحَّل يُعكس فقط ولا يُحذف.
3. **السنة المالية المغلقة**: لا يُسمح بإدخال قيود في سنة مالية مغلقة.
4. **المخزون السالب**: ممنوع — يتحقق النظام من الرصيد قبل صرف أي صنف.
5. **العهدة**: لا يُسمح بإصدار عهدة جديدة لموظف لديه عهدة غير مسواة.
6. **حدود الائتمان**: التحقق من `customer.credit_limit` قبل قبول فاتورة مبيعات جديدة.
7. **الصلاحيات**: كل عملية مالية تحتاج إلى صلاحية محددة مسبقاً.
8. **المسار التدقيقي**: كل تعديل يُسجَّل في جدول `AuditLog` مع المستخدم والوقت والقيمة القديمة.

---

## Development Phases

### Phase 1 — Core Foundation (أسبوعان)
- Setup Django project structure and settings
- Implement `core` app: Account, FiscalYear, JournalEntry, JournalLine, JournalService
- Authentication, permissions, and groups
- Admin interface for chart of accounts setup

### Phase 2 — Sales & Purchases (أسبوعان)
- `sales` app: Customer, SalesInvoice, CustomerReceipt
- `purchases` app: Supplier, PurchaseInvoice, SupplierPayment
- Double-entry automation for both modules
- Basic UI templates with HTMX

### Phase 3 — Inventory (أسبوع)
- `inventory` app: Item, Warehouse, StockMovement, ItemLedger
- FIFO and Weighted Average costing engines
- Stock movement on invoice post/cancel

### Phase 4 — Expenses & Treasury (أسبوع)
- `expenses` app: Expense, Custody, CustodySettlement
- `treasury` app: CashBox, BankAccount, BankTransaction, BankReconciliation
- Cash transfer between accounts

### Phase 5 — Reports (أسبوع)
- Trial Balance
- Income Statement
- Balance Sheet
- Cash Flow Statement
- Customer/Supplier Aging
- Inventory Valuation
- PDF export via WeasyPrint

### Phase 6 — API & Finalization (أسبوع)
- DRF serializers and API endpoints
- Celery tasks for heavy reports
- Automated tests (pytest-django)
- Docker deployment configuration

---

## Example: `requirements/base.txt`

```
Django==5.1
psycopg2-binary==2.9.9
djangorestframework==3.15.2
django-allauth==0.63.6
django-extensions==3.2.3
django-filter==24.2
celery==5.4.0
redis==5.0.7
WeasyPrint==62.3
Pillow==10.4.0
python-decouple==3.8
```

---

*End of Project Plan — Django Accounting System*
*Version 1.0 | Prepared for AI-assisted development*