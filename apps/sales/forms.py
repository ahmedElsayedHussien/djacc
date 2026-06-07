from datetime import date as date_type, timedelta
from django import forms
from django.conf import settings
from django.contrib.auth.models import User
from django.forms import inlineformset_factory
from .models import (
    Customer, SalesInvoice, SalesInvoiceLine, CustomerReceipt, 
    SalesRepresentative, IntermediaryCompany, PriceList, PriceListItem,
    Quotation, QuotationLine, CustomerSector, SalesReturn, SalesReturnLine
)
from apps.hr.models import Employee, Department, JobTitle
from apps.inventory.models import Item, Warehouse
from apps.core.models import TaxType, Account, CostCenter
from apps.treasury.utils import get_available_cash_boxes

class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            'code', 'name', 'tax_number',
            'credit_limit', 'payment_terms_days',
            'address', 'phone', 'email', 'customer_type', 'sector', 'price_list',
            'is_taxable', 'default_tax1', 'default_tax2'
        ]
        labels = {
            'code': 'كود العميل',
            'name': 'اسم العميل',
            'tax_number': 'الرقم الضريبي',
            'credit_limit': 'الحد الائتماني',
            'payment_terms_days': 'مدة السداد (يوم)',
            'address': 'العنوان',
            'phone': 'الهاتف',
            'email': 'البريد الإلكتروني',
            'customer_type': 'نوع العميل',
            'sector': 'القطاع (لربط الخصومات)',
            'price_list': 'قائمة الأسعار',
            'is_taxable': 'خاضع للضريبة',
            'default_tax1': 'الضريبة الافتراضية 1',
            'default_tax2': 'الضريبة الافتراضية 2',
        }
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'tax_number': forms.TextInput(attrs={'class': 'form-control'}),
            'credit_limit': forms.NumberInput(attrs={'class': 'form-control'}),
            'payment_terms_days': forms.NumberInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'customer_type': forms.Select(attrs={'class': 'form-select'}),
            'sector': forms.Select(attrs={'class': 'form-select'}),
            'price_list': forms.Select(attrs={'class': 'form-select'}),
            'is_taxable': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'default_tax1': forms.Select(attrs={'class': 'form-select'}),
            'default_tax2': forms.Select(attrs={'class': 'form-select'}),
        }

    initial_balance = forms.DecimalField(
        max_digits=18, decimal_places=2, required=False, initial=0,
        label='الرصيد الافتتاحي',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    initial_balance_type = forms.ChoiceField(
        choices=[('debit', 'مدين (عليه)'), ('credit', 'دائن (له)')],
        required=False, initial='debit',
        label='طبيعة الرصيد',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.db.models import Q
        tax_qs = TaxType.objects.filter(appear_in_invoices=True, is_active=True).filter(
            Q(name__icontains='مخرجات') | Q(name__icontains='مبيعات')
        )
        self.fields['default_tax1'].queryset = tax_qs
        self.fields['default_tax2'].queryset = tax_qs

        if self.instance and self.instance.pk and self.instance.account_id:
            self.fields['initial_balance'].initial = self.instance.account.initial_balance
            self.fields['initial_balance_type'].initial = self.instance.account.initial_balance_type

    def clean_credit_limit(self):
        cl = self.cleaned_data.get('credit_limit')
        if cl is not None and cl < 0:
            raise forms.ValidationError('حد الائتمان لا يمكن أن يكون سالباً')
        return cl

    def clean_payment_terms_days(self):
        d = self.cleaned_data.get('payment_terms_days')
        if d is not None and d < 0:
            raise forms.ValidationError('فترة السداد لا يمكن أن تكون أقل من صفر')
        return d

    def clean(self):
        cleaned = super().clean()
        cust_type = cleaned.get('customer_type')
        credit_limit = cleaned.get('credit_limit')
        is_taxable = cleaned.get('is_taxable')
        tax1 = cleaned.get('default_tax1')
        tax2 = cleaned.get('default_tax2')

        if cust_type == 'credit' and credit_limit is not None and credit_limit <= 0:
            self.add_error('credit_limit', 'حد الائتمان يجب أن يكون أكبر من صفر للعملاء الآجلين')
        if is_taxable and not tax1 and not tax2:
            self.add_error('default_tax1', 'يرجى تحديد ضريبة افتراضية واحدة على الأقل للعملاء الخاضعين للضريبة')
        return cleaned

class SalesRepresentativeForm(forms.ModelForm):
    # حقول الموظف (تُستخدم فقط في وضع الإنشاء)
    user = forms.ModelChoiceField(
        queryset=None, required=False,
        label='مستخدم النظام',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    national_id = forms.CharField(
        max_length=20, required=False,
        label='الرقم القومي / الإقامة',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    phone = forms.CharField(
        max_length=20, required=False,
        label='رقم الهاتف',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    department = forms.ModelChoiceField(
        queryset=None, required=False,
        label='الإدارة',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    job_title = forms.ModelChoiceField(
        queryset=None, required=False,
        label='المسمى الوظيفي',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    hiring_date = forms.DateField(
        required=False,
        label='تاريخ التعيين',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    basic_salary = forms.DecimalField(
        max_digits=10, decimal_places=2, required=False, initial=0,
        label='الراتب الأساسي',
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = SalesRepresentative
        fields = ['employee', 'code', 'commission_rate', 'territory', 'supervisor', 'is_active']
        labels = {
            'employee': 'الموظف',
            'code': 'كود المندوب',
            'commission_rate': 'نسبة العمولة (%)',
            'territory': 'المنطقة / النطاق',
            'supervisor': 'المشرف',
            'is_active': 'نشط',
        }
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'يُولد تلقائياً'}),
            'commission_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'territory': forms.TextInput(attrs={'class': 'form-control'}),
            'supervisor': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # اليوزرز اللي ليهم موظف مرتبط أو سوبر يوزر — مينفعش يتختاروا
        linked_user_ids = Employee.objects.exclude(user__isnull=True).values_list('user_id', flat=True)
        self.fields['user'].queryset = (
            User.objects.filter(is_active=True)
            .exclude(is_superuser=True)
            .exclude(id__in=linked_user_ids)
            .order_by('username')
        )
        self.fields['department'].queryset = Department.objects.all()
        self.fields['job_title'].queryset = JobTitle.objects.all()
        self.fields['supervisor'].queryset = SalesRepresentative.objects.filter(is_active=True)

        if self.instance and self.instance.pk:
            # وضع التعديل: نخفي حقول إنشاء الموظف ونعطل تغيير employee
            for f in ('user', 'national_id', 'phone', 'department', 'job_title', 'hiring_date', 'basic_salary'):
                self.fields[f].widget = forms.HiddenInput()
            self.fields['employee'].disabled = True
            self.fields['employee'].required = False
            if self.instance.employee and self.instance.employee.user:
                self.fields['user'].initial = self.instance.employee.user_id
        else:
            # وضع الإنشاء: نخفي employee ونظهر حقول الموظف
            self.fields['employee'].widget = forms.HiddenInput()
            self.fields['employee'].required = False
            self.fields['code'].required = False
            self.fields['national_id'].required = True
            self.fields['department'].required = True
            self.fields['job_title'].required = True
            self.fields['hiring_date'].required = True
            self.fields['user'].required = True

    def clean_commission_rate(self):
        rate = self.cleaned_data.get('commission_rate')
        if rate is not None and (rate < 0 or rate > 100):
            raise forms.ValidationError('نسبة العمولة يجب أن تكون بين 0 و 100')
        return rate

    def clean(self):
        cleaned = super().clean()
        if not self.instance or not self.instance.pk:
            dept = cleaned.get('department')
            job = cleaned.get('job_title')
            if dept and job and job.department and job.department != dept:
                raise forms.ValidationError(
                    f"المسمى الوظيفي '{job.name}' مرتبط بإدارة '{job.department.name}'، "
                    f"ولا يمكن اختياره مع إدارة '{dept.name}'."
                )
        return cleaned

class SalesInvoiceForm(forms.ModelForm):
    class Meta:
        model = SalesInvoice
        fields = ['date', 'customer', 'payment_type', 'sales_rep', 'cash_box', 'cost_center', 'due_date', 'notes']
        labels = {
            'date': 'تاريخ الفاتورة',
            'customer': 'العميل',
            'payment_type': 'نوع الدفع',
            'sales_rep': 'المندوب',
            'cash_box': 'الخزينة',
            'cost_center': 'مركز التكلفة',
            'due_date': 'تاريخ الاستحقاق',
            'notes': 'ملاحظات',
        }
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'payment_type': forms.Select(attrs={'class': 'form-select'}),
            'sales_rep': forms.Select(attrs={'class': 'form-select'}),
            'cash_box': forms.Select(attrs={'class': 'form-select'}),
            'cost_center': forms.Select(attrs={'class': 'form-select'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        self.user = user
        super().__init__(*args, **kwargs)
        if 'date' in self.fields and not self.instance.pk:
            self.fields['date'].initial = date_type.today()
        if 'cost_center' in self.fields:
            self.fields['cost_center'].queryset = CostCenter.objects.filter(is_active=True, is_leaf=True).order_by('code')
            self.fields['cost_center'].disabled = True
        if user and 'cash_box' in self.fields:
            self.fields['cash_box'].queryset = get_available_cash_boxes(user)
            
            # Default cost center to "Sales" (code='20')
            cc_sales = CostCenter.objects.filter(code='20', is_active=True).first()
            if not cc_sales:
                cc_sales = CostCenter.objects.filter(name__contains='مبيعات', is_active=True).first()
            if cc_sales:
                self.fields['cost_center'].initial = cc_sales

        if self.user and not self.user.is_superuser:
            if 'due_date' in self.fields:
                self.fields['due_date'].widget.attrs['readonly'] = True
                self.fields['due_date'].widget.attrs['class'] += ' bg-light'

    def clean(self):
        cleaned = super().clean()
        inv_date = cleaned.get('date')
        due_date = cleaned.get('due_date')
        
        # Enforce that the invoice date is strictly within the current month
        if inv_date:
            today = date_type.today()
            if inv_date.year != today.year or inv_date.month != today.month:
                self.add_error('date', 'غير مسموح بإنشاء فاتورة بتاريخ خارج حدود الشهر الحالي.')

        payment_type = cleaned.get('payment_type')
        customer = cleaned.get('customer')

        # Auto-calculate and enforce due_date for non-admins
        if getattr(self, 'user', None) and not self.user.is_superuser:
            if payment_type == 'cash':
                cleaned['due_date'] = inv_date
            elif payment_type == 'credit' and customer and inv_date:
                days = customer.payment_terms_days if customer.payment_terms_days is not None else 30
                if customer.customer_type == 'cash':
                    days = 20
                cleaned['due_date'] = inv_date + timedelta(days=days)
            due_date = cleaned.get('due_date')
                
        if inv_date and due_date and due_date < inv_date:
            self.add_error('due_date', 'تاريخ الاستحقاق يجب أن يكون بعد أو يساوي تاريخ الفاتورة')
            
        if payment_type == 'credit':
            cleaned['cash_box'] = None
            self.instance.cash_box = None
            if 'cash_box' in self._errors:
                del self._errors['cash_box']
                
        return cleaned

class SalesInvoiceLineForm(forms.ModelForm):
    class Meta:
        model = SalesInvoiceLine
        fields = ['item', 'warehouse', 'unit', 'quantity', 'unit_price', 'discount_percent', 'tax_type', 'tax_percent', 'tax_type2', 'tax_percent2', 'total']
        labels = {
            'item': 'الصنف',
            'warehouse': 'المستودع',
            'unit': 'الوحدة',
            'quantity': 'الكمية',
            'unit_price': 'سعر الوحدة',
            'discount_percent': 'نسبة الخصم (%)',
            'tax_type': 'نوع الضريبة 1',
            'tax_type2': 'نوع الضريبة 2',
        }
        widgets = {
            'item': forms.Select(attrs={'class': 'form-select item-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select warehouse-select'}),
            'unit': forms.Select(attrs={'class': 'form-select unit-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control qty-input', 'step': 'any'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control price-input', 'step': 'any'}),
            'discount_percent': forms.NumberInput(attrs={'class': 'form-control discount-input bg-light', 'step': 'any', 'readonly': 'readonly'}),
            'tax_type': forms.Select(attrs={'class': 'form-select tax-select', 'style': 'pointer-events: none; background-color: #e9ecef;', 'tabindex': '-1'}),
            'tax_percent': forms.HiddenInput(attrs={'class': 'tax-rate'}),
            'tax_type2': forms.Select(attrs={'class': 'form-select tax-select2', 'style': 'pointer-events: none; background-color: #e9ecef;', 'tabindex': '-1'}),
            'tax_percent2': forms.HiddenInput(attrs={'class': 'tax-rate2'}),
            'total': forms.HiddenInput(attrs={'class': 'total-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.db.models import Q
        tax_qs = TaxType.objects.filter(appear_in_invoices=True, is_active=True).filter(
            Q(name__icontains='مخرجات') | Q(name__icontains='مبيعات')
        )
        self.fields['tax_type'].queryset = tax_qs
        self.fields['tax_type2'].queryset = tax_qs

    def clean_quantity(self):
        qty = self.cleaned_data.get('quantity')
        if qty is not None and qty <= 0:
            raise forms.ValidationError('يجب أن تكون الكمية أكبر من صفر')
        return qty

    def clean_unit_price(self):
        price = self.cleaned_data.get('unit_price')
        if price is not None and price < 0:
            raise forms.ValidationError('سعر الوحدة لا يمكن أن يكون سالباً')
        return price

    def clean_discount_percent(self):
        disc = self.cleaned_data.get('discount_percent')
        if disc is None:
            return 0
        if disc < 0:
            raise forms.ValidationError('نسبة الخصم لا يمكن أن تكون سالبة')
        if disc > 100:
            raise forms.ValidationError('نسبة الخصم لا يمكن أن تتجاوز 100%')
        return disc

    def clean_extra_discount_percent(self):
        disc = self.cleaned_data.get('extra_discount_percent')
        if disc is None:
            return 0
        if disc < 0:
            raise forms.ValidationError('نسبة الخصم الإضافي لا يمكن أن تكون سالبة')
        if disc > 100:
            raise forms.ValidationError('نسبة الخصم الإضافي لا يمكن أن تتجاوز 100%')
        return disc

    def clean_tax_percent(self):
        tax = self.cleaned_data.get('tax_percent')
        if tax is None:
            return 0
        if tax < 0 or tax > 100:
            raise forms.ValidationError('نسبة الضريبة يجب أن تكون بين 0 و 100')
        return tax

    def clean_tax_percent2(self):
        tax = self.cleaned_data.get('tax_percent2')
        if tax is None:
            return 0
        if tax < 0 or tax > 100:
            raise forms.ValidationError('نسبة الضريبة 2 يجب أن تكون بين 0 و 100')
        return tax

    def clean_total(self):
        from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
        total = self.cleaned_data.get('total')
        if total is None:
            return Decimal('0.00')
        try:
            return Decimal(str(total)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except InvalidOperation:
            return Decimal('0.00')

class BaseSalesInvoiceLineFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
            
        items = []
        for form in self.forms:
            if self.can_delete and self._should_delete_form(form):
                continue
            item = form.cleaned_data.get('item')
            if item:
                if item in items:
                    form.add_error('item', 'هذا الصنف مكرر في الفاتورة. يرجى تجميع الكميات في سطر واحد.')
                items.append(item)

SalesInvoiceLineFormSet = inlineformset_factory(
    SalesInvoice, SalesInvoiceLine,
    form=SalesInvoiceLineForm,
    formset=BaseSalesInvoiceLineFormSet,
    extra=1,
    can_delete=True
)


class CustomerReceiptForm(forms.ModelForm):
    class Meta:
        model = CustomerReceipt
        fields = [
            'date', 'customer', 'amount', 'payment_method', 
            'bank_account', 'cash_box', 'intermediary_company',
            'cheque_number', 'cheque_due_date', 'reference'
        ]
        labels = {
            'date': 'تاريخ التحصيل',
            'customer': 'العميل',
            'amount': 'المبلغ',
            'payment_method': 'طريقة الدفع',
            'bank_account': 'الحساب البنكي',
            'cash_box': 'الخزينة',
            'intermediary_company': 'الشركة الوسيطة',
            'cheque_number': 'رقم الشيك',
            'cheque_due_date': 'تاريخ استحقاق الشيك',
            'reference': 'رقم المرجع',
        }
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'bank_account': forms.Select(attrs={'class': 'form-select'}),
            'cash_box': forms.Select(attrs={'class': 'form-select'}),
            'intermediary_company': forms.Select(attrs={'class': 'form-select'}),
            'cheque_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'رقم الشيك'}),
            'cheque_due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reference': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['cash_box'].queryset = get_available_cash_boxes(user, exclude_rep_boxes=True)
            if hasattr(user, 'salesrepresentative'):
                self.fields['payment_method'].choices = [('cash', 'نقدي')]

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is not None and amount <= 0:
            raise forms.ValidationError('يجب أن يكون المبلغ أكبر من صفر')
        return amount

    def clean_date(self):
        d = self.cleaned_data.get('date')
        if d and d > date_type.today():
            raise forms.ValidationError('تاريخ التحصيل لا يمكن أن يكون في المستقبل')
        return d

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get('payment_method')
        bank = cleaned.get('bank_account')
        cash = cleaned.get('cash_box')
        intermediary = cleaned.get('intermediary_company')
        cheque = cleaned.get('cheque_number')
        chq_date = cleaned.get('cheque_due_date')
        rcp_date = cleaned.get('date')

        if method == 'cash' and not cash:
            self.add_error('cash_box', 'يجب تحديد الخزينة للدفع النقدي')
        if method == 'bank' and not bank:
            self.add_error('bank_account', 'يجب تحديد الحساب البنكي للتحويل')
        if method == 'intermediary' and not intermediary:
            self.add_error('intermediary_company', 'يجب تحديد الشركة الوسيطة')
        if method == 'cheque':
            if not cheque:
                self.add_error('cheque_number', 'يجب إدخال رقم الشيك')
            if not chq_date:
                self.add_error('cheque_due_date', 'يجب إدخال تاريخ استحقاق الشيك')
            if chq_date and rcp_date and chq_date < rcp_date:
                self.add_error('cheque_due_date', 'تاريخ استحقاق الشيك يجب أن يكون بعد أو يساوي تاريخ التحصيل')
        return cleaned



class QuotationForm(forms.ModelForm):
    class Meta:
        model = Quotation
        fields = ['name', 'customer', 'sector', 'start_date', 'end_date', 'status', 'is_active', 'notes']
        labels = {
            'name': 'اسم العرض',
            'customer': 'العميل',
            'sector': 'القطاع',
            'start_date': 'تاريخ البداية',
            'end_date': 'تاريخ الانتهاء',
            'status': 'الحالة',
            'is_active': 'نشط',
            'notes': 'ملاحظات',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'sector': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean(self):
        cleaned_data = super().clean()
        customer = cleaned_data.get('customer')
        sector = cleaned_data.get('sector')
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        status = cleaned_data.get('status')
        is_active = cleaned_data.get('is_active')

        if not customer and not sector:
            raise forms.ValidationError("يجب تحديد إما 'القطاع المستهدف' أو 'العميل المحدد' لإنشاء العرض.")
            
        if customer and sector:
            raise forms.ValidationError("لا يمكن اختيار قطاع وعميل معاً. يرجى اختيار إما قطاع كامل أو عميل محدد لتطبيق الخصم.")

        if start_date and end_date:
            if start_date > end_date:
                self.add_error('end_date', "تاريخ الانتهاء يجب أن يكون بعد أو يساوي تاريخ البدء.")
            
            if status not in ['expired', 'cancelled'] and is_active:
                if sector:
                    # Check for overlapping active quotations for the same sector
                    overlapping_qs = Quotation.objects.filter(
                        sector=sector,
                        status__in=['draft', 'active', 'invoiced'],
                        is_active=True,
                        start_date__lte=end_date,
                        end_date__gte=start_date
                    )
                    if self.instance and self.instance.pk:
                        overlapping_qs = overlapping_qs.exclude(pk=self.instance.pk)
                    if overlapping_qs.exists():
                        raise forms.ValidationError("لا يمكن إنشاء عرض لنفس القطاع في نفس الفترة الزمنية لوجود عرض آخر ساري ومفعل لهذا القطاع.")
                        
                elif customer:
                    # Check for overlapping active quotations for the same customer
                    overlapping_qs = Quotation.objects.filter(
                        customer=customer,
                        status__in=['draft', 'active', 'invoiced'],
                        is_active=True,
                        start_date__lte=end_date,
                        end_date__gte=start_date
                    )
                    if self.instance and self.instance.pk:
                        overlapping_qs = overlapping_qs.exclude(pk=self.instance.pk)
                    if overlapping_qs.exists():
                        raise forms.ValidationError("لا يمكن إنشاء عرض لنفس العميل في نفس الفترة الزمنية لوجود عرض آخر ساري ومفعل له.")
                    
        return cleaned_data

class QuotationLineForm(forms.ModelForm):
    class Meta:
        model = QuotationLine
        fields = ['item', 'discount_percent']
        labels = {
            'item': 'الصنف',
            'discount_percent': 'نسبة الخصم (%)',
        }
        widgets = {
            'item': forms.Select(attrs={'class': 'form-select'}),
            'discount_percent': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
        }

class QuotationLineFormSet(forms.BaseInlineFormSet):
    pass

QuotationLineFormSet = inlineformset_factory(
    Quotation, QuotationLine,
    form=QuotationLineForm,
    extra=1,
    can_delete=True
)

class PriceListForm(forms.ModelForm):
    class Meta:
        model = PriceList
        fields = ['name', 'is_default', 'is_active']
        labels = {
            'name': 'اسم قائمة الأسعار',
            'is_default': 'افتراضية',
            'is_active': 'نشطة',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned = super().clean()
        is_default = cleaned.get('is_default')
        is_active = cleaned.get('is_active')
        if is_default:
            qs = PriceList.objects.filter(is_default=True)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError('يوجد بالفعل قائمة أسعار افتراضية. قم بإلغاء تفعيلها أولاً.')
        if not is_active and is_default:
            raise forms.ValidationError('القائمة غير النشطة لا يمكن أن تكون افتراضية')
        return cleaned

class PriceListItemForm(forms.ModelForm):
    class Meta:
        model = PriceListItem
        fields = ['item', 'unit_price', 'min_qty']
        labels = {
            'item': 'الصنف',
            'unit_price': 'سعر الوحدة',
            'min_qty': 'الحد الأدنى للكمية',
        }
        widgets = {
            'item': forms.Select(attrs={'class': 'form-select'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'min_qty': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001'}),
        }

    def clean_unit_price(self):
        price = self.cleaned_data.get('unit_price')
        if price is not None and price <= 0:
            raise forms.ValidationError('سعر الوحدة يجب أن يكون أكبر من صفر')
        return price

    def clean_min_qty(self):
        qty = self.cleaned_data.get('min_qty')
        if qty is not None and qty <= 0:
            raise forms.ValidationError('الحد الأدنى للكمية يجب أن يكون أكبر من صفر')
        return qty

PriceListItemFormSet = inlineformset_factory(
    PriceList, PriceListItem,
    form=PriceListItemForm,
    extra=1,
    can_delete=True
)

class SalesReturnLineForm(forms.ModelForm):
    class Meta:
        model = SalesReturnLine
        fields = ['item', 'warehouse', 'unit', 'quantity', 'unit_price', 'discount_percent', 'tax_type', 'tax_percent', 'tax_type2', 'tax_percent2', 'total', 'return_account', 'cogs_account']
        labels = {
            'item': 'الصنف',
            'warehouse': 'المستودع',
            'unit': 'الوحدة',
            'quantity': 'الكمية',
            'unit_price': 'سعر الوحدة',
            'discount_percent': 'نسبة الخصم (%)',
            'tax_type': 'نوع الضريبة 1',
            'tax_type2': 'نوع الضريبة 2',
            'return_account': 'حساب المرتجع',
            'cogs_account': 'حساب تكلفة المبيعات',
        }
        widgets = {
            'item': forms.Select(attrs={'class': 'form-select item-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'unit': forms.Select(attrs={'class': 'form-select unit-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control qty-input', 'step': 'any'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control price-input', 'step': 'any'}),
            'discount_percent': forms.NumberInput(attrs={'class': 'form-control discount-input bg-light', 'step': 'any', 'readonly': 'readonly'}),
            'tax_type': forms.Select(attrs={'class': 'form-select tax-select', 'style': 'pointer-events: none; background-color: #e9ecef;', 'tabindex': '-1'}),
            'tax_percent': forms.HiddenInput(attrs={'class': 'tax-rate'}),
            'tax_type2': forms.Select(attrs={'class': 'form-select tax-select2', 'style': 'pointer-events: none; background-color: #e9ecef;', 'tabindex': '-1'}),
            'tax_percent2': forms.HiddenInput(attrs={'class': 'tax-rate2'}),
            'total': forms.HiddenInput(attrs={'class': 'total-input'}),
            'return_account': forms.Select(attrs={'class': 'form-select return-account-select', 'style': 'pointer-events: none; background-color: #e9ecef;', 'tabindex': '-1'}),
            'cogs_account': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        from django.db.models import Q
        tax_qs = TaxType.objects.filter(appear_in_invoices=True, is_active=True).filter(
            Q(name__icontains='مخرجات') | Q(name__icontains='مبيعات')
        )
        self.fields['tax_type'].queryset = tax_qs
        if 'tax_type2' in self.fields:
            self.fields['tax_type2'].queryset = tax_qs
            
        self.fields['return_account'].required = False
        self.fields['cogs_account'].required = False
        
        try:
            default_ret_acc = Account.objects.get(code=getattr(settings, 'DEFAULT_SALES_RETURN_ACCOUNT', '413'))
            self.fields['return_account'].initial = default_ret_acc
        except Account.DoesNotExist:
            self.fields['return_account'].initial = None
            
        try:
            default_cogs_acc = Account.objects.get(code=getattr(settings, 'DEFAULT_COGS_ACCOUNT', '511'))
            self.fields['cogs_account'].initial = default_cogs_acc
        except Account.DoesNotExist:
            self.fields['cogs_account'].initial = None

    def clean_quantity(self):
        qty = self.cleaned_data.get('quantity')
        if qty is not None and qty <= 0:
            raise forms.ValidationError('يجب أن تكون الكمية أكبر من صفر')
        return qty

    def clean_unit_price(self):
        price = self.cleaned_data.get('unit_price')
        if price is not None and price < 0:
            raise forms.ValidationError('سعر الوحدة لا يمكن أن يكون سالباً')
        return price

    def clean_discount_percent(self):
        disc = self.cleaned_data.get('discount_percent')
        if disc is None:
            return 0
        if disc < 0:
            raise forms.ValidationError('نسبة الخصم لا يمكن أن تكون سالبة')
        if disc > 100:
            raise forms.ValidationError('نسبة الخصم لا يمكن أن تتجاوز 100%')
        return disc

    def clean_tax_percent(self):
        tax = self.cleaned_data.get('tax_percent')
        if tax is None:
            return 0
        if tax < 0 or tax > 100:
            raise forms.ValidationError('نسبة الضريبة يجب أن تكون بين 0 و 100')
        return tax

    def clean_tax_percent2(self):
        tax = self.cleaned_data.get('tax_percent2')
        if tax is None:
            return 0
        if tax < 0 or tax > 100:
            raise forms.ValidationError('نسبة الضريبة 2 يجب أن تكون بين 0 و 100')
        return tax

    def clean_total(self):
        from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
        total = self.cleaned_data.get('total')
        if total is None:
            return Decimal('0.00')
        try:
            return Decimal(str(total)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except InvalidOperation:
            return Decimal('0.00')

class SalesReturnLineFormSet(forms.BaseInlineFormSet):
    pass


SalesReturnLineFormSet = inlineformset_factory(
    SalesReturn, SalesReturnLine,
    form=SalesReturnLineForm,
    extra=1,
    can_delete=True
)

class CustomerSectorForm(forms.ModelForm):
    class Meta:
        model = CustomerSector
        fields = ['name', 'description']
        labels = {
            'name': 'اسم القطاع',
            'description': 'وصف',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
