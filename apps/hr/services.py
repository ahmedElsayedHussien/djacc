"""
خدمة الرواتب — PayrollService
================================
تولّد ثلاثة قيود محاسبية مستقلة لكل مسير رواتب:

1. قيد الاستحقاق (Accrual Entry)
   مدين:
     - مصروف الأجور والرواتب       (521)  — بمركز تكلفة كل إدارة
     - مصروف بدل السكن             (5211) — بمركز تكلفة كل إدارة
     - مصروف بدل الانتقال          (5212) — بمركز تكلفة كل إدارة
     - مصروف بدلات وإضافات أخرى   (5213) — بمركز تكلفة كل إدارة
   دائن:
     - سلف العاملين والقروض        (1143) — لكل موظف بسلفته
     - التأمينات ح/ الموظف (وسيط) (2124) — بمركز تكلفة كل إدارة
     - رواتب وأجور مستحقة          (2133) — بمركز تكلفة كل إدارة

2. قيد التأمينات (Insurance Entry) — يُولَّد عند طلبه
   مدين:
     - مصروف التأمينات (حصة المنشأة) (5214) — بمركز تكلفة كل إدارة
     - التأمينات ح/ الموظف (وسيط)   (2124) — بمركز تكلفة كل إدارة (إقفاله)
   دائن:
     - الهيئة العامة للتأمينات       (2127)

3. قيد السداد للموظفين (Payment Entry)
   مدين:  رواتب مستحقة (2133)
   دائن:  البنك / الخزينة

"""
from django.db import transaction
from django.db.models import Sum
from decimal import Decimal
from collections import defaultdict

from apps.core.models import JournalEntry, Account, AccountType, CostCenter
from apps.core.services import JournalService, AuditService
from .models import PayrollPeriod, Payslip


# ─────────────────────────────────────────────────────────────────────────────
# مساعد: جلب أو إنشاء حساب في دليل الحسابات
# ─────────────────────────────────────────────────────────────────────────────
def _get_or_create_account(code, name, parent_code, account_type):
    # ✅ Fix: Use select_for_update() to prevent race conditions during account creation
    parent = Account.objects.select_for_update().get(code=parent_code)
    acc, _ = Account.objects.get_or_create(
        code=code,
        defaults={
            'name': name,
            'parent': parent,
            'account_type': account_type,
            'is_leaf': True,
        }
    )
    return acc


class PayrollService:

    # ─────────────────────────────────────────────────────────────────────────
    # الشرائح الضريبية المصرية (قانون الضرائب - السنوية)
    # ─────────────────────────────────────────────────────────────────────────
    TAX_BRACKETS = [
        (Decimal('15000'), Decimal('0.00')),      # إعفاء
        (Decimal('30000'), Decimal('0.01')),      # 1%
        (Decimal('45000'), Decimal('0.025')),     # 2.5%
        (Decimal('60000'), Decimal('0.05')),      # 5%
        (Decimal('200000'), Decimal('0.10')),     # 10%
        (Decimal('400000'), Decimal('0.15')),     # 15%
        (Decimal('600000'), Decimal('0.20')),     # 20%
        (Decimal('999999999'), Decimal('0.25')),  # 25% (حد أقصى)
    ]

    @staticmethod
    def _calculate_income_tax_brackets(annual_taxable: Decimal) -> Decimal:
        """
        يحسب ضريبة كسب العمل الشهرية باستخدام الشرائح المصرية.
        يتم تقسيمannual_taxable على 12 للحصول على الراتب الشهري.
        """
        if annual_taxable <= 0:
            return Decimal('0')

        monthly_taxable = annual_taxable / 12
        monthly_tax = Decimal('0')

        prev_limit = Decimal('0')
        for limit, rate in PayrollService.TAX_BRACKETS:
            bracket_size = limit - prev_limit
            if monthly_taxable <= limit:
                taxable_in_bracket = min(monthly_taxable - prev_limit, bracket_size)
                monthly_tax += taxable_in_bracket * rate
                break
            else:
                monthly_tax += bracket_size * rate
                prev_limit = limit

        return monthly_tax.quantize(Decimal('0.01'))

    # ─────────────────────────────────────────────────────────────────────────
    # الدالة الرئيسية: قيد الاستحقاق
    # ─────────────────────────────────────────────────────────────────────────
    @staticmethod
    @transaction.atomic
    def post_payroll(period: PayrollPeriod, posted_by) -> JournalEntry:
        """
        يرحّل فترة الرواتب ويُنشئ قيد الاستحقاق التفصيلي مع مراكز التكلفة.
        ✅ Fix #6: يتطلب حالة APPROVED قبل الترحيل.
        """
        if period.status == PayrollPeriod.Status.POSTED:
            raise ValueError("هذه الفترة مرحلة بالفعل.")
        # ✅ Bug #6 Fix: منع القفز من DRAFT مباشرة إلى POSTED
        if period.status != PayrollPeriod.Status.APPROVED:
            raise ValueError(
                "يجب اعتماد فترة الرواتب أولاً قبل الترحيل المحاسبي. الحالة الحالية: "
                + period.get_status_display()
            )

        payslips = period.payslips.select_related(
            'employee', 'employee__department', 'employee__department__cost_center'
        ).all()

        if not payslips.exists():
            raise ValueError("لا يوجد قسائم رواتب في هذه الفترة للترحيل.")

        # ── الحسابات الرئيسية (حسب المعايير المحاسبية والتوجيه الصحيح) ─────────────────
        salary_acc    = _get_or_create_account('5210', 'الرواتب والأجور الأساسية',         '521', AccountType.EXPENSE)
        other_add_acc = _get_or_create_account('5213', 'مصروف بدلات وإضافات أخرى',       '521', AccountType.EXPENSE)
        ins_emp_acc   = _get_or_create_account('2133', 'تأمينات اجتماعية مستحقة',          '213', AccountType.LIABILITY)
        payable_acc   = _get_or_create_account('2132', 'رواتب وأجور مستحقة',              '213', AccountType.LIABILITY)
        loan_acc      = _get_or_create_account('1143', 'سلف الموظفين والقروض',            '114', AccountType.ASSET)
        other_ded_acc = _get_or_create_account('2126', 'استقطاعات أخرى من الموظفين',     '212', AccountType.LIABILITY)
        tax_acc       = _get_or_create_account('2125', 'مصلحة الضرائب - كسب عمل',         '212', AccountType.LIABILITY)

        lines = []

        # ── تجميع البيانات حسب مركز التكلفة (الإدارة) ────────────────────
        by_cc = defaultdict(lambda: {
            'basic': Decimal(0), 'allowances': Decimal(0),
            'additions': Decimal(0),
            'insurance': Decimal(0),
            'tax': Decimal(0),
            'net': Decimal(0), 'other_ded': Decimal(0),
            'loans': Decimal(0),
        })

        for slip in payslips:
            cc = slip.employee.department.cost_center if (
                slip.employee.department and slip.employee.department.cost_center
            ) else None

            by_cc[cc]['basic']      += slip.basic_salary or Decimal(0)
            by_cc[cc]['allowances'] += slip.total_allowances or Decimal(0)
            by_cc[cc]['additions']  += slip.other_additions or Decimal(0)
            # ✅ Bug #1 Fix: net_salary يشمل البدلات والإضافات، لذا يتوازن القيد
            by_cc[cc]['net']        += slip.net_salary or Decimal(0)
            by_cc[cc]['other_ded']  += slip.other_deductions or Decimal(0)
            by_cc[cc]['tax']        += slip.income_tax or Decimal(0)

            if slip.employee.has_social_insurance and slip.social_insurance:
                by_cc[cc]['insurance'] += slip.social_insurance

            if slip.total_deductions and slip.total_deductions > 0:
                by_cc[cc]['loans'] += slip.total_deductions

        # ── بناء سطور المدين والدائن لكل مركز تكلفة ─────────────────────
        for cc, totals in by_cc.items():

            # ✦ مصروف الأجور الأساسي
            if totals['basic'] > 0:
                lines.append({
                    'account': salary_acc,
                    'cost_center': cc,
                    'debit': totals['basic'],
                    'credit': 0,
                    'description': f'مصروف الأجور والرواتب - {cc or "بدون مركز تكلفة"}',
                })

            # ✦ مصروف البدلات الثابتة
            if totals['allowances'] > 0:
                lines.append({
                    'account': other_add_acc,
                    'cost_center': cc,
                    'debit': totals['allowances'],
                    'credit': 0,
                    'description': f'مصروف البدلات الثابتة - {cc or "بدون مركز تكلفة"}',
                })

            # ✦ مصروف الإضافات الأخرى (مكافآت...)
            if totals['additions'] > 0:
                lines.append({
                    'account': other_add_acc,
                    'cost_center': cc,
                    'debit': totals['additions'],
                    'credit': 0,
                    'description': f'مصروف إضافات أخرى - {cc or "بدون مركز تكلفة"}',
                })

            # ✦ التأمينات (حساب وسيط - دائن)
            if totals['insurance'] > 0:
                lines.append({
                    'account': ins_emp_acc,
                    'cost_center': cc,
                    'debit': 0,
                    'credit': totals['insurance'],
                    'description': f'تأمينات اجتماعية حصة الموظف - {cc or "بدون مركز تكلفة"}',
                })

            # ✦ الاستقطاعات الأخرى
            if totals['other_ded'] > 0:
                lines.append({
                    'account': other_ded_acc,
                    'cost_center': cc,
                    'debit': 0,
                    'credit': totals['other_ded'],
                    'description': f'استقطاعات أخرى - {cc or "بدون مركز تكلفة"}',
                })

            # ✦ ضريبة كسب العمل
            if totals['tax'] > 0:
                lines.append({
                    'account': tax_acc,
                    'cost_center': cc,
                    'debit': 0,
                    'credit': totals['tax'],
                    'description': f'ضريبة كسب العمل - {cc or "بدون مركز تكلفة"}',
                })

            # ✦ رواتب مستحقة (الصافي — يشمل البدلات والإضافات)
            if totals['net'] > 0:
                lines.append({
                    'account': payable_acc,
                    'cost_center': cc,
                    'debit': 0,
                    'credit': totals['net'],
                    'description': f'صافي رواتب مستحقة - {cc or "بدون مركز تكلفة"}',
                })

            # ✦ سلف الموظفين (استرداد)
            if totals['loans'] > 0:
                lines.append({
                    'account': loan_acc,
                    'cost_center': cc,
                    'debit': 0,
                    'credit': totals['loans'],
                    'description': f'استرداد سلف - {cc or "بدون مركز تكلفة"}',
                })

        # ── إنشاء القيد ───────────────────────────────────────────────────
        entry = JournalService.create_entry(
            date_val=period.end_date,
            entry_type=JournalEntry.EntryType.MANUAL,
            description=f'قيد استحقاق الرواتب - {period.name}',
            lines=lines,
            source_document=period,
            created_by=posted_by,
        )

        period.journal_entry = entry
        period.status = PayrollPeriod.Status.POSTED
        period.save()

        AuditService.log(posted_by, 'Post', period, f'ترحيل مسير رواتب - {period.name}')
        return entry

    # ─────────────────────────────────────────────────────────────────────────
    # قيد التأمينات الاجتماعية (حصة المنشأة + إقفال حساب حصة الموظف)
    # ─────────────────────────────────────────────────────────────────────────
    @staticmethod
    @transaction.atomic
    def post_insurance_entry(period: PayrollPeriod, employer_rate: Decimal, posted_by) -> JournalEntry:
        """
        يُولِّد قيد التأمينات الاجتماعية (حصة المنشأة):
          مدين: مصروف تأمينات حصة المنشأة (5214)
          دائن: تأمينات اجتماعية مستحقة (2133)
        """
        payslips = period.payslips.select_related(
            'employee__department__cost_center'
        ).filter(employee__has_social_insurance=True)

        if not payslips.exists():
            raise ValueError("لا يوجد موظفون خاضعون للتأمينات الاجتماعية في هذه الفترة.")

        ins_expense_acc = _get_or_create_account('5214', 'حصة المنشأة في التأمينات الاجتماعية', '521', AccountType.EXPENSE)
        ins_payable_acc = _get_or_create_account('2133', 'تأمينات اجتماعية مستحقة', '213', AccountType.LIABILITY)

        lines = []
        total_employer_ins = Decimal(0)

        for slip in payslips:
            cc = slip.employee.department.cost_center if (
                slip.employee.department and slip.employee.department.cost_center
            ) else None
            
            if slip.social_insurance:
                # حساب حصة الشركة بناءً على ما خُصم من الموظف والنسبة المدخلة
                # (بافتراض أن خصم الموظف هو 11% والشركة 18.75% مثلاً)
                # هنا نستخدم الـ employer_rate الممررة (مثلاً 0.1875)
                # ولكن عادة النسبة تُطبق على "الأجر التأميني". للتبسيط سنحسبها كنسبة من الأساسي
                employer_ins = (slip.basic_salary * employer_rate).quantize(Decimal('0.01'))

                if employer_ins > 0:
                    lines.append({
                        'account': ins_expense_acc,
                        'cost_center': cc,
                        'debit': employer_ins,
                        'credit': 0,
                        'description': f'مصروف تأمينات حصة المنشأة - {slip.employee}',
                    })
                    total_employer_ins += employer_ins

        if total_employer_ins > 0:
            lines.append({
                'account': ins_payable_acc,
                'debit': 0,
                'credit': total_employer_ins,
                'description': f'إجمالي تأمينات حصة المنشأة - {period.name}',
            })

            entry = JournalService.create_entry(
                date_val=period.end_date,
                entry_type=JournalEntry.EntryType.MANUAL,
                description=f'قيد حصة المنشأة في التأمينات - {period.name}',
                lines=lines,
                source_document=period,
                created_by=posted_by,
            )
            period.insurance_entry = entry
            period.save(update_fields=['insurance_entry'])
            AuditService.log(posted_by, 'Post', period, f'ترحيل حصة المنشأة في التأمينات - {period.name}')
            return entry
        
        raise ValueError("لم يتم حساب أي مبالغ لحصة المنشأة.")

    # ─────────────────────────────────────────────────────────────────────────
    # قيد سداد الرواتب (من حساب البنك أو الخزينة)
    # ─────────────────────────────────────────────────────────────────────────
    @staticmethod
    @transaction.atomic
    def post_payment_entry(period: PayrollPeriod, payment_account: Account, posted_by) -> JournalEntry:
        """
        يُولِّد قيد صرف الرواتب:
          مدين: رواتب مستحقة (2133) — بمراكز التكلفة
          دائن: البنك / الخزينة
        """
        payslips = period.payslips.select_related('employee__department__cost_center').all()

        payable_acc = _get_or_create_account('2132', 'رواتب وأجور مستحقة', '213', AccountType.LIABILITY)

        by_cc = defaultdict(lambda: Decimal(0))
        for slip in payslips:
            cc = slip.employee.department.cost_center if (
                slip.employee.department and slip.employee.department.cost_center
            ) else None
            by_cc[cc] += slip.net_salary or Decimal(0)

        total_net = Decimal(0)
        lines = []

        for cc, net in by_cc.items():
            if net > 0:
                lines.append({
                    'account': payable_acc,
                    'cost_center': cc,
                    'debit': net,
                    'credit': 0,
                    'description': f'سداد رواتب - {cc or "بدون مركز تكلفة"}',
                })
                total_net += net

        if total_net > 0:
            lines.append({
                'account': payment_account,
                'debit': 0,
                'credit': total_net,
                'description': f'دفع رواتب {period.name} من {payment_account.name}',
            })

        entry = JournalService.create_entry(
            date_val=period.end_date,
            entry_type=JournalEntry.EntryType.PAYMENT,
            description=f'قيد صرف الرواتب - {period.name}',
            lines=lines,
            source_document=period,
            created_by=posted_by,
        )
        period.payment_entry = entry
        period.save(update_fields=['payment_entry'])
        AuditService.log(posted_by, 'Post', period, f'سداد رواتب الفترة - {period.name}')
        return entry

    @staticmethod
    @transaction.atomic
    def post_government_payment(period: PayrollPeriod, payment_account: Account, insurance_amount: Decimal, tax_amount: Decimal, posted_by) -> JournalEntry:
        """
        يُولِّد قيد توريد الاستقطاعات بمبالغ يحددها المستخدم:
          مدين: تأمينات اجتماعية مستحقة (2133)
          مدين: مصلحة الضرائب - كسب عمل (2125)
          دائن: البنك / الخزينة
        """
        ins_acc = _get_or_create_account('2133', 'تأمينات اجتماعية مستحقة', '213', AccountType.LIABILITY)
        tax_acc = _get_or_create_account('2125', 'مصلحة الضرائب - كسب عمل', '212', AccountType.LIABILITY)
        
        lines = []
        if insurance_amount > 0:
            lines.append({
                'account': ins_acc,
                'debit': insurance_amount,
                'credit': 0,
                'description': f'توريد تأمينات اجتماعية - {period.name if period else "سداد عام"}'
            })
        
        if tax_amount > 0:
            lines.append({
                'account': tax_acc,
                'debit': tax_amount,
                'credit': 0,
                'description': f'توريد ضريبة كسب عمل - {period.name if period else "سداد عام"}'
            })
            
        total_payment = insurance_amount + tax_amount
        
        if total_payment > 0:
            lines.append({
                'account': payment_account,
                'debit': 0,
                'credit': total_payment,
                'description': f'سداد استقطاعات للجهات الحكومية - {period.name if period else ""}'
            })

            entry = JournalService.create_entry(
                date_val=period.end_date if period else date.today(),
                entry_type=JournalEntry.EntryType.PAYMENT,
                description=f'قيد توريد استقطاعات - {period.name if period else "سداد مانيوال"}',
                lines=lines,
                source_document=period,
                created_by=posted_by,
            )
            
            if period:
                period.gov_payment_entry = entry
                period.save(update_fields=['gov_payment_entry'])
                
            AuditService.log(posted_by, 'Post', period, f'توريد استقطاعات مانيوال - {period.name if period else ""}')
            return entry
        
        raise ValueError("يجب إدخال مبالغ أكبر من الصفر للتوريد.")

    # ─────────────────────────────────────────────────────────────────────────
    # توليد القسائم المبدئية
    # ─────────────────────────────────────────────────────────────────────────
    @staticmethod
    @transaction.atomic
    def generate_payslips_for_period(period: PayrollPeriod):
        from .models import Employee
        if period.status != PayrollPeriod.Status.DRAFT:
            raise ValueError("يمكن توليد القسائم فقط للفترات في حالة المسودة.")

        active_employees = Employee.objects.filter(status=Employee.Status.ACTIVE)
        created_count = 0

        for emp in active_employees:
            if Payslip.objects.filter(period=period, employee=emp).exists():
                continue

            basic = emp.basic_salary or Decimal(0)

            # ── ✅ Bug #5 Fix: حساب السلف بشكل صحيح لكل سلفة على حدة ──
            loan_deduction = Decimal(0)
            active_loans = emp.loans.filter(status='approved', start_month__lte=period.start_date)
            
            loans_to_deduct = []
            for loan in active_loans:
                # عدد الأشهر التي خُصم فيها قسط هذه السلفة تحديداً (عبر الموديل الجديد)
                deducted_count = loan.installments.count()

                if deducted_count < loan.installments_count:
                    loan_deduction += loan.monthly_installment
                    loans_to_deduct.append(loan)
                    
                    # إذا كان هذا هو القسط الأخير، نحول الحالة لـ PAID
                    if deducted_count + 1 == loan.installments_count:
                        loan.status = 'paid'
                        loan.save(update_fields=['status'])


            # البدلات تُضاف يدوياً لاحقاً عبر PayslipUpdateView
            total_allowances = Decimal(0)
            other_additions  = Decimal(0)
            other_deductions = Decimal(0)

            # ── التأمينات ──
            insurance = Decimal(0)
            if emp.has_social_insurance and basic and emp.social_insurance_rate:
                ins_rate  = emp.social_insurance_rate / Decimal('100')
                insurance = (basic * ins_rate).quantize(Decimal('0.01'))

            # ── ضريبة كسب العمل (الشرائح المصرية أو النسبة الثابتة) ──
            tax = Decimal(0)
            if emp.has_taxes and basic:
                taxable = max(Decimal('0'), basic - insurance)
                if emp.income_tax_rate and emp.income_tax_rate > 0:
                    # الوضع القديم: نسبة ثابتة
                    tax_rate = emp.income_tax_rate / Decimal('100')
                    tax = (taxable * tax_rate).quantize(Decimal('0.01'))
                else:
                    # الوضع الجديد: الشرائح الضريبية المصرية
                    tax = PayrollService._calculate_income_tax_brackets(taxable)

            # ✅ Bug #1 Fix: الصافي يشمل البدلات والإضافات ليتوازن قيد post_payroll
            net = basic + total_allowances + other_additions - insurance - tax - loan_deduction - other_deductions

            slip = Payslip.objects.create(
                period=period,
                employee=emp,
                basic_salary=basic,
                total_allowances=total_allowances,
                other_additions=other_additions,
                total_deductions=loan_deduction,
                other_deductions=other_deductions,
                social_insurance=insurance,
                income_tax=tax,
                net_salary=net,
            )

            # إنشاء سجلات الأقساط المخصومة فعلياً
            from .models import LoanInstallment
            for loan in loans_to_deduct:
                    LoanInstallment.objects.create(
                        loan=loan,
                        payslip=slip,
                        amount=loan.monthly_installment,
                        month=period.start_date
                    )
            created_count += 1

        return created_count


class EOSService:
    @staticmethod
    @transaction.atomic
    def process_settlement(eos_record, posted_by) -> JournalEntry:
        """
        يرحل تسوية نهاية الخدمة محاسبياً.
        ✅ Fix #7: يسوّي رصيد السلف المتبقية من حساب 1143.

        مدين: مصروف تعويضات ترك الخدمة (5215)   — total_settlement
        دائن: سلف الموظفين والقروض (1143)         — outstanding_loan_balance (إن وجد)
        دائن: رواتب وأجور مستحقة (2133)           — total_settlement + outstanding_loan_balance
        """
        if eos_record.is_processed:
            raise ValueError("هذه التسوية مرحلة بالفعل.")

        # ── الحسابات ──────────────────────────────────────────────────────
        eos_expense_acc = _get_or_create_account('5215', 'مصروف تعويضات ومكافآت نهاية الخدمة', '521', AccountType.EXPENSE)
        payable_acc     = _get_or_create_account('2133', 'رواتب وأجور مستحقة',                 '213', AccountType.LIABILITY)
        loan_acc        = _get_or_create_account('1143', 'سلف الموظفين والقروض',               '114', AccountType.ASSET)

        cc = eos_record.employee.department.cost_center if (
            eos_record.employee.department and eos_record.employee.department.cost_center
        ) else None

        # ── حساب رصيد السلف المتبقي ───────────────────────────────────────
        from django.db.models import Sum as DbSum
        from .models import Loan, Payslip as PayslipModel

        approved_loans = Loan.objects.filter(
            employee=eos_record.employee,
            status='approved'
        )
        total_loan_amount = approved_loans.aggregate(total=DbSum('amount'))['total'] or Decimal(0)
        
        # حساب إجمالي ما تم سداده عبر الأقساط الفعلية
        from .models import LoanInstallment
        total_deducted = LoanInstallment.objects.filter(
            loan__employee=eos_record.employee
        ).aggregate(total=DbSum('amount'))['total'] or Decimal(0)
        
        outstanding_loan_balance = max(Decimal(0), total_loan_amount - total_deducted)

        # ── بناء سطور القيد ───────────────────────────────────────────────
        # المصروف الإجمالي = الصافي المطلوب صرفه + السلف التي سيتم استقطاعها من المستحقات
        gross_settlement = eos_record.total_settlement + outstanding_loan_balance
        
        lines = [
            {
                'account': eos_expense_acc,
                'cost_center': cc,
                'debit': gross_settlement,
                'credit': 0,
                'description': f'مصروف نهاية خدمة (إجمالي) - {eos_record.employee}'
            },
        ]

        # إذا توجد سلف متبقية، تُسوَّى من حساب 1143 (أصل ينخفض → دائن)
        if outstanding_loan_balance > 0:
            lines.append({
                'account': loan_acc,
                'cost_center': cc,
                'debit': 0,
                'credit': outstanding_loan_balance,
                'description': f'استقطاع سلف متبقية من مستحقات نهاية الخدمة - {eos_record.employee}'
            })

        # الدائن النهائي: الصافي المستحق للصرف للموظف
        lines.append({
            'account': payable_acc,
            'cost_center': cc,
            'debit': 0,
            'credit': eos_record.total_settlement,
            'description': f'صافي مستحقات نهاية خدمة (للصرف) - {eos_record.employee}'
        })


        entry = JournalService.create_entry(
            date_val=eos_record.termination_date,
            entry_type=JournalEntry.EntryType.MANUAL,
            description=f'قيد تسوية نهاية خدمة - {eos_record.employee}',
            lines=lines,
            source_document=eos_record,
            created_by=posted_by
        )

        # تحديث حالة السلف المسوَّاة إلى PAID
        if outstanding_loan_balance > 0:
            approved_loans.filter(status='approved').update(status='paid')

        eos_record.is_processed = True
        eos_record.save()

        # تحديث حالة الموظف
        eos_record.employee.status = 'terminated'
        eos_record.employee.save()

        AuditService.log(
            posted_by, 'Post', eos_record,
            f'ترحيل تسوية نهاية خدمة - {eos_record.employee} (سلف مسوَّاة: {outstanding_loan_balance})'
        )
        return entry
