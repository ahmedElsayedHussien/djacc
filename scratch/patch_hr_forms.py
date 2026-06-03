import re

def main():
    file_path = 'apps/hr/forms.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    # 1. EmployeeForm reports_to logic
    old_emp_init = """    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['user'].queryset = get_user_model().objects.filter(employee__isnull=True) | get_user_model().objects.filter(employee=self.instance)
        else:
            self.fields['user'].queryset = get_user_model().objects.filter(employee__isnull=True)"""
    new_emp_init = """    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['user'].queryset = get_user_model().objects.filter(employee__isnull=True) | get_user_model().objects.filter(employee=self.instance)
        else:
            self.fields['user'].queryset = get_user_model().objects.filter(employee__isnull=True)
            
        active_employees = Employee.objects.filter(status='active')
        if self.instance and self.instance.pk:
            active_employees = active_employees.exclude(pk=self.instance.pk)
        if 'reports_to' in self.fields:
            self.fields['reports_to'].queryset = active_employees"""
    content = content.replace(old_emp_init, new_emp_init)

    # 2. LeaveRequestForm
    old_leave_clean = """    def clean(self):
        cleaned = super().clean()
        
        return cleaned"""
    new_leave_clean = """    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        total = cleaned.get('total_days')
        
        if start and end:
            if end < start:
                raise forms.ValidationError('تاريخ نهاية الإجازة يجب أن يكون بعد تاريخ البداية')
            if total is not None:
                if total <= 0:
                    self.add_error('total_days', 'عدد الأيام يجب أن يكون أكبر من صفر')
                max_days = (end - start).days + 1
                if total > max_days:
                    self.add_error('total_days', 'عدد الأيام المدخل يتجاوز الفارق الزمني بين تاريخ البداية والنهاية')
        return cleaned"""
    content = content.replace(old_leave_clean, new_leave_clean)

    # 3. LoanForm massive financial loophole
    old_loan_clean = """    def clean(self):
        cleaned = super().clean()
        amount = cleaned.get('amount')
        installments = cleaned.get('installments_count')
        monthly = cleaned.get('monthly_installment')
        
        if installments and monthly and amount:
            if monthly * installments > amount:
                self.add_error('monthly_installment', 'إجمالي الأقساط يتجاوز قيمة السلفة')
        return cleaned"""
    new_loan_clean = """    def clean(self):
        cleaned = super().clean()
        amount = cleaned.get('amount')
        installments = cleaned.get('installments_count')
        monthly = cleaned.get('monthly_installment')
        
        if amount is not None and amount <= 0:
            self.add_error('amount', 'قيمة السلفة يجب أن تكون أكبر من صفر')
        
        if installments is not None and installments <= 0:
            self.add_error('installments_count', 'عدد الأقساط يجب أن يكون أكبر من صفر')
            
        if monthly is not None and monthly <= 0:
            self.add_error('monthly_installment', 'القسط الشهري يجب أن يكون أكبر من صفر')
            
        if installments and monthly and amount:
            total_paid = monthly * installments
            if total_paid < amount:
                self.add_error('monthly_installment', 'إجمالي الأقساط أقل من قيمة السلفة (خسارة مالية)')
            elif total_paid > amount:
                self.add_error('monthly_installment', 'إجمالي الأقساط يتجاوز قيمة السلفة')
        return cleaned"""
    content = content.replace(old_loan_clean, new_loan_clean)

    # 4. PayslipForm
    old_payslip_deductions = """    def clean_total_deductions(self):
        loan_deduction = self.cleaned_data.get('total_deductions', 0)
        if loan_deduction > 0:
            if not self.instance.employee.loans.filter(status='approved').exists():
                raise forms.ValidationError("هذا الموظف ليس لديه أي سلف نشطة في النظام.")
        return loan_deduction"""
    new_payslip_deductions = """    def clean_total_deductions(self):
        loan_deduction = self.cleaned_data.get('total_deductions', 0)
        if loan_deduction > 0:
            employee = getattr(self.instance, 'employee', None)
            if employee:
                if not employee.loans.filter(status='approved').exists():
                    raise forms.ValidationError("هذا الموظف ليس لديه أي سلف نشطة في النظام.")
        return loan_deduction

    def clean(self):
        cleaned_data = super().clean()
        additions = sum(filter(None, [
            cleaned_data.get('basic_salary', 0),
            cleaned_data.get('total_allowances', 0),
            cleaned_data.get('other_additions', 0)
        ]))
        deductions = sum(filter(None, [
            cleaned_data.get('total_deductions', 0),
            cleaned_data.get('other_deductions', 0),
            cleaned_data.get('social_insurance', 0),
            cleaned_data.get('income_tax', 0)
        ]))
        
        if deductions > additions:
            raise forms.ValidationError("إجمالي الاستقطاعات لا يمكن أن يتجاوز إجمالي الاستحقاقات (الراتب الصافي بالسالب).")
        return cleaned_data"""
    content = content.replace(old_payslip_deductions, new_payslip_deductions)

    # 5. LeaveBalanceForm
    old_bal_clean = """    def clean(self):
        cleaned = super().clean()
        
        return cleaned"""
    new_bal_clean = """    def clean(self):
        cleaned = super().clean()
        total = cleaned.get('total_days')
        used = cleaned.get('used_days')
        
        if total is not None and total < 0:
            self.add_error('total_days', 'الرصيد لا يمكن أن يكون سالباً')
        if used is not None and used < 0:
            self.add_error('used_days', 'الأيام المستخدمة لا يمكن أن تكون سالبة')
            
        if total is not None and used is not None and used > total:
            raise forms.ValidationError('الأيام المستخدمة لا يمكن أن تتجاوز إجمالي الرصيد')
        return cleaned"""
    content = content.replace(old_bal_clean, new_bal_clean)

    # 6. EOSForm
    old_eos_clean = """    def clean_termination_date(self):
        d = self.cleaned_data.get('termination_date')
        if d and d > date.today():
            raise forms.ValidationError('تاريخ إنهاء الخدمة لا يمكن أن يكون في المستقبل')
        return d"""
    new_eos_clean = """    def clean_termination_date(self):
        from django.utils.timezone import localdate
        d = self.cleaned_data.get('termination_date')
        employee = self.cleaned_data.get('employee')
        
        if d and d > localdate():
            raise forms.ValidationError('تاريخ إنهاء الخدمة لا يمكن أن يكون في المستقبل')
            
        if d and employee and employee.hiring_date and d < employee.hiring_date:
            raise forms.ValidationError('تاريخ إنهاء الخدمة لا يمكن أن يكون قبل تاريخ التعيين')
            
        return d"""
    content = content.replace(old_eos_clean, new_eos_clean)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Forms patched.")

if __name__ == '__main__':
    main()
