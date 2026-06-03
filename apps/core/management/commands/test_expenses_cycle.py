from datetime import date
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.conf import settings

from apps.core.models import Account, FiscalYear, JournalEntry, JournalLine, TaxType
from apps.treasury.models import CashBox
from apps.expenses.models import (
    Expense, ExpenseCategory, Custody, CustodySettlement,
)
from apps.expenses.services import ExpenseService, CustodyService
from apps.hr.models import Employee, Department, JobTitle


class Command(BaseCommand):
    help = 'اختبار دورة مصروفات كاملة'

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
        CustodySettlement.objects.all().delete()
        Custody.objects.all().delete()
        Employee.objects.all().delete()
        Expense.objects.all().delete()
        ExpenseCategory.objects.all().delete()
        JournalLine.objects.all().delete()
        JournalEntry.objects.all().delete()
        self.stdout.write('تم مسح بيانات الاختبار السابقة')

        # ==================== FISCAL YEAR ====================
        fy = FiscalYear.objects.filter(start_date__lte=today, end_date__gte=today).first()
        if not fy:
            fy = FiscalYear.objects.create(
                name=f'سنة مالية {today.year}', start_date=date(today.year, 1, 1),
                end_date=date(today.year, 12, 31), is_closed=False,
            )

        # ==================== ACCOUNTS & SETUP ====================
        main_cash, _ = CashBox.objects.get_or_create(
            code='CASH-MAIN',
            defaults={
                'name': 'الخزينة الرئيسية',
                'account': Account.objects.get(code='111101'),
                'responsible_user': admin,
                'is_active': True,
            }
        )
        self.stdout.write(f'خزينة رئيسية: {main_cash.name} (حساب {main_cash.account.code})')

        # Create expense category linked to a suitable expense account
        exp_account = Account.objects.get(code='5210')  # الرواتب والأجور الأساسية
        vat_input = TaxType.objects.filter(category='vat', account__code='21212').first()
        if not vat_input:
            vat_input = TaxType.objects.create(
                name='ضريبة القيمة المضافة 14% (مدخلات)',
                category='vat',
                rate=Decimal('14.00'),
                account=Account.objects.get(code='21212'),
                is_active=True,
            )

        cat = ExpenseCategory.objects.create(
            name='مصروفات إدارية',
            account=exp_account,
        )
        self.stdout.write(f'تصنيف مصروف: {cat.name} (حساب {cat.account.code} {cat.account.name})')

        def bal(code):
            lines = JournalLine.objects.filter(account=Account.objects.get(code=code))
            dr = sum((l.debit or 0) for l in lines)
            cr = sum((l.credit or 0) for l in lines)
            return dr - cr

        def check(label, code, expected):
            actual = bal(code)
            ok = '✓' if actual == expected else '✗'
            self.stdout.write(f'  {ok} {label}: ${actual} (متوقع: ${expected})')

        # ==================== 1. CASH EXPENSE (NO TAX) ====================
        self.stdout.write('\n===== 1. مصروف نقدي بدون ضريبة =====')
        exp1 = Expense.objects.create(
            number='EXP-TEST-001', date=today,
            category=cat, subtotal=Decimal('500.00'),
            tax_amount=Decimal('0'), total=Decimal('500.00'),
            amount=Decimal('500.00'), description='مصروف اختبار نقدي',
            payment_method='cash', cash_box=main_cash,
            status=Expense.Status.DRAFT, created_by=admin,
        )
        # Approve
        exp1.status = Expense.Status.APPROVED
        exp1.approved_by = admin
        exp1.save()
        # Post
        ExpenseService.post_expense(exp1, admin)
        self.stdout.write(f'  1.1 مصروف نقدي $500 (لا ضريبة)')
        check(f'   مصروف ({exp_account.code})', exp_account.code, Decimal('500.00'))
        check(f'   الخزينة ({main_cash.account.code})', main_cash.account.code, Decimal('-500.00'))

        # ==================== 2. CASH EXPENSE (WITH VAT) ====================
        self.stdout.write('\n===== 2. مصروف نقدي مع ضريبة (14% VAT مدخلات) =====')
        subtotal2 = Decimal('1000.00')
        tax_val2 = (subtotal2 * vat_input.rate / Decimal('100')).quantize(Decimal('0.01'))  # 140
        total2 = (subtotal2 + tax_val2).quantize(Decimal('0.01'))
        exp2 = Expense.objects.create(
            number='EXP-TEST-002', date=today,
            category=cat, subtotal=subtotal2,
            tax_type=vat_input, tax_percent=vat_input.rate,
            tax_amount=tax_val2, total=total2,
            amount=total2, description='مصروف اختبار مع ضريبة',
            payment_method='cash', cash_box=main_cash,
            status=Expense.Status.DRAFT, created_by=admin,
        )
        # Approve
        exp2.status = Expense.Status.APPROVED
        exp2.approved_by = admin
        exp2.save()
        # Post
        ExpenseService.post_expense(exp2, admin)
        self.stdout.write(f'  2.1 مصروف نقدي $1,000 + ضريبة $140 = $1,140')
        check(f'   مصروف ({exp_account.code})', exp_account.code, Decimal('1500.00'))  # 500 + 1000
        check(f'   ضريبة مدخلات ({vat_input.account.code})', vat_input.account.code, Decimal('140.00'))  # DR = input VAT recoverable
        check(f'   الخزينة ({main_cash.account.code})', main_cash.account.code, Decimal('-1640.00'))  # -500 - 1140

        # ==================== 3. REVERSE FIRST EXPENSE ====================
        self.stdout.write('\n===== 3. عكس المصروف الأول =====')
        ExpenseService.reverse_expense(exp1, admin)
        self.stdout.write(f'  3.1 عكس المصروف {exp1.number}')
        check(f'   مصروف ({exp_account.code})', exp_account.code, Decimal('1000.00'))  # 1500 - 500
        check(f'   الخزينة ({main_cash.account.code})', main_cash.account.code, Decimal('-1140.00'))  # -1640 + 500

        # ==================== 4. CUSTODY FLOW ====================
        self.stdout.write('\n===== 4. دورة العهد =====')
        # Create employee
        dept, _ = Department.objects.get_or_create(name='إدارة الاختبار')
        job, _ = JobTitle.objects.get_or_create(name='موظف اختبار', department=dept)
        emp, _ = Employee.objects.get_or_create(
            national_id='CUST-TEST-001',
            defaults=dict(
                first_name='موظف', last_name='اختبار',
                date_of_birth=date(1990, 1, 1), department=dept, job_title=job,
                hiring_date=today, contract_type='full_time',
            ),
        )
        custody_acc = Account.objects.get(code='1143')  # سلف الموظفين والقروض
        # Issue custody: $2,000
        custody = Custody.objects.create(
            number='CUST-001', date=today, employee=emp,
            amount=Decimal('2000.00'), purpose='عهدة اختبار',
            account=custody_acc, cash_box=main_cash,
            created_by=admin,
        )
        CustodyService.issue_custody(custody, admin)
        self.stdout.write(f'  4.1 إصدار عهدة $2,000')
        check(f'   ذمة الموظف ({custody_acc.code})', custody_acc.code, Decimal('2000.00'))
        check(f'   الخزينة ({main_cash.account.code})', main_cash.account.code, Decimal('-3140.00'))  # -1140 - 2000

        # Post an expense against this custody
        exp3 = Expense.objects.create(
            number='EXP-TEST-003', date=today,
            category=cat, subtotal=Decimal('800.00'),
            tax_amount=Decimal('0'), total=Decimal('800.00'),
            amount=Decimal('800.00'), description='مصروف ضد العهدة',
            payment_method='custody', custody=custody,
            status=Expense.Status.DRAFT, created_by=admin,
        )
        exp3.status = Expense.Status.APPROVED
        exp3.approved_by = admin
        exp3.save()
        ExpenseService.post_expense(exp3, admin)
        self.stdout.write(f'  4.2 مصروف $800 من العهدة')
        check(f'   مصروف ({exp_account.code})', exp_account.code, Decimal('1800.00'))  # 1000 + 800
        check(f'   ذمة الموظف ({custody_acc.code})', custody_acc.code, Decimal('1200.00'))  # 2000 - 800

        # Settle custody
        settle = CustodySettlement.objects.create(
            custody=custody, date=today,
            returned_amount=Decimal('1200.00'),
            cash_box=main_cash, notes='تسوية اختبار', created_by=admin,
        )
        entry = CustodyService.settle_custody(settle, admin)
        self.stdout.write(f'  4.3 تسوية عهدة: صرف $800 + رد $1,200')
        check(f'   ذمة الموظف ({custody_acc.code})', custody_acc.code, Decimal('0.00'))  # 1200 - 1200
        check(f'   الخزينة ({main_cash.account.code})', main_cash.account.code, Decimal('-1940.00'))  # -3140 + 1200

        # ==================== VERIFICATION ====================
        self.stdout.write('\n' + '=' * 60)
        all_entries = JournalEntry.objects.filter(
            entry_type__in=['expense', 'custody']
        ).order_by('date', 'id')
        self.stdout.write(f'القيود المحاسبية ({all_entries.count()}):')
        balanced = 0
        for e in all_entries:
            self.print_entry(e)
            lines = e.lines.all()
            if sum((l.debit or 0) for l in lines) == sum((l.credit or 0) for l in lines):
                balanced += 1

        self.stdout.write(f'\nالقيود المتوازنة: {balanced}/{all_entries.count()}')

        if balanced == all_entries.count() and all_entries.count() > 0:
            self.stdout.write(self.style.SUCCESS('\n✓ تم بنجاح! جميع قيود المصروفات متوازنة'))
        else:
            self.stdout.write(self.style.ERROR('\n✗ يوجد خلل في قيود المصروفات!'))
