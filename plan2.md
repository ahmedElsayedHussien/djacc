# Django Accounting System — Phase 2: Forms, Views & Master Data
# الهدف: إنشاء وربط كل البيانات الأساسية بشجرة الحسابات

---

## ما تم إنجازه (Phase 1 — البنية الأساسية)

- [x] Models كاملة لكل app: core, sales, purchases, inventory, expenses, treasury
- [x] JournalService — محرك القيد المزدوج
- [x] Account, JournalEntry, JournalLine, FiscalYear, CostCenter
- [x] منطق get_account_balance
- [x] Double-entry logic لكل عملية

---

## المطلوب الآن (Phase 2)

لكل entity في القائمة دي هنعمل:
1. **ModelForm** — مع validation كامل
2. **Class-Based Views** — CreateView, UpdateView, ListView, DetailView
3. **URL patterns**
4. **Template** — بسيط وظيفي (Bootstrap 5)
5. **ربط تلقائي بشجرة الحسابات** عند الإنشاء

---

## قائمة الـ Entities المطلوبة

1. شجرة الحسابات (Account Tree)
2. العملاء (Customers)
3. الموردين (Suppliers)
4. الخزن (Cash Boxes)
5. الحسابات البنكية (Bank Accounts)
6. مراكز التكلفة (Cost Centers)
7. السنة المالية (Fiscal Year)
8. المستودعات (Warehouses)
9. الأصناف (Items)
10. فئات الأصناف (Item Categories)
11. وحدات القياس (Units of Measure)
12. فئات المصروفات (Expense Categories)
13. الموظفون / المستخدمون (Users & Permissions)

---

## أولاً: شجرة الحسابات — Account Tree

### الفكرة الأساسية
الشجرة هي أساس كل حاجة. العميل والمورد والخزنة كلهم بيتربطوا بـ Account تلقائياً عند إنشائهم.

### الكود الافتراضي لشجرة الحسابات (Chart of Accounts Seed)

```python
# apps/core/management/commands/create_default_chart.py
# يُشغَّل مرة واحدة: python manage.py create_default_chart

from django.core.management.base import BaseCommand
from apps.core.models import Account

DEFAULT_ACCOUNTS = [
    # (code, name, account_type, parent_code, is_leaf)
    # ── أصول ──
    ('1', 'الأصول', 'asset', None, False),
      ('11', 'الأصول المتداولة', 'asset', '1', False),
        ('111', 'النقدية والبنوك', 'asset', '11', False),
          ('1111', 'الخزينة الرئيسية', 'asset', '111', True),
          ('1112', 'البنوك', 'asset', '111', False),
            ('11121', 'البنك الأهلي', 'asset', '1112', True),
        ('112', 'الذمم المدينة', 'asset', '11', False),
          ('1121', 'العملاء', 'asset', '112', False),   # parent for customer sub-accounts
        ('113', 'المخزون', 'asset', '11', False),
          ('1131', 'مخزون البضاعة', 'asset', '113', True),
        ('114', 'سلف الموظفين', 'asset', '11', False),
          ('1141', 'عهد الموظفين', 'asset', '114', False),  # parent for custody sub-accounts
      ('12', 'الأصول الثابتة', 'asset', '1', False),
        ('121', 'الأراضي والمباني', 'asset', '12', True),
        ('122', 'الآلات والمعدات', 'asset', '12', True),
        ('129', 'مجمع إهلاك الأصول', 'asset', '12', True),

    # ── خصوم ──
    ('2', 'الخصوم', 'liability', None, False),
      ('21', 'الخصوم المتداولة', 'liability', '2', False),
        ('211', 'الذمم الدائنة', 'liability', '21', False),
          ('2111', 'الموردون', 'liability', '211', False),  # parent for supplier sub-accounts
        ('212', 'الضرائب المستحقة', 'liability', '21', False),
          ('2121', 'ضريبة القيمة المضافة', 'liability', '212', True),
          ('2122', 'ضريبة الدخل المستحقة', 'liability', '212', True),
        ('213', 'مصروفات مستحقة', 'liability', '21', True),

    # ── حقوق الملكية ──
    ('3', 'حقوق الملكية', 'equity', None, False),
      ('31', 'رأس المال', 'equity', '3', True),
      ('32', 'الاحتياطيات', 'equity', '3', True),
      ('33', 'الأرباح المرحلة', 'equity', '3', True),
      ('34', 'أرباح/خسائر العام', 'equity', '3', True),

    # ── إيرادات ──
    ('4', 'الإيرادات', 'revenue', None, False),
      ('41', 'إيرادات المبيعات', 'revenue', '4', False),
        ('411', 'مبيعات البضاعة', 'revenue', '41', True),
        ('412', 'إيرادات الخدمات', 'revenue', '41', True),
      ('42', 'إيرادات أخرى', 'revenue', '4', True),

    # ── مصروفات ──
    ('5', 'المصروفات', 'expense', None, False),
      ('51', 'تكلفة البضاعة المباعة', 'expense', '5', True),
      ('52', 'مصروفات التشغيل', 'expense', '5', False),
        ('521', 'مصروفات الرواتب', 'expense', '52', True),
        ('522', 'مصروفات الإيجار', 'expense', '52', True),
        ('523', 'مصروفات المرافق', 'expense', '52', True),
        ('524', 'مصروفات إدارية عامة', 'expense', '52', True),
      ('53', 'مصروفات التمويل', 'expense', '5', True),
]

class Command(BaseCommand):
    def handle(self, *args, **options):
        accounts_map = {}
        for code, name, acc_type, parent_code, is_leaf in DEFAULT_ACCOUNTS:
            parent = accounts_map.get(parent_code) if parent_code else None
            acc, created = Account.objects.get_or_create(
                code=code,
                defaults={'name': name, 'account_type': acc_type, 'parent': parent, 'is_leaf': is_leaf}
            )
            accounts_map[code] = acc
            status = 'created' if created else 'exists'
            self.stdout.write(f'  [{status}] {code} — {name}')
        self.stdout.write(self.style.SUCCESS('Chart of accounts ready.'))
```

### AccountForm

```python
# apps/core/forms.py

from django import forms
from .models import Account

class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ['code', 'name', 'account_type', 'parent', 'is_leaf', 'currency', 'notes']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: 1121001'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'account_type': forms.Select(attrs={'class': 'form-select'}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
            'is_leaf': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'currency': forms.TextInput(attrs={'class': 'form-control', 'value': 'EGP'}),
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
        return cleaned
```

### AccountViews

```python
# apps/core/views/accounts.py

from django.views.generic import ListView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from ..models import Account
from ..forms import AccountForm

class AccountListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Account
    template_name = 'core/accounts/list.html'
    context_object_name = 'accounts'
    permission_required = 'core.view_account'

    def get_queryset(self):
        qs = Account.objects.select_related('parent').order_by('code')
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(name__icontains=q) | qs.filter(code__icontains=q)
        acc_type = self.request.GET.get('type')
        if acc_type:
            qs = qs.filter(account_type=acc_type)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['account_types'] = Account.AccountType.choices
        return ctx

class AccountCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Account
    form_class = AccountForm
    template_name = 'core/accounts/form.html'
    success_url = reverse_lazy('core:account-list')
    permission_required = 'core.add_account'

    def form_valid(self, form):
        messages.success(self.request, f'تم إنشاء الحساب {form.instance.name} بنجاح')
        return super().form_valid(form)

class AccountUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Account
    form_class = AccountForm
    template_name = 'core/accounts/form.html'
    success_url = reverse_lazy('core:account-list')
    permission_required = 'core.change_account'

    def form_valid(self, form):
        messages.success(self.request, 'تم تحديث الحساب بنجاح')
        return super().form_valid(form)
```

---

## ثانياً: العملاء — Customers

### المبدأ الأساسي
عند إنشاء عميل جديد، يُنشأ تلقائياً حساب محاسبي تحت شجرة `1121 - العملاء`. هذا يعني أن كل عميل له حساب مستقل في دليل الحسابات.

```
1121 — العملاء (parent, not leaf)
  ├── 1121001 — شركة النيل للتجارة     ← ينشأ تلقائياً عند إضافة عميل
  ├── 1121002 — مؤسسة الدلتا          ← ينشأ تلقائياً
  └── 1121003 — ...
```

### CustomerForm

```python
# apps/sales/forms.py

from django import forms
from django.db import transaction
from .models import Customer
from apps.core.models import Account

class CustomerForm(forms.ModelForm):
    """
    لا يعرض حقل 'account' للمستخدم — يُنشأ تلقائياً.
    """
    class Meta:
        model = Customer
        fields = [
            'code', 'name', 'tax_number',
            'credit_limit', 'payment_terms_days',
            'address', 'phone', 'email',
        ]
        widgets = {
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'كود العميل (اتركه فارغاً للتوليد التلقائي)'
            }),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'tax_number': forms.TextInput(attrs={'class': 'form-control'}),
            'credit_limit': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'payment_terms_days': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'code': 'كود العميل',
            'name': 'اسم العميل',
            'tax_number': 'الرقم الضريبي',
            'credit_limit': 'حد الائتمان',
            'payment_terms_days': 'أجل السداد (أيام)',
            'address': 'العنوان',
            'phone': 'الهاتف',
            'email': 'البريد الإلكتروني',
        }

    def clean_code(self):
        code = self.cleaned_data.get('code')
        if not code:
            # Auto-generate: C0001, C0002, ...
            last = Customer.objects.order_by('-id').first()
            next_num = (last.id + 1) if last else 1
            code = f'C{next_num:04d}'
        else:
            qs = Customer.objects.filter(code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError('كود العميل مستخدم من قبل')
        return code
```

### CustomerService — ربط العميل بشجرة الحسابات

```python
# apps/sales/services.py

from django.db import transaction
from django.conf import settings
from apps.core.models import Account
from .models import Customer

class CustomerService:

    CUSTOMERS_PARENT_CODE = getattr(settings, 'CUSTOMERS_PARENT_ACCOUNT', '1121')

    @staticmethod
    @transaction.atomic
    def create_customer(validated_data: dict) -> Customer:
        """
        1. يُنشئ الحساب المحاسبي للعميل تحت شجرة العملاء
        2. يُنشئ سجل العميل مرتبطاً بالحساب
        """
        parent = Account.objects.get(code=CustomerService.CUSTOMERS_PARENT_CODE)

        # Generate account code: parent_code + sequential number
        existing_children = Account.objects.filter(
            parent=parent
        ).order_by('code')
        next_seq = existing_children.count() + 1
        account_code = f'{parent.code}{next_seq:03d}'

        # Create the accounting account
        account = Account.objects.create(
            code=account_code,
            name=validated_data['name'],
            account_type='asset',
            parent=parent,
            is_leaf=True,
            currency='EGP',
        )

        # Create the customer linked to that account
        customer = Customer.objects.create(
            account=account,
            **validated_data,
        )
        return customer

    @staticmethod
    @transaction.atomic
    def update_customer(customer: Customer, validated_data: dict) -> Customer:
        # Keep account name in sync with customer name
        if 'name' in validated_data and validated_data['name'] != customer.name:
            customer.account.name = validated_data['name']
            customer.account.save(update_fields=['name'])

        for field, value in validated_data.items():
            setattr(customer, field, value)
        customer.save()
        return customer
```

### CustomerViews

```python
# apps/sales/views/customers.py

from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from ..models import Customer
from ..forms import CustomerForm
from ..services import CustomerService

class CustomerListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Customer
    template_name = 'sales/customers/list.html'
    context_object_name = 'customers'
    permission_required = 'sales.view_customer'
    paginate_by = 25

    def get_queryset(self):
        qs = Customer.objects.select_related('account').order_by('code')
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(name__icontains=q) | qs.filter(code__icontains=q)
        return qs

class CustomerCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'sales/customers/form.html'
    permission_required = 'sales.add_customer'
    success_url = reverse_lazy('sales:customer-list')

    def form_valid(self, form):
        try:
            customer = CustomerService.create_customer(form.cleaned_data)
            messages.success(
                self.request,
                f'تم إنشاء العميل "{customer.name}" بنجاح — كود الحساب: {customer.account.code}'
            )
            from django.shortcuts import redirect
            return redirect(self.success_url)
        except Exception as e:
            messages.error(self.request, f'خطأ: {e}')
            return self.form_invalid(form)

class CustomerUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'sales/customers/form.html'
    permission_required = 'sales.change_customer'
    success_url = reverse_lazy('sales:customer-list')

    def form_valid(self, form):
        CustomerService.update_customer(self.object, form.cleaned_data)
        messages.success(self.request, 'تم تحديث بيانات العميل بنجاح')
        from django.shortcuts import redirect
        return redirect(self.success_url)

class CustomerDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Customer
    template_name = 'sales/customers/detail.html'
    permission_required = 'sales.view_customer'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.core.utils import get_account_balance
        from datetime import date
        ctx['balance'] = get_account_balance(self.object.account, as_of_date=date.today())
        # Latest invoices
        ctx['invoices'] = self.object.salesinvoice_set.order_by('-date')[:10]
        return ctx
```

---

## ثالثاً: الموردون — Suppliers

### نفس مبدأ العملاء لكن تحت شجرة المستحقات

```
2111 — الموردون (parent, not leaf)
  ├── 2111001 — شركة التوريد المصرية    ← ينشأ تلقائياً
  └── 2111002 — مؤسسة الخليج           ← ينشأ تلقائياً
```

### SupplierForm

```python
# apps/purchases/forms.py

from django import forms
from .models import Supplier

class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = [
            'code', 'name', 'tax_number',
            'payment_terms_days', 'address', 'phone', 'email',
        ]
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control',
                'placeholder': 'كود المورد (اتركه فارغاً للتوليد التلقائي)'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'tax_number': forms.TextInput(attrs={'class': 'form-control'}),
            'payment_terms_days': forms.NumberInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }

    def clean_code(self):
        code = self.cleaned_data.get('code')
        if not code:
            last = Supplier.objects.order_by('-id').first()
            next_num = (last.id + 1) if last else 1
            code = f'S{next_num:04d}'
        return code
```

### SupplierService

```python
# apps/purchases/services.py

class SupplierService:

    SUPPLIERS_PARENT_CODE = getattr(settings, 'SUPPLIERS_PARENT_ACCOUNT', '2111')

    @staticmethod
    @transaction.atomic
    def create_supplier(validated_data: dict) -> Supplier:
        parent = Account.objects.get(code=SupplierService.SUPPLIERS_PARENT_CODE)
        next_seq = Account.objects.filter(parent=parent).count() + 1
        account_code = f'{parent.code}{next_seq:03d}'

        account = Account.objects.create(
            code=account_code,
            name=validated_data['name'],
            account_type='liability',    # ← موردون = خصوم
            parent=parent,
            is_leaf=True,
        )
        return Supplier.objects.create(account=account, **validated_data)
```

### SupplierViews

```python
# apps/purchases/views/suppliers.py
# نفس pattern العملاء بالضبط

class SupplierListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Supplier
    template_name = 'purchases/suppliers/list.html'
    context_object_name = 'suppliers'
    permission_required = 'purchases.view_supplier'
    paginate_by = 25

    def get_queryset(self):
        qs = Supplier.objects.select_related('account').order_by('code')
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(name__icontains=q) | qs.filter(code__icontains=q)
        return qs

class SupplierCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Supplier
    form_class = SupplierForm
    template_name = 'purchases/suppliers/form.html'
    permission_required = 'purchases.add_supplier'
    success_url = reverse_lazy('purchases:supplier-list')

    def form_valid(self, form):
        supplier = SupplierService.create_supplier(form.cleaned_data)
        messages.success(self.request,
            f'تم إنشاء المورد "{supplier.name}" — كود الحساب: {supplier.account.code}')
        from django.shortcuts import redirect
        return redirect(self.success_url)

class SupplierUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Supplier
    form_class = SupplierForm
    template_name = 'purchases/suppliers/form.html'
    permission_required = 'purchases.change_supplier'
    success_url = reverse_lazy('purchases:supplier-list')

class SupplierDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Supplier
    template_name = 'purchases/suppliers/detail.html'
    permission_required = 'purchases.view_supplier'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.core.utils import get_account_balance
        from datetime import date
        ctx['balance'] = get_account_balance(self.object.account, as_of_date=date.today())
        ctx['invoices'] = self.object.purchaseinvoice_set.order_by('-date')[:10]
        return ctx
```

---

## رابعاً: الخزن — Cash Boxes

### الربط بشجرة الحسابات

```
1111 — الخزينة الرئيسية (parent)
  ├── 11111 — خزنة المبيعات           ← ينشأ تلقائياً
  ├── 11112 — خزنة الفرع الثاني       ← ينشأ تلقائياً
  └── 11113 — ...
```

### CashBoxForm

```python
# apps/treasury/forms.py

from django import forms
from .models import CashBox
from apps.core.models import Account

class CashBoxForm(forms.ModelForm):
    class Meta:
        model = CashBox
        fields = ['code', 'name', 'currency', 'responsible_user']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control',
                'placeholder': 'كود الخزنة'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'currency': forms.TextInput(attrs={'class': 'form-control', 'value': 'EGP'}),
            'responsible_user': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.fields['responsible_user'].queryset = User.objects.filter(is_active=True)
```

### CashBoxService

```python
# apps/treasury/services.py

from django.conf import settings
from django.db import transaction
from apps.core.models import Account
from .models import CashBox, BankAccount

class TreasuryService:

    CASHBOX_PARENT_CODE = getattr(settings, 'CASHBOX_PARENT_ACCOUNT', '1111')
    BANK_PARENT_CODE = getattr(settings, 'BANK_PARENT_ACCOUNT', '1112')

    @staticmethod
    @transaction.atomic
    def create_cash_box(validated_data: dict) -> CashBox:
        """
        ينشئ حساب محاسبي للخزنة تحت شجرة النقدية،
        ثم يربطها بسجل الخزنة.
        """
        parent = Account.objects.get(code=TreasuryService.CASHBOX_PARENT_CODE)
        next_seq = Account.objects.filter(parent=parent).count() + 1
        account_code = f'{parent.code}{next_seq:1d}'

        account = Account.objects.create(
            code=account_code,
            name=validated_data['name'],
            account_type='asset',
            parent=parent,
            is_leaf=True,
            currency=validated_data.get('currency', 'EGP'),
        )
        return CashBox.objects.create(account=account, **validated_data)

    @staticmethod
    @transaction.atomic
    def create_bank_account(validated_data: dict) -> BankAccount:
        """
        نفس المبدأ للحسابات البنكية.
        """
        parent = Account.objects.get(code=TreasuryService.BANK_PARENT_CODE)
        next_seq = Account.objects.filter(parent=parent).count() + 1
        account_code = f'{parent.code}{next_seq:02d}'

        account = Account.objects.create(
            code=account_code,
            name=f'{validated_data["bank_name"]} — {validated_data["name"]}',
            account_type='asset',
            parent=parent,
            is_leaf=True,
            currency=validated_data.get('currency', 'EGP'),
        )
        return BankAccount.objects.create(account=account, **validated_data)
```

### CashBox & BankAccount Views

```python
# apps/treasury/views.py

class CashBoxListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = CashBox
    template_name = 'treasury/cashboxes/list.html'
    permission_required = 'treasury.view_cashbox'

    def get_queryset(self):
        return CashBox.objects.select_related('account', 'responsible_user').filter(is_active=True)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.core.utils import get_account_balance
        from datetime import date
        # Annotate each box with its current balance
        for box in ctx['object_list']:
            box.current_balance = get_account_balance(box.account, as_of_date=date.today())
        return ctx

class CashBoxCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = CashBox
    form_class = CashBoxForm
    template_name = 'treasury/cashboxes/form.html'
    permission_required = 'treasury.add_cashbox'
    success_url = reverse_lazy('treasury:cashbox-list')

    def form_valid(self, form):
        cash_box = TreasuryService.create_cash_box(form.cleaned_data)
        messages.success(self.request,
            f'تم إنشاء الخزنة "{cash_box.name}" — كود الحساب: {cash_box.account.code}')
        from django.shortcuts import redirect
        return redirect(self.success_url)


class BankAccountForm(forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = ['code', 'name', 'bank_name', 'account_number', 'iban', 'currency']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control',
                'placeholder': 'اسم وصفي للحساب مثل: حساب رواتب'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'account_number': forms.TextInput(attrs={'class': 'form-control'}),
            'iban': forms.TextInput(attrs={'class': 'form-control'}),
            'currency': forms.TextInput(attrs={'class': 'form-control', 'value': 'EGP'}),
        }

class BankAccountListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = BankAccount
    template_name = 'treasury/banks/list.html'
    permission_required = 'treasury.view_bankaccount'

    def get_queryset(self):
        return BankAccount.objects.select_related('account').filter(is_active=True)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.core.utils import get_account_balance
        from datetime import date
        for bank in ctx['object_list']:
            bank.current_balance = get_account_balance(bank.account, as_of_date=date.today())
        return ctx

class BankAccountCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = BankAccount
    form_class = BankAccountForm
    template_name = 'treasury/banks/form.html'
    permission_required = 'treasury.add_bankaccount'
    success_url = reverse_lazy('treasury:bank-list')

    def form_valid(self, form):
        bank = TreasuryService.create_bank_account(form.cleaned_data)
        messages.success(self.request, f'تم إنشاء الحساب البنكي "{bank.name}"')
        from django.shortcuts import redirect
        return redirect(self.success_url)
```

---

## خامساً: المستودعات والأصناف — Warehouses & Items

### WarehouseForm + Views

```python
# apps/inventory/forms.py

class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ['code', 'name', 'location']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

class ItemCategoryForm(forms.ModelForm):
    class Meta:
        model = ItemCategory
        fields = ['code', 'name', 'parent']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
        }

class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = [
            'code', 'name', 'category', 'unit',
            'costing_method', 'inventory_account', 'cogs_account',
            'minimum_stock', 'barcode',
        ]
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'unit': forms.Select(attrs={'class': 'form-select'}),
            'costing_method': forms.Select(attrs={'class': 'form-select'}),
            'inventory_account': forms.Select(attrs={'class': 'form-select'}),
            'cogs_account': forms.Select(attrs={'class': 'form-select'}),
            'minimum_stock': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'barcode': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show leaf accounts for accounting fields
        leaf_accounts = Account.objects.filter(is_leaf=True, is_active=True).order_by('code')
        inventory_accounts = leaf_accounts.filter(account_type='asset')
        expense_accounts = leaf_accounts.filter(account_type='expense')
        self.fields['inventory_account'].queryset = inventory_accounts
        self.fields['cogs_account'].queryset = expense_accounts
```

### ItemViews

```python
# apps/inventory/views/items.py

class ItemListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Item
    template_name = 'inventory/items/list.html'
    context_object_name = 'items'
    permission_required = 'inventory.view_item'
    paginate_by = 30

    def get_queryset(self):
        qs = Item.objects.select_related('category', 'unit').filter(is_active=True).order_by('code')
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(name__icontains=q) | qs.filter(code__icontains=q)
        category = self.request.GET.get('category')
        if category:
            qs = qs.filter(category_id=category)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['categories'] = ItemCategory.objects.all()
        # Annotate with current stock from ItemLedger
        from django.db.models import Sum
        from apps.inventory.models import ItemLedger
        stock_map = {
            l['item_id']: l['total_qty']
            for l in ItemLedger.objects.values('item_id').annotate(total_qty=Sum('quantity_on_hand'))
        }
        for item in ctx['items']:
            item.current_stock = stock_map.get(item.id, 0)
        return ctx

class ItemCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Item
    form_class = ItemForm
    template_name = 'inventory/items/form.html'
    permission_required = 'inventory.add_item'
    success_url = reverse_lazy('inventory:item-list')

    def form_valid(self, form):
        messages.success(self.request, f'تم إنشاء الصنف "{form.instance.name}" بنجاح')
        return super().form_valid(form)
```

---

## سادساً: العهدة والمصروفات — Custody & Expenses

### ExpenseCategoryForm

```python
# apps/expenses/forms.py

class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ['name', 'account']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'account': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only expense leaf accounts
        self.fields['account'].queryset = Account.objects.filter(
            account_type='expense', is_leaf=True, is_active=True
        ).order_by('code')

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            'date', 'category', 'amount', 'description',
            'payment_method', 'bank_account', 'cash_box', 'custody',
            'attachment',
        ]
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01', 'step': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'payment_method': forms.Select(attrs={
                'class': 'form-select',
                'onchange': 'togglePaymentSource(this.value)'   # JS to show/hide bank/cash/custody
            }),
            'bank_account': forms.Select(attrs={'class': 'form-select'}),
            'cash_box': forms.Select(attrs={'class': 'form-select'}),
            'custody': forms.Select(attrs={'class': 'form-select'}),
            'attachment': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get('payment_method')
        if method == 'bank' and not cleaned.get('bank_account'):
            raise forms.ValidationError('يجب تحديد الحساب البنكي عند الدفع بالبنك')
        if method == 'cash' and not cleaned.get('cash_box'):
            raise forms.ValidationError('يجب تحديد الخزنة عند الدفع نقداً')
        if method == 'custody' and not cleaned.get('custody'):
            raise forms.ValidationError('يجب تحديد العهدة')
        return cleaned

class CustodyForm(forms.ModelForm):
    class Meta:
        model = Custody
        fields = ['date', 'employee', 'amount', 'purpose', 'account', 'cash_box']
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01', 'step': '0.01'}),
            'purpose': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'account': forms.Select(attrs={'class': 'form-select'}),
            'cash_box': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.fields['employee'].queryset = User.objects.filter(is_active=True)
        # Custody accounts only
        self.fields['account'].queryset = Account.objects.filter(
            code__startswith='1141', is_leaf=True
        )
        # Validate: no open custody for this employee
    
    def clean_employee(self):
        employee = self.cleaned_data.get('employee')
        if employee:
            open_custody = Custody.objects.filter(
                employee=employee,
                status__in=['open', 'partial']
            ).exists()
            if open_custody and not self.instance.pk:
                raise forms.ValidationError(
                    'هذا الموظف لديه عهدة مفتوحة — يجب تسويتها أولاً'
                )
        return employee
```

---

## سابعاً: السنة المالية — Fiscal Year

```python
# apps/core/forms.py (continued)

class FiscalYearForm(forms.ModelForm):
    class Meta:
        model = FiscalYear
        fields = ['name', 'start_date', 'end_date']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control',
                'placeholder': 'مثال: السنة المالية 2025'}),
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
```

---

## ثامناً: URL Patterns

```python
# apps/core/urls.py
from django.urls import path
from .views import accounts as account_views
from .views import fiscal_year as fy_views

app_name = 'core'

urlpatterns = [
    # Chart of Accounts
    path('accounts/', account_views.AccountListView.as_view(), name='account-list'),
    path('accounts/create/', account_views.AccountCreateView.as_view(), name='account-create'),
    path('accounts/<int:pk>/edit/', account_views.AccountUpdateView.as_view(), name='account-edit'),

    # Fiscal Year
    path('fiscal-years/', fy_views.FiscalYearListView.as_view(), name='fiscalyear-list'),
    path('fiscal-years/create/', fy_views.FiscalYearCreateView.as_view(), name='fiscalyear-create'),
    path('fiscal-years/<int:pk>/close/', fy_views.FiscalYearCloseView.as_view(), name='fiscalyear-close'),

    # Cost Centers
    path('cost-centers/', account_views.CostCenterListView.as_view(), name='costcenter-list'),
    path('cost-centers/create/', account_views.CostCenterCreateView.as_view(), name='costcenter-create'),
]

# apps/sales/urls.py
app_name = 'sales'
urlpatterns = [
    path('customers/', CustomerListView.as_view(), name='customer-list'),
    path('customers/create/', CustomerCreateView.as_view(), name='customer-create'),
    path('customers/<int:pk>/', CustomerDetailView.as_view(), name='customer-detail'),
    path('customers/<int:pk>/edit/', CustomerUpdateView.as_view(), name='customer-edit'),
]

# apps/purchases/urls.py
app_name = 'purchases'
urlpatterns = [
    path('suppliers/', SupplierListView.as_view(), name='supplier-list'),
    path('suppliers/create/', SupplierCreateView.as_view(), name='supplier-create'),
    path('suppliers/<int:pk>/', SupplierDetailView.as_view(), name='supplier-detail'),
    path('suppliers/<int:pk>/edit/', SupplierUpdateView.as_view(), name='supplier-edit'),
]

# apps/treasury/urls.py
app_name = 'treasury'
urlpatterns = [
    path('cashboxes/', CashBoxListView.as_view(), name='cashbox-list'),
    path('cashboxes/create/', CashBoxCreateView.as_view(), name='cashbox-create'),
    path('cashboxes/<int:pk>/edit/', CashBoxUpdateView.as_view(), name='cashbox-edit'),

    path('banks/', BankAccountListView.as_view(), name='bank-list'),
    path('banks/create/', BankAccountCreateView.as_view(), name='bank-create'),
    path('banks/<int:pk>/edit/', BankAccountUpdateView.as_view(), name='bank-edit'),
]

# apps/inventory/urls.py
app_name = 'inventory'
urlpatterns = [
    path('items/', ItemListView.as_view(), name='item-list'),
    path('items/create/', ItemCreateView.as_view(), name='item-create'),
    path('items/<int:pk>/', ItemDetailView.as_view(), name='item-detail'),
    path('items/<int:pk>/edit/', ItemUpdateView.as_view(), name='item-edit'),

    path('warehouses/', WarehouseListView.as_view(), name='warehouse-list'),
    path('warehouses/create/', WarehouseCreateView.as_view(), name='warehouse-create'),

    path('categories/', ItemCategoryListView.as_view(), name='category-list'),
    path('categories/create/', ItemCategoryCreateView.as_view(), name='category-create'),

    path('units/', UnitListView.as_view(), name='unit-list'),
    path('units/create/', UnitCreateView.as_view(), name='unit-create'),
]

# apps/expenses/urls.py
app_name = 'expenses'
urlpatterns = [
    path('categories/', ExpenseCategoryListView.as_view(), name='category-list'),
    path('categories/create/', ExpenseCategoryCreateView.as_view(), name='category-create'),

    path('custody/', CustodyListView.as_view(), name='custody-list'),
    path('custody/create/', CustodyCreateView.as_view(), name='custody-create'),
    path('custody/<int:pk>/', CustodyDetailView.as_view(), name='custody-detail'),
    path('custody/<int:pk>/settle/', CustodySettlementView.as_view(), name='custody-settle'),

    path('', ExpenseListView.as_view(), name='expense-list'),
    path('create/', ExpenseCreateView.as_view(), name='expense-create'),
    path('<int:pk>/approve/', ExpenseApproveView.as_view(), name='expense-approve'),
]

# config/urls.py — Main router
urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('core/', include('apps.core.urls', namespace='core')),
    path('sales/', include('apps.sales.urls', namespace='sales')),
    path('purchases/', include('apps.purchases.urls', namespace='purchases')),
    path('inventory/', include('apps.inventory.urls', namespace='inventory')),
    path('treasury/', include('apps.treasury.urls', namespace='treasury')),
    path('expenses/', include('apps.expenses.urls', namespace='expenses')),
    path('reports/', include('apps.reports.urls', namespace='reports')),
    path('api/', include('apps.api.urls', namespace='api')),
    path('', include('apps.core.urls')),   # Dashboard at root
]
```

---

## تاسعاً: settings.py — حسابات الربط

```python
# config/settings/base.py

# Account codes for auto-linking
# يمكن تغييرها حسب شجرة الحسابات الخاصة بكل شركة
CUSTOMERS_PARENT_ACCOUNT = '1121'       # ذمم مدينة - العملاء
SUPPLIERS_PARENT_ACCOUNT = '2111'       # ذمم دائنة - الموردون
CASHBOX_PARENT_ACCOUNT = '1111'         # الخزينة الرئيسية
BANK_PARENT_ACCOUNT = '1112'            # البنوك
CUSTODY_PARENT_ACCOUNT = '1141'         # سلف الموظفين / عهد
TAX_PAYABLE_ACCOUNT = '2121'            # ضريبة القيمة المضافة
INVENTORY_DEFAULT_ACCOUNT = '1131'      # مخزون البضاعة
COGS_DEFAULT_ACCOUNT = '51'             # تكلفة البضاعة المباعة
RETAINED_EARNINGS_ACCOUNT = '33'        # الأرباح المرحلة
INCOME_SUMMARY_ACCOUNT = '34'           # ملخص الدخل (للإقفال)
```

---

## عاشراً: Template Base (Bootstrap 5)

```html
<!-- templates/base.html -->
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}نظام المحاسبة{% endblock %}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
  {% block extra_css %}{% endblock %}
</head>
<body>

<nav class="navbar navbar-expand-lg navbar-dark bg-primary">
  <div class="container-fluid">
    <a class="navbar-brand" href="/">نظام المحاسبة</a>
    <div class="collapse navbar-collapse">
      <ul class="navbar-nav me-auto">
        <li class="nav-item dropdown">
          <a class="nav-link dropdown-toggle" href="#" data-bs-toggle="dropdown">المبيعات</a>
          <ul class="dropdown-menu">
            <li><a class="dropdown-item" href="{% url 'sales:customer-list' %}">العملاء</a></li>
            <li><a class="dropdown-item" href="#">فواتير المبيعات</a></li>
            <li><a class="dropdown-item" href="#">تحصيلات</a></li>
          </ul>
        </li>
        <li class="nav-item dropdown">
          <a class="nav-link dropdown-toggle" href="#" data-bs-toggle="dropdown">المشتريات</a>
          <ul class="dropdown-menu">
            <li><a class="dropdown-item" href="{% url 'purchases:supplier-list' %}">الموردون</a></li>
            <li><a class="dropdown-item" href="#">فواتير المشتريات</a></li>
            <li><a class="dropdown-item" href="#">مدفوعات</a></li>
          </ul>
        </li>
        <li class="nav-item dropdown">
          <a class="nav-link dropdown-toggle" href="#" data-bs-toggle="dropdown">المخزون</a>
          <ul class="dropdown-menu">
            <li><a class="dropdown-item" href="{% url 'inventory:item-list' %}">الأصناف</a></li>
            <li><a class="dropdown-item" href="{% url 'inventory:warehouse-list' %}">المستودعات</a></li>
          </ul>
        </li>
        <li class="nav-item dropdown">
          <a class="nav-link dropdown-toggle" href="#" data-bs-toggle="dropdown">الخزينة</a>
          <ul class="dropdown-menu">
            <li><a class="dropdown-item" href="{% url 'treasury:cashbox-list' %}">الخزن</a></li>
            <li><a class="dropdown-item" href="{% url 'treasury:bank-list' %}">البنوك</a></li>
          </ul>
        </li>
        <li class="nav-item dropdown">
          <a class="nav-link dropdown-toggle" href="#" data-bs-toggle="dropdown">المحاسبة</a>
          <ul class="dropdown-menu">
            <li><a class="dropdown-item" href="{% url 'core:account-list' %}">دليل الحسابات</a></li>
            <li><a class="dropdown-item" href="#">القيود اليومية</a></li>
            <li><a class="dropdown-item" href="#">التقارير</a></li>
          </ul>
        </li>
      </ul>
    </div>
  </div>
</nav>

<div class="container-fluid mt-3">
  {% if messages %}
    {% for msg in messages %}
      <div class="alert alert-{{ msg.tags }} alert-dismissible fade show">
        {{ msg }}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      </div>
    {% endfor %}
  {% endif %}
  {% block content %}{% endblock %}
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
{% block extra_js %}{% endblock %}
</body>
</html>
```

```html
<!-- templates/sales/customers/form.html -->
{% extends 'base.html' %}
{% block title %}{% if object %}تعديل عميل{% else %}عميل جديد{% endif %}{% endblock %}
{% block content %}
<div class="row justify-content-center">
  <div class="col-md-8">
    <div class="card">
      <div class="card-header">
        <h5 class="mb-0">{% if object %}تعديل: {{ object.name }}{% else %}إضافة عميل جديد{% endif %}</h5>
      </div>
      <div class="card-body">
        <form method="post" novalidate>
          {% csrf_token %}
          <div class="row g-3">
            <div class="col-md-4">
              <label class="form-label">كود العميل</label>
              {{ form.code }}
              {% if form.code.errors %}<div class="text-danger small">{{ form.code.errors }}</div>{% endif %}
            </div>
            <div class="col-md-8">
              <label class="form-label">اسم العميل *</label>
              {{ form.name }}
              {% if form.name.errors %}<div class="text-danger small">{{ form.name.errors }}</div>{% endif %}
            </div>
            <div class="col-md-6">
              <label class="form-label">الرقم الضريبي</label>
              {{ form.tax_number }}
            </div>
            <div class="col-md-3">
              <label class="form-label">حد الائتمان</label>
              {{ form.credit_limit }}
            </div>
            <div class="col-md-3">
              <label class="form-label">أجل السداد (يوم)</label>
              {{ form.payment_terms_days }}
            </div>
            <div class="col-md-6">
              <label class="form-label">الهاتف</label>
              {{ form.phone }}
            </div>
            <div class="col-md-6">
              <label class="form-label">البريد الإلكتروني</label>
              {{ form.email }}
            </div>
            <div class="col-12">
              <label class="form-label">العنوان</label>
              {{ form.address }}
            </div>
          </div>
          {% if form.non_field_errors %}
            <div class="alert alert-danger mt-3">{{ form.non_field_errors }}</div>
          {% endif %}
          <div class="mt-4 d-flex gap-2">
            <button type="submit" class="btn btn-primary">
              <i class="bi bi-save"></i> حفظ
            </button>
            <a href="{% url 'sales:customer-list' %}" class="btn btn-secondary">إلغاء</a>
          </div>
          {% if not object %}
            <div class="mt-3 text-muted small">
              <i class="bi bi-info-circle"></i>
              سيتم إنشاء حساب محاسبي تلقائياً للعميل تحت شجرة العملاء
            </div>
          {% endif %}
        </form>
      </div>
    </div>
  </div>
</div>
{% endblock %}
```

---

## ملخص خريطة الربط (Account Auto-Linking Map)

| Entity         | نوع الحساب   | تحت الكود | مثال ناتج      |
|----------------|-------------|-----------|---------------|
| عميل جديد      | asset       | 1121      | 1121001, 1121002 |
| مورد جديد      | liability   | 2111      | 2111001, 2111002 |
| خزنة جديدة     | asset       | 1111      | 11111, 11112   |
| حساب بنكي      | asset       | 1112      | 111201, 111202 |
| عهدة موظف      | asset       | 1141      | تحت سلف الموظفين |
| صنف مخزون      | يُختار يدوياً | —       | يختار المستخدم  |
| فئة مصروف      | expense     | يُختار يدوياً | يختار المستخدم |

---

## ترتيب التنفيذ المقترح

1. `python manage.py create_default_chart` — إنشاء شجرة الحسابات الافتراضية
2. إنشاء السنة المالية الأولى من `/core/fiscal-years/create/`
3. إنشاء مراكز التكلفة (اختياري)
4. إنشاء الخزن والبنوك
5. إنشاء الموردين والعملاء
6. إنشاء المستودعات وفئات الأصناف ووحدات القياس
7. إنشاء الأصناف مع ربطها بحسابات المخزون
8. إنشاء فئات المصروفات
9. البدء في تشغيل المعاملات اليومية

---

*Phase 2 — Forms, Views & Master Data*
*يكمل بعد: Phase 1 — البنية الأساسية (Models + JournalService)*
*التالي: Phase 3 — فواتير المبيعات والمشتريات والقيود التلقائية*