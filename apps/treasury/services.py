from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.core.models import Account, JournalEntry
from apps.core.services import JournalService
from .models import CashBox, BankAccount, CashTransfer

class TreasuryService:

    CASHBOX_PARENT_CODE = getattr(settings, 'CASHBOX_PARENT_ACCOUNT', '1111')
    BANK_PARENT_CODE = getattr(settings, 'BANK_PARENT_ACCOUNT', '1112')

    @staticmethod
    @transaction.atomic
    def create_cash_box(validated_data: dict) -> CashBox:
        parent = Account.objects.select_for_update().get(code=TreasuryService.CASHBOX_PARENT_CODE)
        next_seq = Account.objects.filter(parent=parent).count() + 1
        account_code = f'{parent.code}{next_seq:02d}'

        account = Account.objects.create(
            code=account_code,
            name=validated_data['name'],
            account_type=parent.account_type,
            parent=parent,
            is_leaf=True,
            currency=validated_data.get('currency', 'EGP'),
            initial_balance=validated_data.get('initial_balance', 0),
            initial_balance_type=validated_data.get('initial_balance_type', 'debit'),
        )
        data = {k: v for k, v in validated_data.items() if k not in ('code', 'account', 'initial_balance', 'initial_balance_type')}
        return CashBox.objects.create(account=account, code=validated_data.get('code'), **data)

    @staticmethod
    @transaction.atomic
    def create_bank_account(validated_data: dict) -> BankAccount:
        parent = Account.objects.select_for_update().get(code=TreasuryService.BANK_PARENT_CODE)
        next_seq = Account.objects.filter(parent=parent).count() + 1
        account_code = f'{parent.code}{next_seq:02d}'

        account = Account.objects.create(
            code=account_code,
            name=f'{validated_data["bank_name"]} — {validated_data["name"]}',
            account_type=parent.account_type,
            parent=parent,
            is_leaf=True,
            currency=validated_data.get('currency', 'EGP'),
            initial_balance=validated_data.get('initial_balance', 0),
            initial_balance_type=validated_data.get('initial_balance_type', 'debit'),
        )
        data = {k: v for k, v in validated_data.items() if k not in ('code', 'account', 'initial_balance', 'initial_balance_type')}
        return BankAccount.objects.create(account=account, code=validated_data.get('code'), **data)

    @staticmethod
    @transaction.atomic
    def process_transfer(transfer, posted_by) -> JournalEntry:
        """
        Creates a Journal Entry:
        DR Destination Account (Cash or Bank)
        CR Source Account (Cash or Bank)
        """
        transfer.full_clean()
        if transfer.journal_entry:
            raise ValueError("هذا التحويل تم ترحيله بالفعل")
            
        source_account = (transfer.from_cash_box.account if transfer.from_cash_box 
                          else transfer.from_bank.account)
        dest_account = (transfer.to_cash_box.account if transfer.to_cash_box 
                        else transfer.to_bank.account)
        
        lines = [
            {
                'account': dest_account,
                'debit': transfer.amount,
                'credit': 0,
                'description': f'تحويل وارد - {transfer.description}'
            },
            {
                'account': source_account,
                'debit': 0,
                'credit': transfer.amount,
                'description': f'تحويل صادر - {transfer.description}'
            }
        ]
        
        entry = JournalService.create_entry(
            date_val=transfer.date,
            entry_type=JournalEntry.EntryType.BANK,
            description=f'تحويل نقدية رقم {transfer.number}',
            lines=lines,
            source_document=transfer,
            created_by=posted_by
        )
        
        transfer.journal_entry = entry
        transfer.save()

        from apps.core.services import AuditService
        AuditService.log(posted_by, 'Post', transfer, f'ترحيل تحويل نقدية رقم {transfer.number}')

        return entry
    @staticmethod
    @transaction.atomic
    def reverse_transfer(transfer, reversed_by) -> JournalEntry:
        """
        عكس عملية تحويل (إنشاء قيد عكسي)
        """
        if not transfer.journal_entry:
            raise ValueError("هذا التحويل لم يتم ترحيله بعد")
        
        if transfer.journal_entry.is_reversed:
            raise ValueError("هذا التحويل تم عكسه مسبقاً")

        entry = JournalService.reverse_entry(
            entry=transfer.journal_entry,
            date_val=timezone.now().date(),
            created_by=reversed_by
        )
        
        from apps.core.services import AuditService
        AuditService.log(reversed_by, 'Reverse', transfer, f'عكس تحويل نقدية رقم {transfer.number}')
        
        return entry

    @staticmethod
    @transaction.atomic
    def process_bank_transaction(transaction_obj: BankTransaction, posted_by) -> JournalEntry:
        """
        Handles accounting for bank transactions (Charges, Interest, etc.)
        """
        if transaction_obj.journal_entry:
            raise ValueError("هذه الحركة مرحلة بالفعل")

        lines = []
        bank_acc = transaction_obj.bank_account.account
        
        # Determine accounting lines based on type
        if transaction_obj.transaction_type == BankTransaction.TransactionType.BANK_CHARGE:
            # DR Bank Charges (Expense) | CR Bank Account (Asset)
            charge_acc = Account.objects.get(code=getattr(settings, 'BANK_CHARGES_ACCOUNT', '5161'))
            lines.append({'account': charge_acc, 'debit': transaction_obj.amount, 'credit': 0, 'description': transaction_obj.description})
            lines.append({'account': bank_acc, 'debit': 0, 'credit': transaction_obj.amount, 'description': f'عمولة بنكية - {transaction_obj.number}'})
        
        elif transaction_obj.transaction_type == BankTransaction.TransactionType.INTEREST:
            # DR Bank Account (Asset) | CR Interest Revenue (Revenue)
            interest_acc = Account.objects.get(code=getattr(settings, 'INTEREST_REVENUE_ACCOUNT', '4141'))
            lines.append({'account': bank_acc, 'debit': transaction_obj.amount, 'credit': 0, 'description': f'فوائد بنكية - {transaction_obj.number}'})
            lines.append({'account': interest_acc, 'debit': 0, 'credit': transaction_obj.amount, 'description': transaction_obj.description})
        
        elif transaction_obj.transaction_type in [BankTransaction.TransactionType.DEPOSIT, BankTransaction.TransactionType.WITHDRAWAL]:
            # These are usually manual or part of a transfer. If manual, they need an offset account.
            # For simplicity, we assume these are already handled or need a suspense account.
            raise ValueError("الإيداع والسحب النقدي يجب أن يتم عبر نظام التحويلات أو المقبوضات/المدفوعات")
        
        if not lines:
            return None

        entry = JournalService.create_entry(
            date_val=transaction_obj.date,
            entry_type=JournalEntry.EntryType.BANK,
            description=f'حركة بنكية رقم {transaction_obj.number}',
            lines=lines,
            source_document=transaction_obj,
            created_by=posted_by
        )
        
        transaction_obj.journal_entry = entry
        transaction_obj.save()
        return entry
