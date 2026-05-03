from django import forms
from .models import (
    Employee, EmployeeDocument, PayrollPeriod, 
    LeaveRequest, Loan
)

class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            'first_name', 'last_name', 'national_id', 'date_of_birth', 
            'phone', 'address', 'department', 'job_title', 'reports_to', 
            'hiring_date', 'contract_type', 'status', 'basic_salary', 
            'bank_account_number', 'user'
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
            'user': forms.Select(attrs={'class': 'form-select'}),
        }

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
