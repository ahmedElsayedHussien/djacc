from datetime import date
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.conf import settings

from apps.core.models import Account, FiscalYear, JournalEntry, JournalLine
from apps.treasury.models import CashBox, BankAccount, CashTransfer, BankTransaction
from apps.treasury.services import TreasuryService


class Command(BaseCommand):
    help = 'اختبار دورة الخزائن والبنوك كاملة'

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
        BankTransaction.objects.all().delete()
        CashTransfer.objects.all().delete()
        JournalLine.objects.all().delete()
        JournalEntry.objects.all().delete()
        # Remove any test bank accounts (delete ba first, then account to avoid ProtectedError)
        for ba in BankAccount.objects.all():
            if ba.code.startswith('TEST-'):
                ba.delete()
                ba.account.delete()
        self.stdout.write('تم مسح بيانات الاختبار السابقة')

        # ==================== FISCAL YEAR ====================
        fy = FiscalYear.objects.filter(start_date__lte=today, end_date__gte=today).first()
        if not fy:
            fy = FiscalYear.objects.create(
                name=f'سنة مالية {today.year}', start_date=date(today.year, 1, 1),
                end_date=date(today.year, 12, 31), is_closed=False,
            )

        # ==================== ACCOUNTS & SETUP ====================
        main_cash = CashBox.objects.get(code='CASH-MAIN')
        rep_cash = CashBox.objects.exclude(code='CASH-MAIN').first()
        transit_acc = Account.objects.get(code='1114')

        def bal(code):
            lines = JournalLine.objects.filter(account=Account.objects.get(code=code))
            dr = sum((l.debit or 0) for l in lines)
            cr = sum((l.credit or 0) for l in lines)
            return dr - cr

        def check(label, code, expected):
            actual = bal(code)
            ok = '✓' if actual == expected else '✗'
            self.stdout.write(f'  {ok} {label}: ${actual} (متوقع: ${expected})')

        # ==================== 1. CASH TRANSFER ====================
        self.stdout.write('\n===== 1. تحويل بين الخزن =====')
        ct = CashTransfer.objects.create(
            number='TRF-001', date=today,
            from_cash_box=main_cash, to_cash_box=rep_cash,
            amount=Decimal('500.00'), description='تحويل اختبار من رئيسية للمندوب',
        )
        TreasuryService.process_issue(ct, admin)
        self.stdout.write(f'  1.1 إصدار تحويل $500 (رئيسية ← نقدية بالطريق)')
        check(f'   الخزينة الرئيسية ({main_cash.account.code})', main_cash.account.code, Decimal('-500.00'))
        check(f'   نقدية بالطريق ({transit_acc.code})', transit_acc.code, Decimal('500.00'))

        TreasuryService.process_receive(ct, admin)
        self.stdout.write(f'  1.2 استلام تحويل $500 (نقدية بالطريق ← المندوب)')
        check(f'   نقدية بالطريق ({transit_acc.code})', transit_acc.code, Decimal('0.00'))
        check(f'   خزينة المندوب ({rep_cash.account.code})', rep_cash.account.code, Decimal('500.00'))
        check(f'   الخزينة الرئيسية ({main_cash.account.code})', main_cash.account.code, Decimal('-500.00'))

        # ==================== 2. CREATE BANK ACCOUNT ====================
        self.stdout.write('\n===== 2. إنشاء حساب بنكي =====')
        bank_acc = TreasuryService.create_bank_account({
            'code': 'TEST-BNK-001',
            'name': 'حساب اختبار بنكي',
            'bank_name': 'بنك الاختبار',
            'account_number': '123456789',
            'currency': 'EGP',
            'is_active': True,
        })
        self.stdout.write(f'  تم إنشاء الحساب البنكي: {bank_acc.name} (حساب {bank_acc.account.code})')

        # ==================== 3. CASH TO BANK TRANSFER ====================
        self.stdout.write('\n===== 3. تحويل من خزينة لبنك =====')
        ct2 = CashTransfer.objects.create(
            number='TRF-002', date=today,
            from_cash_box=main_cash, to_bank=bank_acc,
            amount=Decimal('1000.00'), description='تحويل من خزينة رئيسية للبنك',
        )
        TreasuryService.process_issue(ct2, admin)
        self.stdout.write(f'  3.1 إصدار تحويل $1,000 (رئيسية ← نقدية بالطريق)')
        check(f'   الخزينة الرئيسية ({main_cash.account.code})', main_cash.account.code, Decimal('-1500.00'))
        check(f'   نقدية بالطريق ({transit_acc.code})', transit_acc.code, Decimal('1000.00'))

        TreasuryService.process_receive(ct2, admin)
        self.stdout.write(f'  3.2 استلام تحويل $1,000 (نقدية بالطريق ← بنك)')
        check(f'   نقدية بالطريق ({transit_acc.code})', transit_acc.code, Decimal('0.00'))
        check(f'   البنك ({bank_acc.account.code})', bank_acc.account.code, Decimal('1000.00'))
        check(f'   الخزينة الرئيسية ({main_cash.account.code})', main_cash.account.code, Decimal('-1500.00'))

        # ==================== 4. BANK TRANSACTION (CHARGE) ====================
        self.stdout.write('\n===== 4. حركة بنكية: عمولة =====')
        charge_acc = Account.objects.get(code='531')
        charge = BankTransaction.objects.create(
            number='BANK-TXN-001', date=today,
            bank_account=bank_acc,
            transaction_type=BankTransaction.TransactionType.BANK_CHARGE,
            amount=Decimal('20.00'), description='عمولة بنكية شهرية',
            created_by=admin,
        )
        TreasuryService.process_bank_transaction(charge, admin)
        self.stdout.write(f'  4.1 عمولة بنكية $20')
        check(f'   مصروف عمولات ({charge_acc.code})', charge_acc.code, Decimal('20.00'))
        check(f'   البنك ({bank_acc.account.code})', bank_acc.account.code, Decimal('980.00'))  # 1000 - 20

        # ==================== 5. BANK TRANSACTION (INTEREST) ====================
        self.stdout.write('\n===== 5. حركة بنكية: فائدة =====')
        interest_acc = Account.objects.get(code='421')
        interest = BankTransaction.objects.create(
            number='BANK-TXN-002', date=today,
            bank_account=bank_acc,
            transaction_type=BankTransaction.TransactionType.INTEREST,
            amount=Decimal('10.00'), description='فائدة بنكية شهرية',
            created_by=admin,
        )
        TreasuryService.process_bank_transaction(interest, admin)
        self.stdout.write(f'  5.1 فائدة بنكية $10')
        check(f'   البنك ({bank_acc.account.code})', bank_acc.account.code, Decimal('990.00'))  # 980 + 10
        check(f'   إيراد فوائد ({interest_acc.code})', interest_acc.code, Decimal('-10.00'))  # credit

        # ==================== 6. BANK TO CASH TRANSFER ====================
        self.stdout.write('\n===== 6. تحويل من بنك لخزينة =====')
        ct3 = CashTransfer.objects.create(
            number='TRF-003', date=today,
            from_bank=bank_acc, to_cash_box=main_cash,
            amount=Decimal('500.00'), description='تحويل من البنك للخزينة',
        )
        TreasuryService.process_issue(ct3, admin)
        self.stdout.write(f'  6.1 إصدار تحويل $500 (بنك ← نقدية بالطريق)')
        check(f'   البنك ({bank_acc.account.code})', bank_acc.account.code, Decimal('490.00'))  # 990 - 500
        check(f'   نقدية بالطريق ({transit_acc.code})', transit_acc.code, Decimal('500.00'))

        TreasuryService.process_receive(ct3, admin)
        self.stdout.write(f'  6.2 استلام تحويل $500 (نقدية بالطريق ← خزينة)')
        check(f'   نقدية بالطريق ({transit_acc.code})', transit_acc.code, Decimal('0.00'))
        check(f'   البنك ({bank_acc.account.code})', bank_acc.account.code, Decimal('490.00'))
        check(f'   الخزينة الرئيسية ({main_cash.account.code})', main_cash.account.code, Decimal('-1000.00'))  # -1500 + 500

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
        self.stdout.write(f'الخزينة الرئيسية (111101): ${bal("111101")}')
        self.stdout.write(f'خزينة المندوب (111102): ${bal("111102")}')
        self.stdout.write(f'البنك ({bank_acc.account.code}): ${bal(bank_acc.account.code)}')
        self.stdout.write(f'نقدية بالطريق (1114): ${bal("1114")}')
        self.stdout.write(f'مصروف عمولات (531): ${bal("531")}')
        self.stdout.write(f'إيراد فوائد (421): ${bal("421")}')

        if balanced == all_entries.count() and all_entries.count() > 0:
            self.stdout.write(self.style.SUCCESS('\n✓ تم بنجاح! جميع قيود الخزينة متوازنة'))
        else:
            self.stdout.write(self.style.ERROR('\n✗ يوجد خلل في قيود الخزينة!'))
