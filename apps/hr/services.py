from django.db import transaction
from django.db.models import Sum
from decimal import Decimal
from apps.core.models import JournalEntry, Account, AccountType
from apps.core.services import JournalService
from .models import PayrollPeriod

class PayrollService:
    @staticmethod
    def _get_or_create_account(code, name, parent_code, account_type):
        """Helper to ensure HR specific accounts exist in the Chart of Accounts"""
        parent = Account.objects.filter(code=parent_code).first()
        acc, created = Account.objects.get_or_create(
            code=code,
            defaults={
                'name': name,
                'parent': parent,
                'account_type': account_type,
                'is_leaf': True
            }
        )
        return acc

    @staticmethod
    @transaction.atomic
    def post_payroll(period: PayrollPeriod, posted_by) -> JournalEntry:
        """
        يرحل فترة الرواتب ويقوم بتوليد قيد الاستحقاق (Accrual Journal Entry).
        
        شكل القيد:
        من حـ/ مصروفات الرواتب (إجمالي الرواتب والبدلات)
            إلى مذكورين:
            حـ/ الرواتب والأجور المستحقة (صافي الرواتب)
            حـ/ جاري مصلحة التأمينات الاجتماعية (حصة الموظف المستقطعة)
            حـ/ جاري مصلحة الضرائب - كسب عمل (ضريبة الدخل المستقطعة)
            حـ/ سلف الموظفين (إجمالي الاستقطاعات الأخرى/السلف)
        """
        if period.status == PayrollPeriod.Status.POSTED:
            raise ValueError("هذه الفترة مرحلة بالفعل.")
            
        payslips = period.payslips.all()
        if not payslips.exists():
            raise ValueError("لا يوجد قسائم رواتب في هذه الفترة للترحيل.")

        # حساب المجاميع
        totals = payslips.aggregate(
            gross_salary=Sum('basic_salary') + Sum('total_allowances'),
            net_salary=Sum('net_salary'),
            social_insurance=Sum('social_insurance'),
            income_tax=Sum('income_tax'),
            other_deductions=Sum('total_deductions')
        )
        
        # جلب أو إنشاء الحسابات المطلوبة
        expense_acc = Account.objects.get(code='521')  # مصروفات الرواتب
        payable_acc = PayrollService._get_or_create_account('2133', 'رواتب وأجور مستحقة', '213', AccountType.LIABILITY)
        insurance_acc = PayrollService._get_or_create_account('2124', 'جاري التأمينات الاجتماعية', '212', AccountType.LIABILITY)
        tax_acc = PayrollService._get_or_create_account('2125', 'جاري مصلحة الضرائب - كسب عمل', '212', AccountType.LIABILITY)
        loan_acc = PayrollService._get_or_create_account('1143', 'سلف الموظفين', '114', AccountType.ASSET)
        
        lines = []
        
        # الطرف المدين (المصروفات)
        gross_amount = totals['gross_salary'] or 0
        if gross_amount > 0:
            lines.append({
                'account': expense_acc,
                'debit': gross_amount,
                'credit': 0,
                'description': f'إثبات مصروف الرواتب لفترة {period.name}'
            })

        # الطرف الدائن (الالتزامات والسلف)
        if totals['net_salary'] and totals['net_salary'] > 0:
            lines.append({
                'account': payable_acc,
                'debit': 0,
                'credit': totals['net_salary'],
                'description': f'صافي الرواتب المستحقة لفترة {period.name}'
            })
            
        if totals['social_insurance'] and totals['social_insurance'] > 0:
            lines.append({
                'account': insurance_acc,
                'debit': 0,
                'credit': totals['social_insurance'],
                'description': f'استقطاع تأمينات اجتماعية لفترة {period.name}'
            })
            
        if totals['income_tax'] and totals['income_tax'] > 0:
            lines.append({
                'account': tax_acc,
                'debit': 0,
                'credit': totals['income_tax'],
                'description': f'استقطاع ضريبة كسب عمل لفترة {period.name}'
            })
            
        if totals['other_deductions'] and totals['other_deductions'] > 0:
            # دائن لحساب السلف (يخفض رصيد السلف المفتوحة على الموظفين)
            lines.append({
                'account': loan_acc,
                'debit': 0,
                'credit': totals['other_deductions'],
                'description': f'استرداد سلف واستقطاعات أخرى لفترة {period.name}'
            })

        # إنشاء القيد باستخدام JournalService
        entry = JournalService.create_entry(
            date_val=period.end_date,
            entry_type=JournalEntry.EntryType.GENERAL, # Or create a PAYROLL type in core
            description=f'قيد استحقاق الرواتب - {period.name}',
            lines=lines,
            created_by=posted_by
        )
        
        # ربط القيد بالفترة وتغيير الحالة
        period.journal_entry = entry
        period.status = PayrollPeriod.Status.POSTED
        period.save()
        
        return entry

    @staticmethod
    @transaction.atomic
    def generate_payslips_for_period(period: PayrollPeriod):
        """
        خدمة مساعدة لتوليد قسائم رواتب مسودة (Draft) لكل الموظفين النشطين في الفترة.
        تقوم بجلب الراتب الأساسي، وحساب التأمينات والضرائب مبدئياً.
        """
        from .models import Employee, Payslip
        
        if period.status != PayrollPeriod.Status.DRAFT:
            raise ValueError("يمكن توليد القسائم فقط للفترات في حالة المسودة.")
            
        # الموظفين النشطين فقط
        active_employees = Employee.objects.filter(status=Employee.Status.ACTIVE)
        
        created_count = 0
        for emp in active_employees:
            # إذا لم تكن القسيمة موجودة مسبقاً لهذه الفترة
            if not Payslip.objects.filter(period=period, employee=emp).exists():
                basic = emp.basic_salary
                # حساب افتراضي للتأمينات 11% (حصة الموظف حسب القانون المصري)
                insurance = basic * Decimal('0.11') if basic else 0
                
                # حساب مبسط لضريبة كسب العمل (في الواقع تتطلب شرائح معقدة)
                taxable_amount = basic - insurance # إعفاء التأمينات
                tax = taxable_amount * Decimal('0.10') if taxable_amount > 2000 else 0 # مثال مبسط جداً
                
                net = basic - insurance - tax
                
                Payslip.objects.create(
                    period=period,
                    employee=emp,
                    basic_salary=basic,
                    social_insurance=insurance,
                    income_tax=tax,
                    net_salary=net
                )
                created_count += 1
                
        return created_count
