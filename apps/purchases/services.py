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
            initial_balance=validated_data.get('initial_balance', 0) or 0,
            initial_balance_type=validated_data.get('initial_balance_type', 'credit'),
        )
        supplier_data = {k: v for k, v in validated_data.items() if k not in ('code', 'account', 'initial_balance', 'initial_balance_type')}
        return Supplier.objects.create(
            account=account, 
            code=validated_data.get('code'),
            **supplier_data
        )

    @staticmethod
    @transaction.atomic
    def update_supplier(supplier: Supplier, validated_data: dict) -> Supplier:
        update_account = False
        if 'name' in validated_data and validated_data['name'] != supplier.name:
            supplier.account.name = validated_data['name']
            update_account = True
        
        if 'initial_balance' in validated_data:
            supplier.account.initial_balance = validated_data['initial_balance'] or 0
            update_account = True
            
        if 'initial_balance_type' in validated_data:
            supplier.account.initial_balance_type = validated_data['initial_balance_type']
            update_account = True
            
        if update_account:
            supplier.account.save(update_fields=['name', 'initial_balance', 'initial_balance_type'])

        for field, value in validated_data.items():
            if field not in ('initial_balance', 'initial_balance_type'):
                setattr(supplier, field, value)
        supplier.save()
        return supplier

class PurchaseService:

    @staticmethod
    @transaction.atomic
    def post_invoice(invoice: PurchaseInvoice, posted_by) -> JournalEntry:
        """
        Purchase Invoice Journal Entry:
        DR  Inventory Account (per line)     → quantity * unit_cost + non-deductible taxes
        DR  VAT (deductible)                 → tax_amount
        CR  Supplier (Payable)               → invoice.total
        """
        if invoice.status == PurchaseInvoice.Status.POSTED:
            raise ValueError("هذه الفاتورة مرحلة بالفعل")

        if not invoice.lines.exists():
            raise ValueError("لا يمكن ترحيل فاتورة بدون أسطر")

        lines = []
        
        # 1. Group by Inventory Account (Warehouse-aware)
        # Sum (quantity * unit_cost) + (non-deductible taxes)
        inv_account_totals = {}
        tax_account_totals = {}

        for line in invoice.lines.all():
            # Determine target inventory account
            acc = line.warehouse.gl_account or line.item.inventory_account
            if not acc:
                raise ValueError(f"يرجى تحديد حساب المخزون للصنف {line.item.name} أو للمخزن {line.warehouse.name}")
            
            line_amount = line.quantity * line.unit_cost
            if acc.id not in inv_account_totals:
                inv_account_totals[acc.id] = {'account': acc, 'amount': 0}
            inv_account_totals[acc.id]['amount'] += line_amount

            # Taxes
            for tx_field in ['tax_type', 'tax_type2']:
                tx_type = getattr(line, tx_field)
                if tx_type:
                    tx_rate = getattr(line, f"{tx_field.replace('_type', '')}_percent") or tx_type.rate
                    tx_val = line_amount * (tx_rate / 100)
                    
                    if tx_type.category in ['table', 'customs']:
                        # Capitalize: Add to inventory cost on the same account
                        inv_account_totals[acc.id]['amount'] += tx_val
                    else:
                        # Record as separate tax account
                        tax_acc = tx_type.account
                        if not tax_acc: continue
                        if tax_acc.id not in tax_account_totals:
                            tax_account_totals[tax_acc.id] = {'account': tax_acc, 'amount': 0, 'category': tx_type.category}
                        tax_account_totals[tax_acc.id]['amount'] += tx_val

        # 2. Construct Journal Lines
        # CR Supplier
        lines.append({
            'account': invoice.supplier.account, 
            'debit': 0, 
            'credit': invoice.total,
            'description': f'فاتورة مشتريات {invoice.number}',
            'cost_center': invoice.cost_center
        })

        # DR Inventory Accounts
        for info in inv_account_totals.values():
            lines.append({
                'account': info['account'],
                'debit': info['amount'],
                'credit': 0,
                'description': f"مشتريات مخزنية - فاتورة {invoice.number}",
                'cost_center': invoice.cost_center
            })

        # DR/CR Tax Accounts
        for tax_info in tax_account_totals.values():
            if tax_info['amount'] > 0:
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
        
        # ✅ Fix: InventoryService increase_stock should also handle base quantities if needed, 
        # but let's ensure we use the right quantity here.
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
                quantity=-line.base_quantity, # ✅ Fix #1: استخدام الكمية الأساسية
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
            # شيكات مسحوبة - حساب وسيط 2141
            source_account = Account.objects.get(code=getattr(settings, 'CHEQUES_ISSUED_ACCOUNT', '2141'))
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
            remaining = invoice.total - invoice.paid_amount
            actual_alloc = min(allocation.amount, remaining)
            
            invoice.paid_amount += actual_alloc # ✅ Fix #2: منع الدفع الزائد
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
        CR  Discount (Reverse)           → discount_amount (✅ Fix #3: لموازنة القيد)
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

        # ✅ Fix #3: إضافة سطر للخصم لموازنة القيد
        if purchase_return.discount_amount > 0:
            # استخدام حساب خصم المشتريات (غالباً كود 422 أو من الإعدادات)
            discount_acc_code = getattr(settings, 'PURCHASE_DISCOUNT_ACCOUNT', '422')
            from apps.inventory.services import _get_or_create_account # أو استيراد مباشر
            discount_acc = Account.objects.get(code=discount_acc_code)
            lines.append({
                'account': discount_acc,
                'debit': 0,
                'credit': purchase_return.discount_amount,
                'description': f'خصم مكتسب (مرتجع {purchase_return.number})',
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
        
        # ✅ Fix #1: record_movement الآن جزء من الـ transaction بسبب @transaction.atomic
        from apps.inventory.models import StockMovement
        for line in purchase_return.lines.all():
            InventoryService.record_movement(
                date_val=purchase_return.date,
                item=line.item,
                warehouse=line.warehouse,
                movement_type=StockMovement.MovementType.PURCHASE_RETURN,
                quantity=-line.base_quantity, # ✅ Fix: استخدام الكمية الأساسية
                unit_cost=line.unit_cost,
                source=purchase_return,
                reference=purchase_return.number,
            )

        from apps.core.services import AuditService
        AuditService.log(posted_by, 'Post', purchase_return, f'ترحيل مرتجع مشتريات رقم {purchase_return.number}')

        return entry
