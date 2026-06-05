import logging
from datetime import date
from decimal import Decimal
from django.db import transaction
from django.conf import settings
from django.db.models import F
from apps.core.models import JournalEntry, Account
from apps.core.services import JournalService, DocumentService, AuditService
from apps.inventory.services import InventoryService
from apps.inventory.models import StockMovement
from apps.core.tax_utils import calculate_line_taxes
from .models import PurchaseInvoice, Supplier, SupplierPayment, PaymentAllocation, PurchaseReturn

logger = logging.getLogger(__name__)


def _conversion_to_base(line):
    """حساب معامل تحويل الوحدة إلى الوحدة الأساسية"""
    if not hasattr(line, 'unit') or not line.unit or not line.item:
        return Decimal('1')
    item = line.item
    if line.unit_id == item.base_unit_id:
        return Decimal('1')
    if line.unit_id == item.purchase_unit_id:
        return item.purchase_conversion_factor or Decimal('1')
    if line.unit_id == item.sales_unit_id:
        return item.conversion_factor or Decimal('1')
    return Decimal('1')

class SupplierService:
    SUPPLIERS_PARENT_CODE = getattr(settings, 'SUPPLIERS_PARENT_ACCOUNT', '2111')

    @staticmethod
    @transaction.atomic
    def create_supplier(validated_data: dict) -> Supplier:
        parent = Account.objects.select_for_update().get(code=SupplierService.SUPPLIERS_PARENT_CODE)
        # ✅ Fix: Use max code instead of count() to avoid duplicates
        from django.db.models import IntegerField
        from django.db.models.functions import Cast, Substr
        last_account = Account.objects.filter(parent=parent).annotate(
            seq_int=Cast(Substr('code', len(parent.code) + 1), output_field=IntegerField())
        ).order_by('-seq_int').first()
        if last_account:
            try:
                last_seq = last_account.seq_int
                next_seq = last_seq + 1
            except (ValueError, TypeError, IndexError):
                next_seq = Account.objects.filter(parent=parent).count() + 1
        else:
            next_seq = 1

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
        
        # Generate supplier code if not provided
        supplier_code = validated_data.get('code')
        if not supplier_code:
            supplier_code = SupplierService.generate_supplier_code()

        supplier_data = {k: v for k, v in validated_data.items() if k not in ('code', 'account', 'initial_balance', 'initial_balance_type')}
        return Supplier.objects.create(
            account=account, 
            code=supplier_code,
            **supplier_data
        )

    @staticmethod
    @transaction.atomic
    def generate_supplier_code():
        locked = Supplier.objects.select_for_update().filter(code__startswith='vend-').order_by('-code').first()
        if locked:
            try:
                last_num = int(locked.code.split('-')[1])
                next_num = last_num + 1
            except (IndexError, ValueError):
                next_num = Supplier.objects.count() + 1
        else:
            next_num = Supplier.objects.count() + 1
        
        code = f"vend-{next_num:06d}"
        while Supplier.objects.filter(code=code).exists():
            next_num += 1
            code = f"vend-{next_num:06d}"
        return code

    @staticmethod
    @transaction.atomic
    def update_supplier(supplier: Supplier, validated_data: dict) -> Supplier:
        # Lock the supplier and their linked account record
        supplier = Supplier.objects.select_for_update().get(pk=supplier.pk)
        supplier.account = Account.objects.select_for_update().get(pk=supplier.account.pk)
        
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
            if field not in ('initial_balance', 'initial_balance_type', 'code', 'account', 'account_id'):
                setattr(supplier, field, value)
        supplier.save()
        return supplier

class PurchaseService:

    @staticmethod
    @transaction.atomic
    def post_invoice(invoice: PurchaseInvoice, posted_by) -> JournalEntry:
        # Lock the invoice record to prevent concurrent posting/editing
        invoice = PurchaseInvoice.objects.select_for_update().get(pk=invoice.pk)
        
        if invoice.status == PurchaseInvoice.Status.POSTED:
            raise ValueError("هذه الفاتورة مرحلة بالفعل")
        if invoice.status == PurchaseInvoice.Status.CANCELLED:
            raise ValueError("لا يمكن ترحيل فاتورة ملغاة")

        if not invoice.lines.exists():
            raise ValueError("لا يمكن ترحيل فاتورة بدون أسطر")

        lines = []
        
        # 1. Group by Inventory Account (Warehouse-aware)
        # Sum (quantity * unit_cost) + (non-deductible taxes)
        inv_account_totals = {}
        tax_account_totals = {}

        for line in invoice.lines.all():
            # Determine target inventory account
            warehouse_acc = line.warehouse.gl_account if line.warehouse else None
            acc = warehouse_acc or line.item.inventory_account or getattr(line.item, 'expense_account', None)
            if not acc:
                raise ValueError(f"يرجى تحديد حساب المخزون للصنف {line.item.name} أو للمخزن {line.warehouse.name}")
            
            # Calculate net line amount (Price - Discount) to ensure balanced journal entry
            # and accurate average cost calculation in inventory.
            discount_pct = Decimal(str(line.discount_percent or '0'))
            line_net = line.quantity * line.unit_cost * (Decimal('1') - (discount_pct / Decimal('100')))
            
            res = calculate_line_taxes(
                line_net,
                line.tax_type,
                line.tax_percent,
                line.tax_type2,
                line.tax_percent2,
                is_purchase_or_expense=True
            )
            
            # Inventory Cost = Net + Table + Customs etc. (Capitalization)
            inv_cost = line_net + res['capitalized_amount']
            if acc.id not in inv_account_totals:
                inv_account_totals[acc.id] = {'account': acc, 'amount': Decimal('0')}
            inv_account_totals[acc.id]['amount'] += inv_cost
            
            # Non-capitalized taxes (VAT, WHT)
            for tx_type, tx_val in [(line.tax_type, res['tax1_value']), (line.tax_type2, res['tax2_value'])]:
                if tx_type and tx_val > 0:
                    if tx_type.category not in ['table', 'customs', 'stamp', 'other']:
                        tax_acc = tx_type.account
                        if not tax_acc:
                            raise ValueError(f"يرجى تحديد حساب الأستاذ لضريبة {tx_type.name}")
                        if tax_acc.id not in tax_account_totals:
                            tax_account_totals[tax_acc.id] = {'account': tax_acc, 'amount': Decimal('0'), 'category': tx_type.category}
                        tax_account_totals[tax_acc.id]['amount'] += tx_val

        # 2. Construct Journal Lines
        # In Purchases: Even for cash, we pass through the Supplier account (Credit)
        # to maintain a full history of transactions in the supplier ledger.
        # An automatic payment will be generated later if it's a cash invoice.
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

        total_dr = sum(l['debit'] for l in lines)
        total_cr = sum(l['credit'] for l in lines)
        if total_dr != total_cr:
            raise ValueError(f"عدم اتزان مالي: مدين {total_dr} ، دائن {total_cr}. يرجى مراجعة الخصومات والضرائب.")
            
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
        
        # 3. Handle Auto-Payment for Cash Purchases
        if invoice.payment_type == PurchaseInvoice.PaymentType.CASH:
            # Determine payment method
            pm = 'cash'
            if invoice.payment_method == 'bank':
                pm = 'bank'

            payment = SupplierPayment.objects.create(
                number=DocumentService.generate_number(SupplierPayment, 'PAY'),
                date=invoice.date,
                supplier=invoice.supplier,
                amount=invoice.total,
                payment_method=pm,
                cash_box=invoice.cash_box,
                bank_account=invoice.bank_account,
                created_by=posted_by,
                reference=f"Settlement for {invoice.number}",
            )
            # Create allocation
            PaymentAllocation.objects.create(
                payment=payment,
                invoice=invoice,
                amount=invoice.total
            )
            # Post the payment
            PurchaseService.record_payment(payment, posted_by)

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
        invoice = PurchaseInvoice.objects.select_for_update().get(pk=invoice.pk)
        if invoice.status != PurchaseInvoice.Status.POSTED:
            raise ValueError("يمكن فقط عكس الفواتير المرحلة")
        
        if not invoice.journal_entry:
            raise ValueError("الفاتورة لا تملك قيداً محاسبياً لعكسه")

        if invoice.journal_entry.is_reversed:
            raise ValueError("هذه الفاتورة تم عكسها مسبقاً")

        if invoice.paid_amount > 0:
            raise ValueError(
                f"لا يمكن عكس فاتورة مدفوعة جزئياً ({invoice.paid_amount:.2f}). "
                f"يرجى عكس سندات الصرف المرتبطة أولاً"
            )

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
        for line in invoice.lines.all():
            base_qty = line.base_quantity or line.quantity
            if base_qty <= 0:
                continue

            discount_pct = Decimal(str(line.discount_percent or '0'))
            line_net = line.quantity * line.unit_cost * (Decimal('1') - (discount_pct / Decimal('100')))
            res = calculate_line_taxes(line_net, line.tax_type, line.tax_percent or 0, line.tax_type2, line.tax_percent2 or 0, is_purchase_or_expense=True)
            inv_cost = line_net + res['capitalized_amount']
            base_qty = line.base_quantity or line.quantity
            unit_cost_base = (inv_cost / base_qty) if base_qty > 0 else Decimal('0')

            InventoryService.record_movement(
                date_val=date.today(),
                item=line.item,
                warehouse=line.warehouse,
                movement_type=StockMovement.MovementType.PURCHASE_RETURN,
                quantity=-base_qty,
                unit_cost=unit_cost_base,
                source=invoice,
                reference=f'Reverse {invoice.number}'
            )

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
        payment = SupplierPayment.objects.select_for_update().get(pk=payment.pk)
        if payment.journal_entry:
            raise ValueError("هذا السند مرحل بالفعل")
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
            if not payment.bank_account:
                raise ValueError("يجب تحديد الحساب البنكي للدفع عبر البنك")
            source_account = payment.bank_account.account
        elif payment.payment_method == 'cheque':
            # شيكات مسحوبة - حساب وسيط 2141
            source_account = Account.objects.get(code=getattr(settings, 'CHEQUES_ISSUED_ACCOUNT', '2141'))
        else:
            if not payment.cash_box:
                raise ValueError("يجب تحديد الخزنة للدفع النقدي")
            source_account = payment.cash_box.account
            
        # Credit Bank/Cash/Cheque
        lines.append({
            'account': source_account,
            'debit': 0,
            'credit': payment.amount,
            'description': f'سند صرف رقم {payment.number}'
        })
        
        total_dr = sum(l['debit'] for l in lines)
        total_cr = sum(l['credit'] for l in lines)
        if total_dr != total_cr:
            raise ValueError(f"عدم اتزان مالي: مدين {total_dr} ، دائن {total_cr}. يرجى مراجعة الخصومات والضرائب.")
            
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
        total_allocated = Decimal('0')
        for allocation in payment.paymentallocation_set.select_related('invoice').all():
            if allocation.amount <= 0:
                raise ValueError("مبلغ التخصيص يجب أن يكون موجباً")
            total_allocated += allocation.amount
            
            invoice = allocation.invoice
            Invoice = type(invoice)
            locked_invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
            
            if locked_invoice.status != PurchaseInvoice.Status.POSTED:
                raise ValueError(f"لا يمكن السداد لفاتورة غير مرحلة أو ملغاة: {locked_invoice.number}")
                
            if locked_invoice.paid_amount + allocation.amount > locked_invoice.total:
                raise ValueError(f"التخصيص يتجاوز المتبقي للفاتورة {locked_invoice.number}")
                
            locked_invoice.paid_amount += allocation.amount
            locked_invoice.save(update_fields=['paid_amount'])
            
        if total_allocated > payment.amount:
            raise ValueError("إجمالي التخصيصات يتجاوز مبلغ السند")

        AuditService.log(posted_by, 'Record', payment, f'تسجيل سند صرف مورد رقم {payment.number}')

        return entry

    @staticmethod
    @transaction.atomic
    def clear_cheque(payment: SupplierPayment, cleared_date, cleared_by):
        """
        Clears a supplier cheque.
        DR  Cheques Issued (Liability)   → payment.amount
        CR  Bank Account                 → payment.amount
        """
        payment = SupplierPayment.objects.select_for_update().get(pk=payment.pk)
        if payment.payment_method != 'cheque':
            raise ValueError("هذا السند ليس شيكاً")
        if payment.is_cleared:
            raise ValueError("هذا الشيك تم صرفه بالفعل")
        if not payment.bank_account:
            raise ValueError("لا يوجد حساب بنكي مسجل مع هذا الشيك")

        # 1. Update Payment Status
        payment.is_cleared = True
        payment.cleared_at = cleared_date
        payment.save(update_fields=['is_cleared', 'cleared_at'])

        # 2. Create Journal Entry
        cheques_issued_acc = Account.objects.get(code=getattr(settings, 'CHEQUES_ISSUED_ACCOUNT', '2141'))
        bank_acc = payment.bank_account.account

        lines = [
            {
                'account': cheques_issued_acc,
                'debit': payment.amount,
                'credit': 0,
                'description': f'صرف الشيك رقم {payment.cheque_number}'
            },
            {
                'account': bank_acc,
                'debit': 0,
                'credit': payment.amount,
                'description': f'صرف الشيك رقم {payment.cheque_number}'
            }
        ]

        entry = JournalService.create_entry(
            date_val=cleared_date,
            entry_type=JournalEntry.EntryType.BANK,
            description=f'صرف الشيك الصادر رقم {payment.cheque_number} للمورد {payment.supplier.name}',
            lines=lines,
            source_document=payment,
            created_by=cleared_by
        )

        AuditService.log(cleared_by, 'Record', payment, f'تم صرف الشيك رقم {payment.cheque_number} في البنك')
        return entry

    @staticmethod
    @transaction.atomic
    def post_return(purchase_return, posted_by) -> JournalEntry:
        """
        Purchase Return Journal Entry:
        DR  Supplier (Payable ↓)         → total_amount
        CR  Inventory Account (↓)        → Net + Capitalized taxes
        CR  Tax Deductible (Reverse)     → VAT (Credit), WHT (Debit)
        """
        purchase_return = PurchaseReturn.objects.select_for_update().get(pk=purchase_return.pk)
        if purchase_return.status == PurchaseReturn.Status.POSTED:
            raise ValueError("هذا المرتجع مرحل بالفعل")

        lines = []
        
        # Debit: Supplier (Liability decrease)
        lines.append({
            'account': purchase_return.supplier.account,
            'debit': purchase_return.total,
            'credit': 0,
            'description': f"مرتجع مشتريات رقم {purchase_return.number} - {purchase_return.supplier.name}",
            'cost_center': purchase_return.cost_center
        })

        if getattr(purchase_return, 'payment_type', 'credit') == 'cash':
            cash_account = None
            if purchase_return.cash_box:
                cash_account = purchase_return.cash_box.account
            elif purchase_return.invoice and purchase_return.invoice.cash_box:
                cash_account = purchase_return.invoice.cash_box.account
                
            if cash_account:
                lines.append({
                    'account': purchase_return.supplier.account,
                    'debit': 0,
                    'credit': purchase_return.total,
                    'description': f"استرداد نقدي لمرتجع رقم {purchase_return.number}",
                    'cost_center': purchase_return.cost_center
                })
                lines.append({
                    'account': cash_account,
                    'debit': purchase_return.total,
                    'credit': 0,
                    'description': f"استرداد نقدي لمرتجع رقم {purchase_return.number}",
                    'cost_center': purchase_return.cost_center
                })
            else:
                raise ValueError("لا يمكن تحديد الخزينة للاسترداد النقدي")

        inv_account_totals = {}
        tax_account_totals = {}

        for line in purchase_return.lines.all():
            # Determine target inventory account (Warehouse-aware)
            warehouse_acc = line.warehouse.gl_account if line.warehouse else None
            acc = warehouse_acc or line.item.inventory_account or getattr(line.item, 'expense_account', None)
            if not acc:
                raise ValueError(f"يرجى تحديد حساب المخزون للصنف {line.item.name} أو للمخزن {line.warehouse.name}")
            
            discount_pct = Decimal(str(line.discount_percent or '0'))
            line_net = line.quantity * line.unit_cost * (Decimal('1') - (discount_pct / Decimal('100')))
            
            res = calculate_line_taxes(
                line_net,
                line.tax_type,
                line.tax_percent,
                line.tax_type2,
                line.tax_percent2,
                is_purchase_or_expense=True
            )
            
            # Inventory Cost to credit = Net + Capitalized taxes
            inv_cost = line_net + res['capitalized_amount']
            if acc.id not in inv_account_totals:
                inv_account_totals[acc.id] = {'account': acc, 'amount': Decimal('0')}
            inv_account_totals[acc.id]['amount'] += inv_cost
            
            # Non-capitalized taxes (VAT, WHT)
            for tx_type, tx_val in [(line.tax_type, res['tax1_value']), (line.tax_type2, res['tax2_value'])]:
                if tx_type and tx_val > 0:
                    if tx_type.category not in ['table', 'customs', 'stamp', 'other']:
                        tax_acc = tx_type.account
                        if not tax_acc:
                            raise ValueError(f"يرجى تحديد حساب الأستاذ لضريبة {tx_type.name}")
                        if tax_acc.id not in tax_account_totals:
                            tax_account_totals[tax_acc.id] = {'account': tax_acc, 'amount': Decimal('0'), 'category': tx_type.category}
                        tax_account_totals[tax_acc.id]['amount'] += tx_val

        # CR Inventory Accounts
        for info in inv_account_totals.values():
            lines.append({
                'account': info['account'],
                'debit': 0,
                'credit': info['amount'],
                'description': f"مردودات مشتريات - مرتجع {purchase_return.number}",
                'cost_center': purchase_return.cost_center
            })

        # CR/DR Tax Accounts
        for tax_info in tax_account_totals.values():
            if tax_info['amount'] > 0:
                # WHT is debited in returns (reducing the WHT deduction credit)
                # VAT is credited in returns (reducing the VAT debit)
                is_debit = (tax_info['category'] in ['wht', 'insurance', 'salary'])
                lines.append({
                    'account': tax_info['account'],
                    'debit': tax_info['amount'] if is_debit else 0,
                    'credit': 0 if is_debit else tax_info['amount'],
                    'description': f"عكس ضريبة {tax_info['account'].name} (مرتجع مشتريات)",
                    'cost_center': purchase_return.cost_center
                })

        total_dr = sum(l['debit'] for l in lines)
        total_cr = sum(l['credit'] for l in lines)
        if total_dr != total_cr:
            raise ValueError(f"عدم اتزان مالي: مدين {total_dr} ، دائن {total_cr}. يرجى مراجعة الخصومات والضرائب.")
            
        entry = JournalService.create_entry(
            date_val=purchase_return.date,
            entry_type=JournalEntry.EntryType.PURCHASE,
            description=f'مرتجع مشتريات رقم {purchase_return.number}',
            lines=lines,
            source_document=purchase_return,
            created_by=posted_by,
        )
        
        purchase_return.journal_entry = entry
        purchase_return.status = PurchaseReturn.Status.POSTED
        purchase_return.save()
        
        for line in purchase_return.lines.all():
            discount_pct = Decimal(str(line.discount_percent or '0'))
            line_net = line.quantity * line.unit_cost * (Decimal('1') - (discount_pct / Decimal('100')))
            res = calculate_line_taxes(line_net, line.tax_type, line.tax_percent or 0, line.tax_type2, line.tax_percent2 or 0, is_purchase_or_expense=True)
            inv_cost = line_net + res['capitalized_amount']
            base_qty = line.base_quantity or line.quantity
            unit_cost_base = (inv_cost / base_qty) if base_qty > 0 else Decimal('0')

            InventoryService.record_movement(
                date_val=purchase_return.date,
                item=line.item,
                warehouse=line.warehouse,
                movement_type=StockMovement.MovementType.PURCHASE_RETURN,
                quantity=-(line.base_quantity or line.quantity),
                unit_cost=unit_cost_base,
                source=purchase_return,
                reference=purchase_return.number,
            )

        AuditService.log(posted_by, 'Post', purchase_return, f'ترحيل مرتجع مشتريات رقم {purchase_return.number}')

        return entry
