from django.db import transaction
from django.conf import settings
from apps.core.models import JournalEntry, Account
from apps.core.services import JournalService
from apps.inventory.services import InventoryService
from .models import PurchaseInvoice, Supplier

class SupplierService:
    SUPPLIERS_PARENT_CODE = getattr(settings, 'SUPPLIERS_PARENT_ACCOUNT', '2111')

    @staticmethod
    @transaction.atomic
    def create_supplier(validated_data: dict) -> Supplier:
        parent = Account.objects.select_for_update().get(code=SupplierService.SUPPLIERS_PARENT_CODE)
        next_seq = Account.objects.filter(parent=parent).count() + 1
        account_code = f'{parent.code}{next_seq:03d}'

        account = Account.objects.create(
            code=account_code,
            name=validated_data['name'],
            account_type=parent.account_type,
            parent=parent,
            is_leaf=True,
        )
        supplier_data = {k: v for k, v in validated_data.items() if k not in ('code', 'account')}
        return Supplier.objects.create(
            account=account, 
            code=validated_data.get('code'),
            **supplier_data
        )

class PurchaseService:

    @staticmethod
    @transaction.atomic
    def post_invoice(invoice: PurchaseInvoice, posted_by) -> JournalEntry:
        """
        Purchase Invoice Journal Entry:
        DR  Inventory Account (per line)     → quantity * unit_cost
        DR  Tax Deductible (if applicable)   → tax_amount
        CR  Supplier (Payable)               → invoice.total
        """
        if invoice.status == PurchaseInvoice.Status.POSTED:
            raise ValueError("هذه الفاتورة مرحلة بالفعل")

        if not invoice.lines.exists():
            raise ValueError("لا يمكن ترحيل فاتورة بدون أسطر")

        lines = []

        # Credit supplier payable
        lines.append({
            'account': invoice.supplier.account, 
            'debit': 0, 
            'credit': invoice.total,
            'description': f'فاتورة مشتريات {invoice.number}',
            'cost_center': invoice.cost_center
        })

        # Debit inventory per line
        for line in invoice.lines.all():
            lines.append({
                'account': line.item.inventory_account, 
                'debit': line.quantity * line.unit_cost, 
                'credit': 0,
                'description': f'إضافة مخزون - {line.item.name}',
                'cost_center': invoice.cost_center
            })

        # Group taxes by account
        tax_lines = {}
        capitalized_tax_amount = 0  # For Table Tax and Customs which are added to inventory cost
        
        for line in invoice.lines.all():
            line_amount = line.quantity * line.unit_cost
            
            # Process Tax 1
            if line.tax_type:
                tax_rate = line.tax_percent if line.tax_percent else line.tax_type.rate
                tax_val = line_amount * (tax_rate / 100)
                
                if line.tax_type.category in ['table', 'customs']:
                    # Capitalize: Add to inventory cost
                    capitalized_tax_amount += tax_val
                else:
                    # Record as separate line (VAT, WHT, etc.)
                    acc = line.tax_type.account
                    if acc.id not in tax_lines:
                        tax_lines[acc.id] = {'account': acc, 'amount': 0, 'category': line.tax_type.category}
                    tax_lines[acc.id]['amount'] += tax_val
            
            # Process Tax 2
            if hasattr(line, 'tax_type2') and line.tax_type2:
                tax_rate2 = line.tax_percent2 if line.tax_percent2 else line.tax_type2.rate
                tax_val2 = line_amount * (tax_rate2 / 100)
                
                if line.tax_type2.category in ['table', 'customs']:
                    capitalized_tax_amount += tax_val2
                else:
                    acc2 = line.tax_type2.account
                    if acc2.id not in tax_lines:
                        tax_lines[acc2.id] = {'account': acc2, 'amount': 0, 'category': line.tax_type2.category}
                    tax_lines[acc2.id]['amount'] += tax_val2

        # 1. Main Inventory/Purchase Line (Capitalized with Table Tax/Customs)
        lines.append({
            'account': inventory_account,
            'debit': invoice.subtotal + capitalized_tax_amount,
            'credit': 0,
            'description': f"مشتريات - فاتورة {invoice.number} (شاملة الضرائب غير المستردة)",
            'cost_center': invoice.cost_center
        })

        # 2. Tax Lines (VAT, WHT, etc.)
        for tax_info in tax_lines.values():
            if tax_info['amount'] > 0:
                # In Purchases: WHT and Insurance are credits (liabilities)
                is_credit = (tax_info['category'] in ['wht', 'insurance', 'salary'])
                lines.append({
                    'account': tax_info['account'],
                    'debit': 0 if is_credit else tax_info['amount'],
                    'credit': tax_info['amount'] if is_credit else 0,
                    'description': f"ضريبة {tax_info['account'].name}",
                    'cost_center': invoice.cost_center
                })

        entry = JournalService.create_entry(
            date_val=invoice.date,
            entry_type=JournalEntry.EntryType.PURCHASE,
            description=f'فاتورة مشتريات رقم {invoice.number}',
            lines=lines,
            source_document=invoice,
            created_by=posted_by,
        )
        
        invoice.journal_entry = entry
        invoice.status = PurchaseInvoice.Status.POSTED
        invoice.save()
        
        InventoryService.increase_stock(invoice)
        return entry

    @staticmethod
    @transaction.atomic
    def reverse_invoice(invoice: PurchaseInvoice, reversed_by) -> JournalEntry:
        """
        Reverses a posted purchase invoice by creating a reversal journal entry 
        and reducing inventory stock.
        """
        if invoice.status != PurchaseInvoice.Status.POSTED:
            raise ValueError("يمكن فقط عكس الفواتير المرحلة")
        
        if not invoice.journal_entry:
            raise ValueError("الفاتورة لا تملك قيداً محاسبياً لعكسه")

        from datetime import date
        # 1. Reverse the Journal Entry
        reversal_entry = JournalService.reverse_entry(
            invoice.journal_entry, 
            date_val=date.today(), 
            created_by=reversed_by
        )

        # 2. Update Invoice Status
        invoice.status = PurchaseInvoice.Status.CANCELLED
        invoice.save()

        # 3. Reduce Inventory Stock (Inverse of increase_stock)
        from apps.inventory.models import StockMovement
        for line in invoice.lines.all():
            InventoryService.record_movement(
                date_val=date.today(),
                item=line.item,
                warehouse=line.warehouse,
                movement_type=StockMovement.MovementType.ADJUSTMENT_OUT,
                quantity=-line.quantity,
                unit_cost=line.unit_cost,
                source=invoice,
                reference=f'Reverse {invoice.number}'
            )

        from apps.core.services import AuditService
        AuditService.log(reversed_by, 'Reverse', invoice, f'عكس فاتورة مشتريات رقم {invoice.number}')
        return reversal_entry

    @staticmethod
    @transaction.atomic
    def record_payment(payment, posted_by) -> JournalEntry:
        """
        Supplier Payment Journal Entry:
        DR  Supplier Payable            → payment.amount
        CR  Cash/Bank Account           → payment.amount
        """
        lines = []
        
        # Debit Supplier
        lines.append({
            'account': payment.supplier.account,
            'debit': payment.amount,
            'credit': 0,
            'description': f'سداد للمورد {payment.supplier.name}'
        })
        
        # Determine source account
        if payment.payment_method == 'bank':
            source_account = payment.bank_account.account
        elif payment.payment_method == 'cheque':
            # شيكات مسحوبة - حساب وسيط 2132
            source_account = Account.objects.get(code=getattr(settings, 'CHEQUES_ISSUED_ACCOUNT', '2132'))
        else:
            source_account = payment.cash_box.account
            
        # Credit Bank/Cash/Cheque
        lines.append({
            'account': source_account,
            'debit': 0,
            'credit': payment.amount,
            'description': f'سند صرف رقم {payment.number}'
        })
        
        entry = JournalService.create_entry(
            date_val=payment.date,
            entry_type=JournalEntry.EntryType.PAYMENT,
            description=f'سند صرف رقم {payment.number}',
            lines=lines,
            source_document=payment,
            created_by=posted_by,
        )
        
        payment.journal_entry = entry
        payment.save()

        # Update paid_amount in related invoices
        for allocation in payment.paymentallocation_set.all():
            invoice = allocation.invoice
            invoice.paid_amount += allocation.amount
            invoice.save()

        from apps.core.services import AuditService
        AuditService.log(posted_by, 'Record', payment, f'تسجيل سند صرف مورد رقم {payment.number}')

        return entry

    @staticmethod
    @transaction.atomic
    def post_return(purchase_return, posted_by) -> JournalEntry:
        """
        Purchase Return Journal Entry:
        DR  Supplier (Payable ↓)         → total_amount
        CR  Inventory Account (↓)        → quantity * unit_cost
        CR  Tax Deductible (Reverse)     → tax_amount
        """
        if purchase_return.status == 'posted':
            raise ValueError("هذا المرتجع مرحل بالفعل")

        lines = []
        
        # Debit: Supplier (Liability decrease)
        lines.append({
            'account': purchase_return.supplier.account,
            'debit': purchase_return.total,
            'credit': 0,
            'description': f"Purchase Return {purchase_return.number} - {purchase_return.supplier.name}",
            'cost_center': purchase_return.cost_center
        })

        for line in purchase_return.lines.all():
            # Credit: Inventory
            lines.append({
                'account': line.item.inventory_account,
                'debit': 0,
                'credit': line.quantity * line.unit_cost,
                'description': f'مردودات مشتريات - {line.item.name}',
                'cost_center': purchase_return.cost_center
            })

        # Group taxes by account
        tax_lines = {}
        for line in purchase_return.lines.all():
            if line.tax_type:
                tax_rate = line.tax_percent if line.tax_percent else line.tax_type.rate
                tax_val = (line.quantity * line.unit_cost) * (tax_rate / 100)
                acc = line.tax_type.account
                if acc.id not in tax_lines:
                    tax_lines[acc.id] = {'account': acc, 'amount': 0, 'category': line.tax_type.category}
                tax_lines[acc.id]['amount'] += tax_val

        for tax_info in tax_lines.values():
            if tax_info['amount'] > 0:
                # If VAT was debited in purchases, it's credited in returns
                is_credit = (tax_info['category'] != 'wht') 
                lines.append({
                    'account': tax_info['account'],
                    'debit': tax_info['amount'] if not is_credit else 0,
                    'credit': tax_info['amount'] if is_credit else 0,
                    'description': f"عكس ضريبة {tax_info['account'].name} (مرتجع مشتريات)",
                    'cost_center': purchase_return.cost_center
                })

        entry = JournalService.create_entry(
            date_val=purchase_return.date,
            entry_type=JournalEntry.EntryType.PURCHASE,
            description=f'مرتجع مشتريات رقم {purchase_return.number}',
            lines=lines,
            source_document=purchase_return,
            created_by=posted_by,
        )
        
        purchase_return.journal_entry = entry
        purchase_return.status = 'posted'
        purchase_return.save()
        
        for line in purchase_return.lines.all():
            InventoryService.record_movement(
                date_val=purchase_return.date,
                item=line.item,
                warehouse=line.warehouse,
                movement_type='purchase_return',
                quantity=-line.quantity,
                unit_cost=getattr(line, 'unit_price', None) or line.unit_cost,
                source=purchase_return,
                reference=purchase_return.number,
            )

        from apps.core.services import AuditService
        AuditService.log(posted_by, 'Post', purchase_return, f'ترحيل مرتجع مشتريات رقم {purchase_return.number}')

        return entry
