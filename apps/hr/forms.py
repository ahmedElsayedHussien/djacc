from django import forms
from .models import (
    Employee, EmployeeDocument, PayrollPeriod, 
    LeaveRequest, Loan, JobTitle, Department, LeaveBalance, LeaveType, EndOfService
)

class JobTitleForm(forms.ModelForm):
    class Meta:
        model = JobTitle
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: مدير مالي'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'type', 'description', 'parent', 'cost_center']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
            'cost_center': forms.Select(attrs={'class': 'form-select'}),
        }

class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            'first_name', 'last_name', 'national_id', 'date_of_birth',
            'phone', 'address', 'department', 'job_title', 'reports_to',
            'hiring_date', 'contract_type', 'status', 'basic_salary',
            'bank_account_number',
            'has_social_insurance', 'social_insurance_rate',
            'has_taxes', 'income_tax_rate',
            'user'
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'hiring_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'job_title': forms.Select(attrs={'class': 'form-select'}),
            'reports_to': forms.Select(attrs={'class': 'form-select'}),
            'contract_type': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'basic_salary': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'has_social_insurance': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'social_insurance_rate': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'max': '100', 'step': '0.01', 'placeholder': 'مثال: 11.00'}),
            'has_taxes': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'income_tax_rate': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'max': '100', 'step': '0.01', 'placeholder': 'مثال: 10.00'}),
            'user': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # منع ربط يوزر واحد بأكثر من موظف
        # نقوم بتصفية قائمة المستخدمين لتشمل فقط من ليس لهم ملف موظف
        # أو المستخدم المرتبط حالياً بهذا الموظف (في حالة التعديل)
        from django.contrib.auth.models import User
        linked_users = Employee.objects.exclude(user__isnull=True)
        if self.instance and self.instance.pk and self.instance.user:
            linked_users = linked_users.exclude(pk=self.instance.pk)
        
        linked_user_ids = linked_users.values_list('user_id', flat=True)
        self.fields['user'].queryset = User.objects.exclude(id__in=linked_user_ids)

class EmployeeDocumentForm(forms.ModelForm):
    class Meta:
        model = EmployeeDocument
        fields = ['document_type', 'title', 'file', 'issue_date', 'expiry_date']
        widgets = {
            'document_type': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'file': forms.FileInput(attrs={'class': 'form-control'}),
            'issue_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

class PayrollPeriodForm(forms.ModelForm):
    class Meta:
        model = PayrollPeriod
        fields = ['name', 'start_date', 'end_date']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: رواتب مايو 2026'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ['leave_type', 'start_date', 'end_date', 'total_days', 'reason']
        widgets = {
            'leave_type': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'total_days': forms.NumberInput(attrs={'class': 'form-control', 'min': '0.5', 'step': '0.5'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

class LoanForm(forms.ModelForm):
    class Meta:
        model = Loan
        fields = ['amount', 'installments_count', 'monthly_installment', 'start_month', 'reason']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'installments_count': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'monthly_installment': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'start_month': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

from .models import Payslip, PayslipItem

class PayslipItemForm(forms.ModelForm):
    class Meta:
        model = PayslipItem
        fields = ['name', 'amount', 'item_type']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control item-name', 'placeholder': 'اسم البند (مثال: مكافأة مبيعات)'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control item-amount', 'placeholder': 'المبلغ', 'step': '0.01'}),
            'item_type': forms.Select(attrs={'class': 'form-select item-type'}),
        }

from django.forms import inlineformset_factory
PayslipItemFormSet = inlineformset_factory(
    Payslip, PayslipItem, form=PayslipItemForm,
    extra=0, can_delete=True
)

class PayslipForm(forms.ModelForm):
    class Meta:
        model = Payslip
        fields = [
            'basic_salary', 'total_allowances', 'other_additions', 
            'total_deductions', 'other_deductions', 
            'social_insurance', 'income_tax', 'note'
        ]
        widgets = {
            'basic_salary': forms.NumberInput(attrs={'class': 'form-control'}),
            'total_allowances': forms.NumberInput(attrs={'class': 'form-control'}),
            'other_additions': forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
            'total_deductions': forms.NumberInput(attrs={'class': 'form-control'}),
            'other_deductions': forms.NumberInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
            'social_insurance': forms.NumberInput(attrs={'class': 'form-control'}),
            'income_tax': forms.NumberInput(attrs={'class': 'form-control'}),
            'note': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'سبب الإضافة أو الخصم الإضافي...'}),
        }

    def clean_total_deductions(self):
        loan_deduction = self.cleaned_data.get('total_deductions', 0)
        if loan_deduction > 0:
            employee = self.instance.employee
            # Check if there are any approved loans
            has_active_loans = employee.loans.filter(status='approved').exists()
            if not has_active_loans:
                raise forms.ValidationError(
                    "هذا الموظف ليس لديه أي سلف نشطة/معتمدة في النظام. "
                    "الرجاء التأكد أو استخدام خانة (استقطاعات أخرى) إذا كان الخصم لسبب آخر."
                )
        return loan_deduction
from django.contrib.auth.models import User

class UserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}), label="كلمة المرور")
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}), label="تأكيد كلمة المرور")

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password != confirm_password:
            raise forms.ValidationError("كلمات المرور غير متطابقة")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user

class LeaveBalanceForm(forms.ModelForm):
    class Meta:
        model = LeaveBalance
        fields = ['leave_type', 'year', 'total_days', 'used_days']
        widgets = {
            'leave_type': forms.Select(attrs={'class': 'form-select'}),
            'year': forms.NumberInput(attrs={'class': 'form-control', 'min': '2000'}),
            'total_days': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5'}),
            'used_days': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5'}),
        }
class EOSForm(forms.ModelForm):
    class Meta:
        model = EndOfService
        fields = [
            'employee', 'termination_date', 'reason', 
            'assets_returned', 'loans_settled', 
            'severance_pay', 'leave_encashment', 'total_settlement'
        ]
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'termination_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reason': forms.TextInput(attrs={'class': 'form-control'}),
            'assets_returned': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'loans_settled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'severance_pay': forms.NumberInput(attrs={'class': 'form-control'}),
            'leave_encashment': forms.NumberInput(attrs={'class': 'form-control'}),
            'total_settlement': forms.NumberInput(attrs={'class': 'form-control'}),
        }
