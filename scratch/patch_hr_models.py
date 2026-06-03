import re

def main():
    file_path = 'apps/hr/models.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    # 1. Department Loop Detection
    old_dept_clean = "    def __str__(self):\n        return self.name"
    new_dept_clean = """    def clean(self):
        super().clean()
        parent = self.parent
        while parent:
            if parent == self:
                raise ValidationError({'parent': 'لا يمكن أن يكون القسم أباً لنفسه (دورة غير منتهية).'})
            parent = parent.parent

    def __str__(self):
        return self.name"""
    content = content.replace(old_dept_clean, new_dept_clean)

    # 2. Employee Loop Detection
    old_emp_clean = "    def __str__(self):\n        return f'{self.first_name} {self.last_name}'"
    new_emp_clean = """    def clean(self):
        super().clean()
        manager = self.reports_to
        while manager:
            if manager == self:
                raise ValidationError({'reports_to': 'لا يمكن أن يكون الموظف مديراً لنفسه (دورة غير منتهية).'})
            manager = manager.reports_to

    def __str__(self):
        return f'{self.first_name} {self.last_name}'"""
    content = content.replace(old_emp_clean, new_emp_clean)

    # 3. Employee save() privileges
    old_emp_save = """    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Setup initial roles based on department if user exists
        if self.user and self.department:
            from django.contrib.auth.models import Group
            group, _ = Group.objects.get_or_create(name=f'dept_{self.department.name}')
            self.user.groups.set([group])
            self.user.is_staff = True
            self.user.save()"""
    new_emp_save = """    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # We no longer override user groups and is_staff automatically here to prevent privilege escalation."""
    content = content.replace(old_emp_save, new_emp_save)

    # 4. Shift clean (Night shifts)
    old_shift_clean = """    def clean(self):
        if self.end_time <= self.start_time:
            raise ValidationError('وقت نهاية الوردية يجب أن يكون بعد وقت البداية')"""
    new_shift_clean = """    def clean(self):
        super().clean()
        pass  # Removed validation to allow night shifts that cross midnight"""
    content = content.replace(old_shift_clean, new_shift_clean)

    # 5. Payslip clean (Math Validation)
    old_payslip_str = "    def __str__(self):\n        return f'قسيمة {self.employee} - {self.period.month}/{self.period.year}'"
    new_payslip_str = """    def clean(self):
        super().clean()
        expected_net = (self.basic_salary + self.total_allowances + self.other_additions) - \\
                       (self.total_deductions + self.other_deductions + self.social_insurance + self.income_tax)
        if self.net_salary != expected_net:
            raise ValidationError(f"صافي الراتب غير صحيح. الصافي المتوقع: {expected_net}")

    def __str__(self):
        return f'قسيمة {self.employee} - {self.period.month}/{self.period.year}'"""
    content = content.replace(old_payslip_str, new_payslip_str)

    # 6. Loan clean (Math Validation)
    old_loan_str = "    def __str__(self):\n        return f'سلفة {self.employee} - {self.amount}'"
    new_loan_str = """    def clean(self):
        super().clean()
        if self.amount and self.installments_count and self.monthly_installment:
            from decimal import Decimal
            expected = Decimal(str(self.installments_count)) * self.monthly_installment
            if abs(expected - self.amount) > Decimal('0.01'):
                raise ValidationError("إجمالي الأقساط يجب أن يساوي مبلغ السلفة.")

    def __str__(self):
        return f'سلفة {self.employee} - {self.amount}'"""
    content = content.replace(old_loan_str, new_loan_str)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Models patched.")

if __name__ == '__main__':
    main()
