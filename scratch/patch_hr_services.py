import re

def main():
    file_path = 'apps/hr/services.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    # 1. Tax Calculation (annual conversion)
    old_tax_calc = """    @staticmethod
    def _calculate_income_tax_brackets(monthly_taxable: Decimal) -> Decimal:
        if monthly_taxable <= 0:
            return Decimal('0')

        annual_tax = Decimal('0')
        prev_limit = Decimal('0')

        for limit, rate in PayrollService.TAX_BRACKETS:
            bracket_size = limit - prev_limit
            if monthly_taxable <= limit:
                taxable_in_bracket = min(monthly_taxable - prev_limit, bracket_size)
                annual_tax += taxable_in_bracket * rate
                break
            else:
                annual_tax += bracket_size * rate
                prev_limit = limit

        monthly_tax = annual_tax / 12
        return monthly_tax.quantize(Decimal('0.01'))"""
    new_tax_calc = """    @staticmethod
    def _calculate_income_tax_brackets(monthly_taxable: Decimal) -> Decimal:
        if monthly_taxable <= 0:
            return Decimal('0')

        annual_taxable = monthly_taxable * 12
        annual_tax = Decimal('0')
        prev_limit = Decimal('0')

        for limit, rate in PayrollService.TAX_BRACKETS:
            bracket_size = limit - prev_limit
            if annual_taxable <= limit:
                taxable_in_bracket = min(annual_taxable - prev_limit, bracket_size)
                annual_tax += taxable_in_bracket * rate
                break
            else:
                annual_tax += bracket_size * rate
                prev_limit = limit

        monthly_tax = annual_tax / 12
        return monthly_tax.quantize(Decimal('0.01'))"""
    content = content.replace(old_tax_calc, new_tax_calc)

    # 2. post_payment_entry and post_insurance_entry status validation
    old_post_payment = """    def post_payment_entry(period: PayrollPeriod, cash_box, posted_by) -> JournalEntry:
        period = PayrollPeriod.objects.select_for_update().get(pk=period.pk)"""
    new_post_payment = """    def post_payment_entry(period: PayrollPeriod, cash_box, posted_by) -> JournalEntry:
        period = PayrollPeriod.objects.select_for_update().get(pk=period.pk)
        if period.status != PayrollPeriod.Status.POSTED:
            raise ValueError("لا يمكن السداد إلا لفترة رواتب مُرحلة.")"""
    content = content.replace(old_post_payment, new_post_payment)

    old_post_ins = """    def post_insurance_entry(period: PayrollPeriod, posted_by) -> JournalEntry:
        period = PayrollPeriod.objects.select_for_update().get(pk=period.pk)"""
    new_post_ins = """    def post_insurance_entry(period: PayrollPeriod, posted_by) -> JournalEntry:
        period = PayrollPeriod.objects.select_for_update().get(pk=period.pk)
        if period.status != PayrollPeriod.Status.POSTED:
            raise ValueError("لا يمكن ترحيل التأمينات إلا لفترة رواتب مُرحلة.")"""
    content = content.replace(old_post_ins, new_post_ins)

    # 3. generate_payslips_for_period loan calculation capping & premature paid status
    old_gen_payslip = """                    # Deduct the monthly installment
                    loan_deduction += loan.monthly_installment
                    
                    # Create the installment record tracking this month
                    LoanInstallment.objects.create(
                        loan=loan,
                        amount=loan.monthly_installment,
                        date=period.end_date,
                        payroll_period=period
                    )
                    
                    # إذا كان هذا هو القسط الأخير، نحول الحالة لـ PAID
                    if deducted_count + 1 == loan.installments_count:
                        loan.status = 'paid'
                        loan.save(update_fields=['status'])

            net = basic + total_allowances + other_additions - insurance - tax - other_deductions - loan_deduction

            Payslip.objects.create("""
    new_gen_payslip = """                    # Deduct the monthly installment
                    loan_deduction += loan.monthly_installment
                    
                    # Create the installment record tracking this month
                    LoanInstallment.objects.create(
                        loan=loan,
                        amount=loan.monthly_installment,
                        date=period.end_date,
                        payroll_period=period
                    )

            net = basic + total_allowances + other_additions - insurance - tax - other_deductions
            actual_loan_deduction = min(loan_deduction, net) if net > 0 else Decimal(0)
            net -= actual_loan_deduction

            Payslip.objects.create("""
    content = content.replace(old_gen_payslip, new_gen_payslip)
    # We also need to change `loan_deduction` to `actual_loan_deduction` inside `Payslip.objects.create(`
    content = content.replace("total_deductions=loan_deduction,", "total_deductions=actual_loan_deduction,")

    # 4. EOS Settlements logic
    old_eos_loan = """        # ── حساب رصيد السلف المتبقي ───────────────────────────────────────
        approved_loans = Loan.objects.filter(
            employee=eos_record.employee,
            status='approved'
        )
        total_loan_amount = approved_loans.aggregate(total=Sum('amount'))['total'] or Decimal(0)
        total_deducted = LoanInstallment.objects.filter(
            loan__employee=eos_record.employee
        ).aggregate(total=Sum('amount'))['total'] or Decimal(0)
        
        outstanding_loan_balance = max(Decimal(0), total_loan_amount - total_deducted)

        # ── بناء سطور القيد ───────────────────────────────────────────────
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

        if outstanding_loan_balance > 0:
            lines.append({
                'account': loan_acc,
                'cost_center': cc,
                'debit': 0,
                'credit': outstanding_loan_balance,
                'description': f'استقطاع سلف متبقية من مستحقات نهاية الخدمة - {eos_record.employee}'
            })

        if eos_record.total_settlement > 0:
            lines.append({
                'account': payable_acc,
                'cost_center': cc,
                'debit': 0,
                'credit': eos_record.total_settlement,
                'description': f'صافي مستحقات نهاية خدمة (للصرف) - {eos_record.employee}'
            })"""
            
    new_eos_loan = """        # ── حساب رصيد السلف المتبقي ───────────────────────────────────────
        approved_loans = Loan.objects.filter(
            employee=eos_record.employee,
            status='approved'
        )
        total_loan_amount = approved_loans.aggregate(total=Sum('amount'))['total'] or Decimal(0)
        total_deducted = LoanInstallment.objects.filter(
            loan__in=approved_loans
        ).aggregate(total=Sum('amount'))['total'] or Decimal(0)
        
        outstanding_loan_balance = max(Decimal(0), total_loan_amount - total_deducted)

        # ── بناء سطور القيد ───────────────────────────────────────────────
        gross_settlement = eos_record.total_settlement
        
        net_payable = max(Decimal(0), gross_settlement - outstanding_loan_balance)
        recovered_loan = min(outstanding_loan_balance, gross_settlement)
        
        lines = [
            {
                'account': eos_expense_acc,
                'cost_center': cc,
                'debit': gross_settlement,
                'credit': 0,
                'description': f'مصروف نهاية خدمة (إجمالي) - {eos_record.employee}'
            },
        ]

        if recovered_loan > 0:
            lines.append({
                'account': loan_acc,
                'cost_center': cc,
                'debit': 0,
                'credit': recovered_loan,
                'description': f'استقطاع سلف متبقية من مستحقات نهاية الخدمة - {eos_record.employee}'
            })

        if net_payable > 0:
            lines.append({
                'account': payable_acc,
                'cost_center': cc,
                'debit': 0,
                'credit': net_payable,
                'description': f'صافي مستحقات نهاية خدمة (للصرف) - {eos_record.employee}'
            })"""
    content = content.replace(old_eos_loan, new_eos_loan)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Services patched.")

if __name__ == '__main__':
    main()
