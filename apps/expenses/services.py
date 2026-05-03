from django.db import transaction
from django.db.models import Sum
from apps.core.models import JournalEntry
from apps.core.services import JournalService
from .models import Expense, Custody, CustodySettlement

class ExpenseService:
    @staticmethod
    @transaction.atomic
    def post_expense(expense: Expense, posted_by) -> JournalEntry:
        """
        Expense Journal Entry:
        DR  Expense Account (from category)    → expense.amount
        CR  Cash/Bank/Custody Account           → expense.amount
        """
        if expense.status == Expense.Status.POSTED:
            raise ValueError("هذا المصروف مرحل بالفعل")
        if expense.status != Expense.Status.APPROVED:
            raise ValueError("يجب اعتماد المصروف قبل الترحيل")
        lines = []
        
        # Taxes processing
        tax_entries = []
        capitalized_tax = 0  # Non-refundable (Table, Stamp, Customs)
        separate_tax_debit = 0 # Refundable (VAT)
        separate_tax_credit = 0 # Deducted (WHT)
        
        def process_tax(t_type, t_percent):
            nonlocal capitalized_tax, separate_tax_debit, separate_tax_credit
            if not t_type: return
            rate = t_percent if t_percent else t_type.rate
            tax_val = expense.subtotal * (rate / 100)
            
            if t_type.category in ['table', 'stamp', 'customs']:
                # Rule 3: Non-refundable -> Capitalize on expense
                capitalized_tax += tax_val
            elif t_type.category in ['wht', 'salary', 'insurance']:
                # Rule 1: Deducted -> Credit tax liability, Expense stays at Gross
                tax_entries.append({
                    'account': t_type.account,
                    'debit': 0,
                    'credit': tax_val,
                    'description': f'استقطاع {t_type.name} - مصروف {expense.number}'
                })
            else: # VAT / Others (Refundable)
                # Rule 2: Refundable -> Debit tax asset, Expense stays at Net
                tax_entries.append({
                    'account': t_type.account,
                    'debit': tax_val,
                    'credit': 0,
                    'description': f'ضريبة {t_type.name} - مصروف {expense.number}'
                })

        process_tax(expense.tax_type, expense.tax_percent)
        process_tax(expense.tax_type2, expense.tax_percent2)

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
        
        expense.status = 'rejected' # Or add a 'cancelled' status if preferred
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
        """
        Journal Entry for Custody Settlement:
        DR  Expense Accounts (for each expense)   → expense.amount
        DR  Cash Box (if refund)                  → settlement.returned_amount
        """
        if settlement.is_posted:
            raise ValueError("هذه التسوية مرحلة بالفعل")
            
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
