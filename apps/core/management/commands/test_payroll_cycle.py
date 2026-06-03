from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from apps.core.models import Account, FiscalYear, JournalEntry, JournalLine
from apps.treasury.models import CashBox
from apps.hr.models import PayrollPeriod, Payslip, Employee, EndOfService
from apps.hr.services import PayrollService, EOSService


class Command(BaseCommand):
    help = 'اختبار دورة رواتب كاملة'

    def print_entry(self, e, indent=4):
        lines = e.lines.all()
        total_dr = sum((l.debit or 0) for l in lines)
        total_cr = sum((l.credit or 0) for l in lines)
        status = '✓' if total_dr == total_cr else '✗'
        self.stdout.write(f"{' ' * indent}{status} قيد #{e.id} | {e.date} | {e.description}")
        for line in lines:
            dr_str = f'{line.debit:>8}' if line.debit else '       0'
            cr_str = f'{line.credit:>8}' if line.credit else '       0'
            self.stdout.write(f"{' ' * (indent + 2)}{line.account.code} {line.account.name}: مدين={dr_str} دائن={cr_str}")
        self.stdout.write(f"{' ' * (indent + 2)}── المجموع: مدين={total_dr} دائن={total_cr}")

    def handle(self, *args, **options):
        today = date.today()
        User = get_user_model()
        admin = User.objects.filter(is_superuser=True).first()
        if not admin:
            self.stdout.write(self.style.ERROR('لا يوجد مستخدم superuser'))
            return

        # ==================== CLEANUP ====================
        from apps.hr.models import EndOfService, Loan, LoanInstallment, Payslip
        from apps.sales.models import SalesRepresentative
        LoanInstallment.objects.all().delete()
        Loan.objects.all().delete()
        EndOfService.objects.all().delete()
        Payslip.objects.all().delete()
        PayrollPeriod.objects.all().delete()
        Employee.objects.filter(basic_salary=0).delete()
        JournalLine.objects.all().delete()
        JournalEntry.objects.all().delete()
        Employee.objects.filter(status='terminated').update(status='active')
        self.stdout.write('تم مسح بيانات الاختبار السابقة')

        # ==================== FISCAL YEAR ====================
        fy = FiscalYear.objects.filter(start_date__lte=today, end_date__gte=today).first()
        if not fy:
            fy = FiscalYear.objects.create(
                name=f'سنة مالية {today.year}', start_date=date(today.year, 1, 1),
                end_date=date(today.year, 12, 31), is_closed=False,
            )

        # ==================== SETUP ====================
        main_cash = CashBox.objects.get(code='CASH-MAIN')

        # Find or create employee with basic salary
        emp = Employee.objects.filter(basic_salary__gt=0).first()
        if not emp:
            from apps.hr.models import Department, JobTitle
            dept, _ = Department.objects.get_or_create(name='إدارة عامة')
            job, _ = JobTitle.objects.get_or_create(name='موظف رواتب', department=dept)
            emp = Employee.objects.create(
                first_name='موظف رواتب', last_name='اختبار', national_id='PAYROLL-TEST-001',
                date_of_birth=date(1990, 1, 1), department=dept, job_title=job,
                hiring_date=today, contract_type='full_time',
                basic_salary=Decimal('8000.00'),
                has_social_insurance=True, social_insurance_rate=Decimal('11.00'),
                has_taxes=True, income_tax_rate=Decimal('0.00'),
            )
        self.stdout.write(f'الموظف: {emp.full_name} — الراتب الأساسي: ${emp.basic_salary}')

        def bal(code):
            lines = JournalLine.objects.filter(account=Account.objects.get(code=code))
            dr = sum((l.debit or 0) for l in lines)
            cr = sum((l.credit or 0) for l in lines)
            return dr - cr

        def check(label, code, expected):
            actual = bal(code)
            ok = '✓' if actual == expected else '✗'
            self.stdout.write(f'  {ok} {label}: ${actual} (متوقع: ${expected})')

        # ==================== CREATE PAYROLL PERIOD ====================
        self.stdout.write('\n===== 1. إنشاء فترة رواتب وتوليد القسائم =====')
        period = PayrollPeriod.objects.create(
            name=f'راتب اختبار {today.strftime("%B %Y")}',
            start_date=date(today.year, today.month, 1),
            end_date=today,
        )
        count = PayrollService.generate_payslips_for_period(period)
        self.stdout.write(f'  تم إنشاء {count} قسيمة راتب')

        slip = period.payslips.filter(employee=emp).first()
        self.stdout.write(f'  الأساسي: ${slip.basic_salary}')
        self.stdout.write(f'  التأمينات: ${slip.social_insurance}')
        self.stdout.write(f'  الضريبة: ${slip.income_tax}')
        self.stdout.write(f'  السلف: ${slip.total_deductions}')
        self.stdout.write(f'  الصافي: ${slip.net_salary}')

        # Calculate expected values
        basic = slip.basic_salary
        insurance = slip.social_insurance
        tax = slip.income_tax
        loans = slip.total_deductions
        net = slip.net_salary

        # ==================== APPROVE ====================
        period.status = PayrollPeriod.Status.APPROVED
        period.save(update_fields=['status'])
        self.stdout.write(f'  تم اعتماد الفترة')

        # ==================== POST PAYROLL (ACCRUAL) ====================
        self.stdout.write('\n===== 2. قيد استحقاق الرواتب =====')
        PayrollService.post_payroll(period, admin)
        check(f'   مصروف رواتب (5210)', '5210', basic)
        check(f'   صافي رواتب مستحقة (2132)', '2132', Decimal(f'-{net}'))
        check(f'   تأمينات مستحقة (2133)', '2133', Decimal(f'-{insurance}'))
        if tax > 0:
            check(f'   ضريبة كسب عمل (2125)', '2125', Decimal(f'-{tax}'))

        # ==================== POST INSURANCE ====================
        self.stdout.write('\n===== 3. قيد التأمينات (حصة المنشأة) =====')
        employer_rate = Decimal('0.1875')
        PayrollService.post_insurance_entry(period, employer_rate, admin)
        employer_ins = (basic * employer_rate).quantize(Decimal('0.01'))
        check(f'   مصروف تأمينات حصة المنشأة (5214)', '5214', employer_ins)
        total_ins_payable = insurance + employer_ins
        check(f'   إجمالي تأمينات مستحقة (2133)', '2133', Decimal(f'-{total_ins_payable}'))

        # ==================== POST PAYMENT (NET SALARY) ====================
        self.stdout.write('\n===== 4. قيد صرف الرواتب =====')
        payment_acc = main_cash.account
        PayrollService.post_payment_entry(period, payment_acc, admin)
        check(f'   صافي رواتب مستحقة (2132)', '2132', Decimal('0.00'))  # cleared
        check(f'   الخزينة ({payment_acc.code})', payment_acc.code, Decimal(f'-{net}'))

        # ==================== POST GOVERNMENT PAYMENT ====================
        self.stdout.write('\n===== 5. قيد توريد الاستقطاعات للحكومة =====')
        PayrollService.post_government_payment(period, payment_acc, total_ins_payable, tax, admin)
        check(f'   تأمينات مستحقة (2133)', '2133', Decimal('0.00'))  # cleared
        check(f'   ضريبة كسب عمل (2125)', '2125', Decimal('0.00'))  # cleared
        total_gov = total_ins_payable + tax
        check(f'   الخزينة ({payment_acc.code})', payment_acc.code, Decimal(f'-{net + total_gov}'))

        # ==================== 6. LOAN + END OF SERVICE ====================
        self.stdout.write('\n===== 6. سلفة + نهاية خدمة =====')
        from apps.hr.models import Loan, LoanInstallment
        loan = Loan.objects.create(
            employee=emp, amount=Decimal('500.00'),
            installments_count=2, monthly_installment=Decimal('250.00'),
            start_month=date(today.year, today.month, 1),
            reason='سلفة اختبار', status='approved',
        )
        self.stdout.write(f'  تم إنشاء سلفة $500 (قسطان $250)')

        # Second payroll period with loan deduction
        period2 = PayrollPeriod.objects.create(
            name=f'راتب اختبار 2 {today.strftime("%B %Y")}',
            start_date=date(today.year, today.month, 1),
            end_date=today,
        )
        PayrollService.generate_payslips_for_period(period2)
        slip2 = period2.payslips.first()
        self.stdout.write(f'  القسيمة الثانية: السلف=${slip2.total_deductions} الصافي=${slip2.net_salary}')

        period2.status = PayrollPeriod.Status.APPROVED
        period2.save(update_fields=['status'])
        PayrollService.post_payroll(period2, admin)
        self.stdout.write(f'  تم ترحيل الفترة الثانية')
        check(f'   مصروف رواتب (5210) بعد الفترة الثانية', '5210', Decimal(f'{basic * 2}'))
        check(f'   السلف (1143)', '1143', Decimal('-250.00'))  # credit = loan deducted

        # End of Service
        eos = EndOfService.objects.create(
            employee=emp, termination_date=today,
            reason='اختبار نهاية خدمة',
            severance_pay=Decimal('3000.00'),
            leave_encashment=Decimal('500.00'),
            total_settlement=Decimal('3500.00'),
        )
        EOSService.process_settlement(eos, admin)
        self.stdout.write(f'  تم ترحيل نهاية خدمة $3,500')
        check(f'   السلف المتبقية (1143)', '1143', Decimal('-500.00'))  # total recovered via payroll+EOS
        emp.refresh_from_db()
        self.stdout.write(f'  حالة الموظف: {emp.status}')

        # ==================== VERIFICATION ====================
        self.stdout.write('\n' + '=' * 60)
        all_entries = JournalEntry.objects.all().order_by('date', 'id')
        self.stdout.write(f'القيود المحاسبية ({all_entries.count()}):')
        balanced = 0
        for e in all_entries:
            self.print_entry(e)
            lines = e.lines.all()
            if sum((l.debit or 0) for l in lines) == sum((l.credit or 0) for l in lines):
                balanced += 1

        self.stdout.write(f'\nالقيود المتوازنة: {balanced}/{all_entries.count()}')

        if balanced == all_entries.count() and all_entries.count() > 0:
            self.stdout.write(self.style.SUCCESS('\n✓ تم بنجاح! جميع قيود الرواتب متوازنة'))
        else:
            self.stdout.write(self.style.ERROR('\n✗ يوجد خلل في قيود الرواتب!'))
