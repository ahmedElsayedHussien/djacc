from django import forms
from .models import Expense, ExpenseCategory, Custody
from apps.treasury.models import CashBox
from apps.core.models import Account

class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ['name', 'account']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'account': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'name': 'اسم الفئة',
            'account': 'الحساب المحاسبي المرتبط',
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
            'date', 'category', 'subtotal', 'tax_type', 'tax_percent', 
            'tax_type2', 'tax_percent2', 'description', 'cost_center',
            'payment_method', 'bank_account', 'cash_box', 'custody',
            'attachment',
        ]
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'cost_center': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'subtotal': forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01', 'step': '0.01'}),
            'tax_type': forms.Select(attrs={'class': 'form-select'}),
            'tax_percent': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'tax_type2': forms.Select(attrs={'class': 'form-select'}),
            'tax_percent2': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'payment_method': forms.Select(attrs={
                'class': 'form-select',
                'onchange': 'togglePaymentSource(this.value)'
            }),
            'bank_account': forms.Select(attrs={'class': 'form-select'}),
            'cash_box': forms.Select(attrs={'class': 'form-select'}),
            'custody': forms.Select(attrs={'class': 'form-select'}),
            'attachment': forms.FileInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'date': 'تاريخ المصروف',
            'category': 'فئة المصروف',
            'subtotal': 'المبلغ (قبل الضريبة)',
            'tax_type': 'نوع الضريبة 1',
            'tax_percent': 'نسبة الضريبة 1 %',
            'tax_type2': 'نوع الضريبة 2',
            'tax_percent2': 'نسبة الضريبة 2 %',
            'description': 'الوصف / البيان',
            'cost_center': 'مركز التكلفة',
            'payment_method': 'طريقة الدفع',
            'bank_account': 'الحساب البنكي',
            'cash_box': 'الخزنة',
            'custody': 'العهدة',
            'attachment': 'المرفقات (صورة الفاتورة)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cash_box'].queryset = CashBox.objects.exclude(
            salesrepresentative__isnull=False
        ).filter(is_active=True).order_by('name')

        from apps.core.models import CostCenter
        if 'cost_center' in self.fields:
            self.fields['cost_center'].queryset = CostCenter.objects.filter(is_active=True, is_leaf=True).order_by('code')

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
        labels = {
            'date': 'التاريخ',
            'employee': 'الموظف (المستلم)',
            'amount': 'قيمة العهدة',
            'purpose': 'الغرض من العهدة',
            'account': 'حساب العهدة (ذمة موظف)',
            'cash_box': 'خزنة الصرف',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.fields['employee'].queryset = User.objects.filter(is_active=True)
        from django.conf import settings
        custody_parent = getattr(settings, 'CUSTODY_ACCOUNTS_PARENT', '1142')
        self.fields['account'].queryset = Account.objects.filter(
            code__startswith=custody_parent, is_leaf=True
        )
        
        from apps.treasury.models import CashBox
        self.fields['cash_box'].queryset = CashBox.objects.exclude(
            salesrepresentative__isnull=False
        ).filter(is_active=True).order_by('name')
    
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

from .models import CustodySettlement

class CustodySettlementForm(forms.ModelForm):
    class Meta:
        model = CustodySettlement
        fields = ['date', 'returned_amount', 'cash_box', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'returned_amount': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
            'cash_box': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
        labels = {
            'date': 'تاريخ التسوية',
            'returned_amount': 'المبلغ المرتجع نقداً',
            'cash_box': 'الخزنة المستلمة',
            'notes': 'ملاحظات',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.treasury.models import CashBox
        self.fields['cash_box'].queryset = CashBox.objects.exclude(
            salesrepresentative__isnull=False
        ).filter(is_active=True).order_by('name')

    def clean(self):
        cleaned = super().clean()
        returned_amount = cleaned.get('returned_amount', 0)
        cash_box = cleaned.get('cash_box')
        
        if returned_amount > 0 and not cash_box:
            raise forms.ValidationError('يجب تحديد الخزنة لاستلام النقدية المرتجعة.')
            
        # ✅ Fix: Over-settlement validation in Form
        if self.instance and hasattr(self, 'custody_obj'):
            custody = self.custody_obj
            from django.db.models import Sum
            # Get expenses already posted but not yet settled
            posted_expenses = custody.expense_set.filter(status='posted', settlement__isnull=True)
            current_expenses_total = posted_expenses.aggregate(t=Sum('amount'))['t'] or 0
            
            already_settled = custody.settled_amount
            remaining = custody.amount - already_settled
            
            total_this_time = current_expenses_total + returned_amount
            
            if total_this_time > remaining:
                raise forms.ValidationError(
                    f'إجمالي المصروفات ({current_expenses_total}) + المرتجع ({returned_amount}) '
                    f'أكبر من الرصيد المتبقي للعهدة ({remaining}).'
                )
        return cleaned
