from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from apps.core.models import JournalEntry
from apps.core.services import JournalService, AuditService
from apps.core.tax_utils import calculate_line_taxes
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
        
        # Taxes processing using unified engine
        tax_entries = []
        
        subtotal = Decimal(str(expense.subtotal or '0'))
        res = calculate_line_taxes(
            subtotal,
            expense.tax_type,
            expense.tax_percent,
            expense.tax_type2,
            expense.tax_percent2,
            is_purchase_or_expense=True
        )
        
        capitalized_tax = res['capitalized_amount']
        
        for tx_type, tx_val in [(expense.tax_type, res['tax1_value']), (expense.tax_type2, res['tax2_value'])]:
            if tx_type and tx_val > 0:
                if tx_type.category not in ['table', 'stamp', 'customs', 'other']:
                    is_credit = (tx_type.category in ['wht', 'salary', 'insurance'])
                    tax_entries.append({
                        'account': tx_type.account,
                        'debit': 0 if is_credit else tx_val,
                        'credit': tx_val if is_credit else 0,
                        'description': f'ضريبة {tx_type.name} - مصروف {expense.number}'
                    })

        # 1. Main Expense Line (Base + Capitalized Taxes)
        lines.append({
            'account': expense.category.account,
            'debit': subtotal + capitalized_tax,
            'credit': 0,
            'description': f'مصروف: {expense.description}',
            'cost_center': expense.cost_center,
        })
        
        # 2. Add Separate Tax Lines
        lines.extend(tax_entries)
        
        # 3. Credit Payment Source (Amount Paid = subtotal + Additions - Deductions)
        net_paid = (subtotal + capitalized_tax + 
                    sum(t['debit'] for t in tax_entries) - 
                    sum(t['credit'] for t in tax_entries))

        if expense.amount != net_paid:
            raise ValueError(f"قيمة السداد ({expense.amount}) لا تتطابق مع صافي المصروف بعد الضرائب ({net_paid})")
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
        expense = Expense.objects.select_for_update().get(pk=expense.pk)
        if expense.status != Expense.Status.POSTED:
            raise ValueError("يمكن عكس المصاريف المرحلة فقط")
        
        if expense.journal_entry.is_reversed:
            raise ValueError("هذا المصروف تم عكسه مسبقاً")

        entry = JournalService.reverse_entry(
            entry=expense.journal_entry,
            date_val=expense.date, # Or current date
            created_by=reversed_by
        )
        
        expense.status = Expense.Status.REVERSED
        expense.save()
        
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
        posted_expenses = custody.expense_set.filter(status=Expense.Status.POSTED, settlement__isnull=True)
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
        expenses = settlement.custody.expense_set.filter(status=Expense.Status.POSTED, settlement__isnull=True)
        total_expenses = expenses.aggregate(t=Sum('amount'))['t'] or 0
        expenses.update(settlement=settlement)
        
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
        total_expenses_all = custody.expense_set.filter(settlement__is_posted=True).aggregate(t=Sum('amount'))['t'] or 0
        
        custody.settled_amount = total_returned + total_expenses_all
        
        if custody.settled_amount >= custody.amount:
            custody.status = Custody.Status.SETTLED
        else:
            custody.status = Custody.Status.PARTIALLY_SETTLED
            
        custody.save()
        return entry
