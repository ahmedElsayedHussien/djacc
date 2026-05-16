from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.core.models import Account, JournalEntry
from apps.core.services import JournalService
from .models import CashBox, BankAccount, CashTransfer, BankTransaction, BankReconciliation

class TreasuryService:

    CASHBOX_PARENT_CODE = getattr(settings, 'CASHBOX_PARENT_ACCOUNT', '1111')
    BANK_PARENT_CODE = getattr(settings, 'BANK_PARENT_ACCOUNT', '1112')

    @staticmethod
    @transaction.atomic
    def create_cash_box(validated_data: dict) -> CashBox:
        parent = Account.objects.select_for_update().get(code=TreasuryService.CASHBOX_PARENT_CODE)
        # ✅ Fix: Use max code instead of count() to avoid duplicates if a middle account is deleted
        last_account = Account.objects.filter(parent=parent).order_by('-code').first()
        if last_account:
            try:
                # Extract sequence from code (e.g., 111105 -> 05)
                last_seq = int(last_account.code[len(parent.code):])
                next_seq = last_seq + 1
            except (ValueError, IndexError):
                next_seq = Account.objects.filter(parent=parent).count() + 1
        else:
            next_seq = 1
            
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
        # ✅ Fix: Use max code instead of count()
        last_account = Account.objects.filter(parent=parent).order_by('-code').first()
        if last_account:
            try:
                last_seq = int(last_account.code[len(parent.code):])
                next_seq = last_seq + 1
            except (ValueError, IndexError):
                next_seq = Account.objects.filter(parent=parent).count() + 1
        else:
            next_seq = 1

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
    def update_cash_box(cash_box: CashBox, validated_data: dict) -> CashBox:
        # Lock the cash box and its linked account
        cash_box = CashBox.objects.select_for_update().get(pk=cash_box.pk)
        cash_box.account = Account.objects.select_for_update().get(pk=cash_box.account.pk)
        
        update_account = False
        if 'name' in validated_data and validated_data['name'] != cash_box.name:
            cash_box.account.name = validated_data['name']
            update_account = True
        
        if 'initial_balance' in validated_data:
            cash_box.account.initial_balance = validated_data['initial_balance'] or 0
            update_account = True
            
        if 'initial_balance_type' in validated_data:
            cash_box.account.initial_balance_type = validated_data['initial_balance_type']
            update_account = True
            
        if update_account:
            cash_box.account.save(update_fields=['name', 'initial_balance', 'initial_balance_type'])

        for field, value in validated_data.items():
            if field not in ('initial_balance', 'initial_balance_type'):
                setattr(cash_box, field, value)
        cash_box.save()
        return cash_box

    @staticmethod
    @transaction.atomic
    def update_bank_account(bank_account: BankAccount, validated_data: dict) -> BankAccount:
        # Lock the bank account and its linked account
        bank_account = BankAccount.objects.select_for_update().get(pk=bank_account.pk)
        bank_account.account = Account.objects.select_for_update().get(pk=bank_account.account.pk)
        
        update_account = False
        full_name = f'{validated_data.get("bank_name", bank_account.bank_name)} — {validated_data.get("name", bank_account.name)}'
        if full_name != bank_account.account.name:
            bank_account.account.name = full_name
            update_account = True
            
        if 'initial_balance' in validated_data:
            bank_account.account.initial_balance = validated_data['initial_balance'] or 0
            update_account = True
            
        if 'initial_balance_type' in validated_data:
            bank_account.account.initial_balance_type = validated_data['initial_balance_type']
            update_account = True
            
        if update_account:
            bank_account.account.save(update_fields=['name', 'initial_balance', 'initial_balance_type'])

        for field, value in validated_data.items():
            if field not in ('initial_balance', 'initial_balance_type'):
                setattr(bank_account, field, value)
        bank_account.save()
        return bank_account

    @staticmethod
    @transaction.atomic
    def process_issue(transfer, posted_by) -> JournalEntry:
        """
        Step 1: Outgoing Transfer (Issue)
        DR Cash in Transit (1113)
        CR Source Account (Cash or Bank)
        """
        transfer.full_clean()
        if transfer.issue_entry:
            raise ValueError("هذا التحويل تم إصدار قيده بالفعل")
            
        source_account = (transfer.from_cash_box.account if transfer.from_cash_box 
                          else transfer.from_bank.account)
        
        # ح/ نقدية بالطريق
        transit_account = Account.objects.get(code=getattr(settings, 'CASH_IN_TRANSIT_ACCOUNT', '1114'))
        
        lines = [
            {
                'account': transit_account,
                'debit': transfer.amount,
                'credit': 0,
                'description': f'نقدية بالطريق (تحويل صادر) - {transfer.description}'
            },
            {
                'account': source_account,
                'debit': 0,
                'credit': transfer.amount,
                'description': f'صرف تحويل نقدية - {transfer.description}'
            }
        ]
        
        entry = JournalService.create_entry(
            date_val=transfer.date,
            entry_type=JournalEntry.EntryType.BANK,
            description=f'إصدار تحويل نقدية رقم {transfer.number}',
            lines=lines,
            source_document=transfer,
            created_by=posted_by
        )
        
        transfer.issue_entry = entry
        transfer.status = CashTransfer.Status.PENDING
        transfer.save()

        from apps.core.services import AuditService
        AuditService.log(posted_by, 'Post', transfer, f'إصدار تحويل نقدية رقم {transfer.number}')

        return entry

    @staticmethod
    @transaction.atomic
    def process_receive(transfer, received_by) -> JournalEntry:
        """
        Step 2: Incoming Transfer (Receive)
        DR Destination Account (Cash or Bank)
        CR Cash in Transit (1113)
        """
        if transfer.status != CashTransfer.Status.PENDING:
            raise ValueError("لا يمكن استلام تحويل غير صادر أو تم استلامه مسبقاً")
        
        if transfer.receive_entry:
            raise ValueError("هذا التحويل تم تأكيد استلامه بالفعل")

        dest_account = (transfer.to_cash_box.account if transfer.to_cash_box 
                        else transfer.to_bank.account)
        
        # ح/ نقدية بالطريق
        transit_account = Account.objects.get(code=getattr(settings, 'CASH_IN_TRANSIT_ACCOUNT', '1114'))
        
        lines = [
            {
                'account': dest_account,
                'debit': transfer.amount,
                'credit': 0,
                'description': f'استلام تحويل نقدية - {transfer.description}'
            },
            {
                'account': transit_account,
                'debit': 0,
                'credit': transfer.amount,
                'description': f'إقفال نقدية بالطريق - {transfer.description}'
            }
        ]
        
        entry = JournalService.create_entry(
            date_val=timezone.now().date(),
            entry_type=JournalEntry.EntryType.BANK,
            description=f'تأكيد استلام تحويل رقم {transfer.number}',
            lines=lines,
            source_document=transfer,
            created_by=received_by
        )
        
        transfer.receive_entry = entry
        transfer.status = CashTransfer.Status.COMPLETED
        transfer.received_at = timezone.now()
        transfer.received_by = received_by
        transfer.save()

        from apps.core.services import AuditService
        AuditService.log(received_by, 'Receive', transfer, f'تأكيد استلام تحويل نقدية رقم {transfer.number}')

        return entry
    @staticmethod
    @transaction.atomic
    def reverse_transfer(transfer, reversed_by) -> JournalEntry:
        """
        عكس عملية تحويل (إصدار و/أو استلام)
        """
        if not transfer.issue_entry and not transfer.receive_entry:
            raise ValueError("هذا التحويل لم يتم ترحيله بعد")
        
        # عكس قيد الاستلام أولاً إذا وجد
        if transfer.receive_entry and not transfer.receive_entry.is_reversed:
            JournalService.reverse_entry(
                entry=transfer.receive_entry,
                date_val=timezone.now().date(),
                created_by=reversed_by
            )
        
        # عكس قيد الإصدار
        if transfer.issue_entry and not transfer.issue_entry.is_reversed:
            JournalService.reverse_entry(
                entry=transfer.issue_entry,
                date_val=timezone.now().date(),
                created_by=reversed_by
            )
        
        transfer.status = CashTransfer.Status.CANCELLED
        transfer.save()
        
        from apps.core.services import AuditService
        AuditService.log(reversed_by, 'Reverse', transfer, f'عكس تحويل نقدية رقم {transfer.number}')
        
        return None

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
            charge_acc = Account.objects.get(code=getattr(settings, 'BANK_CHARGES_ACCOUNT', '531'))
            lines.append({'account': charge_acc, 'debit': transaction_obj.amount, 'credit': 0, 'description': transaction_obj.description})
            lines.append({'account': bank_acc, 'debit': 0, 'credit': transaction_obj.amount, 'description': f'عمولة بنكية - {transaction_obj.number}'})
        
        elif transaction_obj.transaction_type == BankTransaction.TransactionType.INTEREST:
            # DR Bank Account (Asset) | CR Interest Revenue (Revenue)
            interest_acc = Account.objects.get(code=getattr(settings, 'INTEREST_REVENUE_ACCOUNT', '421'))
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


class BankReconciliationService:
    @staticmethod
    @transaction.atomic
    def reconcile(reconciliation, posted_by):
        """
        Finalizes a reconciliation.
        Marks all linked transactions as reconciled and calculates the final book balance.
        """
        if reconciliation.status == BankReconciliation.Status.COMPLETED:
            raise ValueError("هذه التسوية منتهية بالفعل")
            
        # Update linked transactions
        for trans in reconciliation.transactions.all():
            trans.is_reconciled = True
            trans.reconciled_at = timezone.now()
            trans.save()
            
        reconciliation.status = BankReconciliation.Status.COMPLETED
        reconciliation.save()
        
        from apps.core.services import AuditService
        AuditService.log(posted_by, 'Reconcile', reconciliation, f'إتمام المطابقة البنكية للبيان {reconciliation.statement_date}')
        return reconciliation

