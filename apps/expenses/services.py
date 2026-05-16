from django.db import transaction
from django.db.models import Sum
from apps.core.models import JournalEntry
from apps.core.services import JournalService
from .models import Expense, Custody, CustodySettlement

class ExpenseService:
    @staticmethod
    @transaction.atomic
    def post_expense(expense: Expense, posted_by) -> JournalEntry:
        # Lock the record to prevent concurrent posting
        expense = Expense.objects.select_for_update().get(pk=expense.pk)
        
        if expense.status == Expense.Status.POSTED:
            raise ValueError("هذا المصروف مرحل بالفعل")
        if expense.status != Expense.Status.APPROVED:
            raise ValueError("يجب اعتماد المصروف قبل الترحيل")
            
        # ✅ Fix: Validate payment source
        if expense.payment_method == 'cash' and not expense.cash_box:
            raise ValueError("يجب تحديد الخزنة للدفع النقدي")
        if expense.payment_method == 'bank' and not expense.bank_account:
            raise ValueError("يجب تحديد الحساب البنكي للدفع عبر البنك")
        if expense.payment_method == 'custody' and not expense.custody:
            raise ValueError("يجب تحديد العهدة")

        lines = []
        
        # Taxes processing
        # Professional tax processing: VAT on (Subtotal + Table Tax)
        tax_entries = []
        capitalized_tax = 0  # Non-refundable (Table, Stamp, Customs)
        
        taxes_to_process = []
        if expense.tax_type: taxes_to_process.append({'type': expense.tax_type, 'rate': expense.tax_percent})
        if expense.tax_type2: taxes_to_process.append({'type': expense.tax_type2, 'rate': expense.tax_percent2})
        
        # First pass: calculate Table Tax (Capitalized)
        table_tax_val = 0
        for tx_info in taxes_to_process:
            tx = tx_info['type']
            if tx.category == 'table':
                rate = tx_info['rate'] if tx_info['rate'] is not None else tx.rate
                table_tax_val += expense.subtotal * (rate / 100)
        
        # Second pass: calculate all taxes
        for tx_info in taxes_to_process:
            tx = tx_info['type']
            rate = tx_info['rate'] if tx_info['rate'] is not None else tx.rate
            
            if tx.category == 'vat':
                # VAT is on (Subtotal + Table Tax)
                val = (expense.subtotal + table_tax_val) * (rate / 100)
            elif tx.category in ['table', 'stamp', 'customs']:
                # Capitalize
                val = expense.subtotal * (rate / 100)
                capitalized_tax += val
                continue
            else:
                # Others (WHT, etc.) are on Subtotal
                val = expense.subtotal * (rate / 100)
            
            if val == 0: continue
            
            # Routing: WHT/Salary/Insurance in expenses are Credits (Deductions from payee)
            # VAT/Others are Debits (Refundable assets)
            is_credit = (tx.category in ['wht', 'salary', 'insurance'])
            tax_entries.append({
                'account': tx.account,
                'debit': 0 if is_credit else val,
                'credit': val if is_credit else 0,
                'description': f'ضريبة {tx.name} - مصروف {expense.number}'
            })

        # 1. Main Expense Line (Base + Capitalized Taxes)
        lines.append({
            'account': expense.category.account,
            'debit': expense.subtotal + capitalized_tax,
            'credit': 0,
            'description': f'مصروف: {expense.description}',
            'cost_center': expense.cost_center,
        })
        
        # 2. Add Separate Tax Lines
        lines.extend(tax_entries)
        
        # 3. Credit Payment Source (Amount Paid = subtotal + Additions - Deductions)
        # Note: expense.amount should already be the net paid amount from the view
        if expense.payment_method == 'cash':
            account = expense.cash_box.account
        elif expense.payment_method == 'bank':
            account = expense.bank_account.account
        else: # custody
            account = expense.custody.account
            
        lines.append({
            'account': account,
            'debit': 0,
            'credit': expense.amount, # Net Paid
            'description': f'سداد مصروف {expense.number}'
        })
        
        entry = JournalService.create_entry(
            date_val=expense.date,
            entry_type=JournalEntry.EntryType.EXPENSE,
            description=f'قيد مصروف رقم {expense.number}',
            lines=lines,
            source_document=expense,
            created_by=posted_by,
        )
        
        expense.journal_entry = entry
        expense.status = Expense.Status.POSTED
        expense.save()
        return entry

    @staticmethod
    @transaction.atomic
    def reverse_expense(expense: Expense, reversed_by) -> JournalEntry:
        """
        عكس مصروف (إنشاء قيد عكسي)
        """
        if expense.status != Expense.Status.POSTED:
            raise ValueError("يمكن عكس المصاريف المرحلة فقط")
        
        if expense.journal_entry.is_reversed:
            raise ValueError("هذا المصروف تم عكسه مسبقاً")

        entry = JournalService.reverse_entry(
            entry=expense.journal_entry,
            date_val=expense.date, # Or current date
            created_by=reversed_by
        )
        
        expense.status = Expense.Status.REVERSED # ✅ Fixed status
        expense.save()
        
        from apps.core.services import AuditService
        AuditService.log(reversed_by, 'Reverse', expense, f'عكس مصروف رقم {expense.number}')
        
        return entry

class CustodyService:
    @staticmethod
    @transaction.atomic
    def issue_custody(custody: Custody, created_by) -> JournalEntry:
        """
        DR  Employee Advance Account          → custody.amount
        CR  Cash Box                          → custody.amount
        """
        lines = [
            {'account': custody.account, 'debit': custody.amount, 'credit': 0, 'description': f'إصدار عهدة {custody.number}'},
            {'account': custody.cash_box.account, 'debit': 0, 'credit': custody.amount, 'description': f'صرف عهدة {custody.number}'},
        ]
        
        entry = JournalService.create_entry(
            date_val=custody.date,
            entry_type=JournalEntry.EntryType.CUSTODY,
            description=f'قيد عهدة رقم {custody.number}',
            lines=lines,
            source_document=custody,
            created_by=created_by,
        )
        custody.journal_entry = entry
        custody.save()
        return entry

    @staticmethod
    @transaction.atomic
    def settle_custody(settlement: CustodySettlement, created_by) -> JournalEntry:
        # Lock the settlement and custody to prevent concurrency issues
        settlement = CustodySettlement.objects.select_for_update().get(pk=settlement.pk)
        custody = settlement.custody
        custody = Custody.objects.select_for_update().get(pk=custody.pk)
        
        if settlement.is_posted:
            raise ValueError("هذه التسوية مرحلة بالفعل")
        # ✅ Fix: Over-settlement validation
        posted_expenses = custody.expense_set.filter(status='posted', settlement__isnull=True)
        current_expenses_total = posted_expenses.aggregate(t=Sum('amount'))['t'] or 0
        
        # Calculate what has already been settled
        already_settled = custody.settled_amount # Sum of previous settlements
        remaining_to_settle = custody.amount - already_settled
        
        total_this_settlement = current_expenses_total + settlement.returned_amount
        
        if total_this_settlement > remaining_to_settle:
            raise ValueError(
                f"خطأ في التسوية: المبلغ المطلوب تسويته ({total_this_settlement}) "
                f"أكبر من الرصيد المتبقي للعهدة ({remaining_to_settle})"
            )
            
        lines = []
        entry = None
        
        # 1. Calculate Expenses - Only those already posted (they already have G/L entries)
        expenses = settlement.custody.expense_set.filter(status='posted', settlement__isnull=True)
        total_expenses = 0
        for exp in expenses:
            total_expenses += exp.amount
            exp.settlement = settlement  # Mark as settled
            exp.save()
            
        # 2. Handle Cash Refund (G/L Entry needed for this part)
        if settlement.returned_amount > 0:
            lines.append({
                'account': settlement.cash_box.account,
                'debit': settlement.returned_amount,
                'credit': 0,
                'description': f'رد متبقي عهدة {settlement.custody.number}'
            })
            
            lines.append({
                'account': settlement.custody.account,
                'debit': 0,
                'credit': settlement.returned_amount,
                'description': f'تسوية رد متبقي عهدة {settlement.custody.number}'
            })

            entry = JournalService.create_entry(
                date_val=settlement.date,
                entry_type=JournalEntry.EntryType.CUSTODY,
                description=f'تسوية رد نقدية عهدة رقم {settlement.custody.number}',
                lines=lines,
                source_document=settlement,
                created_by=created_by,
            )
            settlement.journal_entry = entry
            
        settlement.expenses_amount = total_expenses
        settlement.is_posted = True
        settlement.save()
        
        # 4. Update Custody Status
        custody = settlement.custody
        # Total settled is the sum of ALL settlements' returned_amount + sum of all expenses linked to any settlement
        total_returned = custody.settlements.filter(is_posted=True).aggregate(t=Sum('returned_amount'))['t'] or 0
        total_expenses_all = custody.expense_set.filter(settlement__isnull=False).aggregate(t=Sum('amount'))['t'] or 0
        
        custody.settled_amount = total_returned + total_expenses_all
        
        if custody.settled_amount >= custody.amount:
            custody.status = Custody.Status.SETTLED
        else:
            custody.status = Custody.Status.PARTIALLY_SETTLED
            
        custody.save()
        return entry
