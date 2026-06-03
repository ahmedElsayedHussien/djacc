from datetime import date
from decimal import Decimal
from django.db import transaction
from django.db.models import Max, F, Sum
from django.conf import settings
from apps.core.models import JournalEntry, Account
from apps.core.services import JournalService, AuditService, DocumentService
from apps.core.tax_utils import calculate_line_taxes
from apps.inventory.models import Item, Warehouse, StockMovement
from apps.treasury.models import CashBox
from apps.treasury.services import TreasuryService
from apps.inventory.services import InventoryService
from .models import SalesInvoice, Customer, SalesRepresentative, CustomerReceipt, IntermediaryCompany, ReceiptAllocation, SalesReturn, RepSettlementInvoice, RepDailySettlement

class CustomerService:
    CUSTOMERS_PARENT_CODE = getattr(settings, 'CUSTOMERS_PARENT_ACCOUNT', '1121')

    @staticmethod
    def generate_customer_code():
        with transaction.atomic():
            last_customer = Customer.objects.select_for_update().filter(
                code__regex=r'^cus-\d+$'
            ).order_by('-code').first()
            if last_customer:
                try:
                    parts = last_customer.code.split('-')
                    if len(parts) > 1:
                        next_num = int(parts[1]) + 1
                    else:
                        next_num = Customer.objects.count() + 1
                except (IndexError, ValueError):
                    next_num = Customer.objects.count() + 1
            else:
                next_num = 1

            code = f"cus-{next_num:05d}"
            while Customer.objects.filter(code=code).exists():
                next_num += 1
                code = f"cus-{next_num:05d}"
            return code

    @staticmethod
    @transaction.atomic
    def create_customer(validated_data: dict) -> Customer:
        """
        1. يُنشئ الحساب المحاسبي للعميل تحت شجرة العملاء
        2. يُنشئ سجل العميل مرتبطاً بالحساب
        """
        parent = Account.objects.select_for_update().get(code=CustomerService.CUSTOMERS_PARENT_CODE)

        # Generate account code: parent_code + sequential number (Safe Max+1 logic)
        last_code = Account.objects.filter(parent=parent).aggregate(Max('code'))['code__max']
        if last_code:
            try:
                next_seq = int(last_code[len(parent.code):]) + 1
            except (ValueError, TypeError):
                next_seq = Account.objects.filter(parent=parent).count() + 1
        else:
            next_seq = 1
        account_code = f'{parent.code}{next_seq:03d}'

        # Create the accounting account
        account = Account.objects.create(
            code=account_code,
            name=validated_data['name'],
            account_type=parent.account_type,
            parent=parent,
            is_leaf=True,
            currency='EGP',
            initial_balance=validated_data.get('initial_balance', 0) or 0,
            initial_balance_type=validated_data.get('initial_balance_type', 'debit'),
        )

        # Create the customer linked to that account
        customer_data = {k: v for k, v in validated_data.items() if k not in ('code', 'account', 'initial_balance', 'initial_balance_type')}
        
        customer_code = validated_data.get('code')
        if not customer_code:
            customer_code = CustomerService.generate_customer_code()

        customer = Customer.objects.create(
            account=account,
            code=customer_code,
            **customer_data,
        )
        return customer

    @staticmethod
    @transaction.atomic
    def update_customer(customer: Customer, validated_data: dict) -> Customer:
        # Lock the customer and their linked account record
        customer = Customer.objects.select_for_update().get(pk=customer.pk)
        customer.account = Account.objects.select_for_update().get(pk=customer.account.pk)
        
        # Update account fields
        update_account = False
        if 'name' in validated_data and validated_data['name'] != customer.name:
            customer.account.name = validated_data['name']
            update_account = True
        
        if 'initial_balance' in validated_data:
            customer.account.initial_balance = validated_data['initial_balance'] or 0
            update_account = True
            
        if 'initial_balance_type' in validated_data:
            customer.account.initial_balance_type = validated_data['initial_balance_type']
            update_account = True
            
        if update_account:
            customer.account.save(update_fields=['name', 'initial_balance', 'initial_balance_type'])

        for field, value in validated_data.items():
            if field not in ('initial_balance', 'initial_balance_type'):
                setattr(customer, field, value)
        customer.save()
        return customer

class SalesRepresentativeService:
    REP_INVENTORY_PARENT = getattr(settings, 'SALES_REP_INVENTORY_PARENT', '1134')

    @staticmethod
    def generate_rep_code():
        with transaction.atomic():
            last_rep = SalesRepresentative.objects.select_for_update().filter(
                code__regex=r'^sr-\d+$'
            ).order_by('-code').first()
            if last_rep:
                try:
                    parts = last_rep.code.split('-')
                    if len(parts) > 1:
                        next_num = int(parts[1]) + 1
                    else:
                        next_num = SalesRepresentative.objects.count() + 1
                except (IndexError, ValueError):
                    next_num = SalesRepresentative.objects.count() + 1
            else:
                next_num = 1

            code = f"sr-{next_num:05d}"
            while SalesRepresentative.objects.filter(code=code).exists():
                next_num += 1
                code = f"sr-{next_num:05d}"
            return code

    @staticmethod
    @transaction.atomic
    def create_rep(validated_data: dict) -> SalesRepresentative:
        """
        1. إنشاء مخزن للمندوب (مع ربطه بحساب محاسبي آلياً)
        2. إنشاء خزنة للمندوب (مرتبطة بحساب محاسبي)
        3. إنشاء سجل المندوب
        """
        employee = validated_data.get('employee')
        rep_name = validated_data.get('name')
        rep_user = validated_data.get('user')
        
        if employee:
            rep_name = f"{employee.first_name} {employee.last_name}"
            rep_user = employee.user

        # Generate rep code if not provided
        rep_code = validated_data.get('code')
        if not rep_code:
            rep_code = SalesRepresentativeService.generate_rep_code()

        # 1. Create Warehouse Account
        parent_inv = Account.objects.select_for_update().get(
            code=SalesRepresentativeService.REP_INVENTORY_PARENT
        )

        last_code = Account.objects.filter(parent=parent_inv).aggregate(Max('code'))['code__max']
        if last_code:
            try:
                next_seq = int(last_code[len(parent_inv.code):]) + 1
            except (ValueError, TypeError):
                next_seq = Account.objects.filter(parent=parent_inv).count() + 1
        else:
            next_seq = 1
        warehouse_account = Account.objects.create(
            code=f'{parent_inv.code}{next_seq:03d}',
            name=f'مخزن مندوب - {rep_name}',
            account_type='asset',
            parent=parent_inv,
            is_leaf=True,
        )

        # 2. Create Warehouse
        warehouse = Warehouse.objects.create(
            code=f"W-{rep_code}",
            name=f"مخزن مندوب - {rep_name}",
            gl_account=warehouse_account
        )

        # 3. Create CashBox using TreasuryService
        cash_box_data = {
            'code': f"CB-{rep_code}",
            'name': f"خزنة مندوب - {rep_name}",
            'responsible_user': rep_user,
            'currency': 'EGP'
        }
        cash_box = TreasuryService.create_cash_box(cash_box_data)

        # 4. Create Rep (بدون account أولاً)
        rep_data = {k: v for k, v in validated_data.items()
                    if k not in ('warehouse', 'cash_box', 'account', 'code')}
        rep = SalesRepresentative.objects.create(
            code=rep_code,
            warehouse=warehouse,
            cash_box=cash_box,
            **rep_data
        )

        # 5. Create accounting account for rep receivable
        account = RepSettlementService.create_rep_account(rep)
        rep.account = account
        rep.save(update_fields=['account'])

        return rep

class SalesService:

    @staticmethod
    @transaction.atomic
    def post_invoice(invoice: SalesInvoice, posted_by) -> JournalEntry:
        """
        Sales Invoice Journal Entry:
        DR  Customer (Receivable)           → invoice.total
        CR  Revenue Account (per line)      → line.total - line.tax
        CR  Tax Payable                     → invoice.tax_amount
        DR  Cost of Goods Sold              → item.cost * quantity
        CR  Inventory                       → item.cost * quantity
        """
        # Lock the invoice record to prevent concurrent posting/editing
        invoice = SalesInvoice.objects.select_for_update().get(pk=invoice.pk)

        if invoice.status == SalesInvoice.Status.POSTED:
            raise ValueError("هذه الفاتورة مرحلة بالفعل")

        if not invoice.lines.exists():
            raise ValueError("لا يمكن ترحيل فاتورة بدون أسطر")

        # ✅ Fix #1 & #2: تحديث المخزون أولاً للحصول على التكلفة الحقيقية (بعد الـ lock) لضمان مطابقة القيد للمخازن
        line_costs = InventoryService.reduce_stock(invoice)

        # 1. Always Debit Customer for Sales Invoices (to track in AR)
        # For Cash sales, we will create an auto-receipt next.
        debit_account = invoice.customer.account

        lines = []
        # Debit: Customer
        lines.append({
            'account': debit_account,
            'debit': invoice.total,
            'credit': 0,
            'description': f"فاتورة مبيعات {invoice.number} - {invoice.customer.name}",
            'cost_center': invoice.cost_center
        })

        # Credit revenue and Debit discount per line
        for line in invoice.lines.all():
            # Gross Revenue = quantity * unit_price (before discount)
            gross_revenue = line.quantity * line.unit_price

            # CR Revenue (Gross)
            lines.append({
                'account': line.revenue_account, 
                'debit': 0, 
                'credit': gross_revenue,
                'description': f'إيراد مبيعات - {line.item.name}',
                'cost_center': invoice.cost_center
            })

            # DR Sales Discount (if any)
            discount_total = (line.quantity * line.unit_price) * (line.discount_percent / Decimal('100'))
            if discount_total > 0:
                discount_account = Account.objects.get(code=getattr(settings, 'SALES_DISCOUNT_ACCOUNT', '414'))
                lines.append({
                    'account': discount_account,
                    'debit': discount_total,
                    'credit': 0,
                    'description': f'خصم مبيعات - {line.item.name}',
                    'cost_center': invoice.cost_center
                })
            
            # COGS entry (✅ Fix #1: استخدام الكمية الأساسية من السطر)
            cost = line_costs.get(line.id, line.cost)
            if cost <= 0:
                raise ValueError(f"تكلفة الصنف {line.item.name} تساوي صفراً، لا يمكن ترحيل الفاتورة وتجاهل حساب التكلفة للمخزون.")
                
            base_qty = getattr(line, 'base_quantity', line.quantity) or line.quantity
            
            lines.append({
                'account': line.cost_of_goods_account, 
                'debit': cost * base_qty, 
                'credit': 0,
                'description': f'تكلفة مبيعات - {line.item.name}',
                'cost_center': invoice.cost_center
            })
            lines.append({
                'account': line.item.inventory_account, 
                'debit': 0, 
                'credit': cost * base_qty,
                'description': f'صرف مخزون - {line.item.name}',
                'cost_center': invoice.cost_center
            })

        # Group taxes by account using unified tax engine
        tax_account_totals = {}
        for line in invoice.lines.all():
            net_before_tax = Decimal(str(line.quantity * line.unit_price)) * (Decimal('1') - (Decimal(str(line.discount_percent)) / Decimal('100')))
            res = calculate_line_taxes(
                net_before_tax,
                line.tax_type,
                line.tax_percent,
                line.tax_type2,
                line.tax_percent2,
                is_purchase_or_expense=False
            )
            
            for tx_type, tx_val in [(line.tax_type, res['tax1_value']), (line.tax_type2, res['tax2_value'])]:
                if tx_type and tx_val > 0:
                    acc = tx_type.account
                    if acc:
                        if acc.id not in tax_account_totals:
                            tax_account_totals[acc.id] = {'account': acc, 'amount': Decimal('0'), 'category': tx_type.category}
                        tax_account_totals[acc.id]['amount'] += tx_val

        for tax_info in tax_account_totals.values():
            if tax_info['amount'] > 0:
                # In Sales: WHT, Salary tax, and Insurance are usually debits (deductions from the receivable)
                is_debit = (tax_info['category'] in ['wht', 'salary', 'insurance'])
                lines.append({
                    'account': tax_info['account'],
                    'debit': tax_info['amount'] if is_debit else 0,
                    'credit': 0 if is_debit else tax_info['amount'],
                    'description': f"ضريبة {tax_info['account'].name} - فاتورة {invoice.number}",
                    'cost_center': invoice.cost_center
                })

        entry = JournalService.create_entry(
            date_val=invoice.date,
            entry_type=JournalEntry.EntryType.SALE,
            description=f'فاتورة مبيعات رقم {invoice.number}',
            lines=lines,
            source_document=invoice,
            created_by=posted_by,
        )
        
        invoice.journal_entry = entry
        invoice.status = SalesInvoice.Status.POSTED
        invoice.save()


        # 2. Handle Auto-Settlement for Cash Sales
        if invoice.payment_type == SalesInvoice.PaymentType.CASH:
            if not invoice.cash_box:
                # This should have been validated at form level, but extra safety
                raise ValueError("يجب تحديد الخزنة للفواتير النقدية لعمل التسوية الآلية")
            
            # Create a receipt automatically
            receipt = CustomerReceipt.objects.create(
                number=DocumentService.generate_number(CustomerReceipt, 'RCPT'),
                date=invoice.date,
                customer=invoice.customer,
                amount=invoice.total,
                payment_method='cash',
                cash_box=invoice.cash_box,
                reference=f"Settlement for {invoice.number}",
            )
            # Create allocation
            ReceiptAllocation.objects.create(
                receipt=receipt,
                invoice=invoice,
                amount=invoice.total
            )
            # Post the receipt
            SalesService.record_receipt(receipt, posted_by)

        AuditService.log(posted_by, 'Post', invoice, f'ترحيل فاتورة مبيعات رقم {invoice.number}')
        return entry

    @staticmethod
    @transaction.atomic
    def reverse_invoice(invoice: SalesInvoice, reversed_by) -> JournalEntry:
        """
        Reverses a posted invoice by creating a reversal journal entry 
        and restoring inventory stock.
        """
        invoice = SalesInvoice.objects.select_for_update().get(pk=invoice.pk)
        if invoice.status != SalesInvoice.Status.POSTED:
            raise ValueError("يمكن فقط عكس الفواتير المرحلة")
        
        if not invoice.journal_entry:
            raise ValueError("الفاتورة لا تملك قيداً محاسبياً لعكسه")

        if invoice.journal_entry.is_reversed:
            raise ValueError(f"هذه الفاتورة تم عكسها مسبقاً")

        # Handle Receipt Allocations
        allocations = invoice.receiptallocation_set.select_related('receipt').all()
        if allocations.exists():
            if invoice.payment_type == SalesInvoice.PaymentType.CASH:
                for allocation in allocations:
                    receipt = allocation.receipt
                    if receipt.reference and receipt.reference.startswith(f"Settlement for {invoice.number}"):
                        if receipt.journal_entry and not receipt.journal_entry.is_reversed:
                            from django.utils import timezone
                            JournalService.reverse_entry(receipt.journal_entry, timezone.now().date(), reversed_by)
                        receipt.reference = f"{receipt.reference} (ملغي)"
                        receipt.save(update_fields=['reference'])
                        allocation.delete()
                    else:
                        raise ValueError("لا يمكن عكس الفاتورة لأن لها سندات قبض يدوية. يرجى إلغاء سندات القبض أولاً.")
            else:
                raise ValueError("لا يمكن عكس الفاتورة لأن لها سندات قبض مرتبطة بها. يرجى إلغاء سندات القبض أولاً.")

        # 1. Reverse the Journal Entry
        from django.utils import timezone
        reversal_entry = JournalService.reverse_entry(
            invoice.journal_entry, 
            date_val=timezone.now().date(), 
            created_by=reversed_by
        )

        # 2. Update Invoice Status
        invoice.status = SalesInvoice.Status.CANCELLED
        invoice.save()

        # 3. Restore Inventory Stock
        InventoryService.restore_stock(invoice) # Need to ensure this exists

        AuditService.log(reversed_by, 'Reverse', invoice, f'عكس فاتورة مبيعات رقم {invoice.number}')
        return reversal_entry

    @staticmethod
    @transaction.atomic
    def post_return(sales_return, posted_by) -> JournalEntry:
        """
        Sales Return Journal Entry:
        DR  Sales Returns Account           → net_amount
        DR  Tax Payable (Reverse)           → tax_amount
        CR  Customer (Receivable)           → total_amount
        DR  Inventory                       → cost
        CR  Cost of Goods Sold (Reverse)    → cost
        """
        sales_return = SalesReturn.objects.select_for_update().get(pk=sales_return.pk)
        if sales_return.status == 'posted':
            raise ValueError("هذا المرتجع مرحل بالفعل")

        lines = []
        return_lines = list(sales_return.lines.select_related('item', 'tax_type', 'tax_type2', 'return_account', 'cogs_account', 'warehouse').all())
        
        # Determine Cost Center (Project) from the linked sales invoice
        cost_center = sales_return.invoice.cost_center if sales_return.invoice else None
        
        # 1. Always Credit Customer for Sales Returns (to track in AR)
        lines.append({
            'account': sales_return.customer.account,
            'debit': 0,
            'credit': sales_return.total,
            'description': f"مرتجع مبيعات رقم {sales_return.number}",
            'cost_center': cost_center
        })

        # If it's a cash return, also create settlement lines in the same entry
        if sales_return.payment_type == 'cash':
            cash_account = None
            if sales_return.cash_box:
                cash_account = sales_return.cash_box.account
            elif sales_return.invoice and sales_return.invoice.cash_box:
                cash_account = sales_return.invoice.cash_box.account
                
            if cash_account:
                # Debit Customer (giving them cash)
                lines.append({
                    'account': sales_return.customer.account,
                    'debit': sales_return.total,
                    'credit': 0,
                    'description': f"سداد نقدي للمرتجع رقم {sales_return.number}",
                    'cost_center': cost_center
                })
                # Credit Cash Box (money leaving)
                lines.append({
                    'account': cash_account,
                    'debit': 0,
                    'credit': sales_return.total,
                    'description': f"صرف قيمة مرتجع رقم {sales_return.number}",
                    'cost_center': cost_center
                })
            else:
                raise ValueError("لا يمكن تحديد الخزينة لصرف المرتجع النقدي")

        for line in return_lines:
            # Compute net amount before tax (price after discount, before tax)
            gross = line.quantity * line.unit_price
            discount = gross * (line.discount_percent / Decimal('100'))
            net = gross - discount
            
            # Debit: Sales Returns Account
            lines.append({
                'account': line.return_account,
                'debit': net,
                'credit': 0,
                'description': f'مردودات مبيعات - {line.item.name}',
                'cost_center': cost_center
            })
            
            # Inventory reversal entry (✅ Fix #2: استخدام الكمية الأساسية من السطر)
            cost = line.cost # Use stored cost
            if cost <= 0:
                raise ValueError(f"تكلفة المرتجع للصنف {line.item.name} تساوي صفراً، لا يمكن إنشاء قيد المرتجع بدون قيمة التكلفة.")
                
            base_qty = line.base_quantity or line.quantity

            lines.append({
                'account': line.item.inventory_account, 
                'debit': cost * base_qty, 
                'credit': 0,
                'description': f'إعادة للمخزون (مرتجع) - {line.item.name}',
                'cost_center': cost_center
            })
            lines.append({
                'account': line.cogs_account, 
                'debit': 0, 
                'credit': cost * base_qty,
                'description': f'عكس تكلفة مبيعات - {line.item.name}',
                'cost_center': cost_center
            })

        # Group taxes by account using unified tax engine
        tax_account_totals = {}
        for line in return_lines:
            net_before_tax = Decimal(str(line.quantity * line.unit_price)) * (Decimal('1') - (Decimal(str(line.discount_percent)) / Decimal('100')))
            res = calculate_line_taxes(
                net_before_tax,
                line.tax_type,
                line.tax_percent,
                line.tax_type2,
                line.tax_percent2,
                is_purchase_or_expense=False
            )
            
            for tx_type, tx_val in [(line.tax_type, res['tax1_value']), (line.tax_type2, res['tax2_value'])]:
                if tx_type and tx_val > 0:
                    acc = tx_type.account
                    if acc:
                        if acc.id not in tax_account_totals:
                            tax_account_totals[acc.id] = {
                                'account': acc,
                                'amount': Decimal('0'),
                                'category': tx_type.category
                            }
                        tax_account_totals[acc.id]['amount'] += tx_val

        for tax_info in tax_account_totals.values():
            if tax_info['amount'] > 0:
                # In returns, VAT and Table Tax are DEBIT (reverse of credit in sales)
                # WHT, salary, and insurance are CREDIT
                is_debit = (tax_info['category'] not in ['wht', 'salary', 'insurance'])
                lines.append({
                    'account': tax_info['account'],
                    'debit': tax_info['amount'] if is_debit else 0,
                    'credit': 0 if is_debit else tax_info['amount'],
                    'description': f"عكس ضريبة {tax_info['account'].name} (مرتجع)",
                    'cost_center': cost_center
                })

        entry = JournalService.create_entry(
            date_val=sales_return.date,
            entry_type=JournalEntry.EntryType.SALE, # Or specific RETURN type if available
            description=f'مرتجع مبيعات رقم {sales_return.number}',
            lines=lines,
            source_document=sales_return,
            created_by=posted_by,
        )
        
        sales_return.journal_entry = entry
        sales_return.status = 'posted'
        sales_return.save()
        
        # Increase stock
        for line in return_lines:
            base_qty = line.base_quantity or line.quantity
            InventoryService.record_movement(
                date_val=sales_return.date,
                item=line.item,
                warehouse=line.warehouse,
                movement_type=StockMovement.MovementType.SALE_RETURN,
                quantity=base_qty,
                unit_cost=line.cost,
                source=sales_return,
                reference=sales_return.number,
            )

        AuditService.log(posted_by, 'Post', sales_return, f'ترحيل مرتجع مبيعات رقم {sales_return.number}')
        return entry

    @staticmethod
    @transaction.atomic
    def record_receipt(receipt, posted_by) -> JournalEntry:
        """
        Customer Receipt Journal Entry:
        DR  Cash/Bank Account           → receipt.amount
        CR  Customer Receivable         → receipt.amount
        """
        # Validate sum of allocations does not exceed receipt amount
        allocations_total = receipt.receiptallocation_set.aggregate(s=Sum('amount'))['s'] or 0
        if allocations_total > receipt.amount:
            raise ValueError(
                f'مجموع مبالغ التوزيعات ({allocations_total}) يتجاوز مبلغ السند ({receipt.amount})'
            )

        lines = []
        
        # Determine source account (Bank, Cash, Cheque, or Intermediary)
        if receipt.payment_method == 'bank':
            source_account = receipt.bank_account.account
        elif receipt.payment_method == 'cheque':
            # شيكات تحت التحصيل - حساب وسيط 1151
            source_account = Account.objects.get(code=getattr(settings, 'CHEQUES_UNDER_COLLECTION_ACCOUNT', '1151'))
        elif receipt.payment_method == 'intermediary':
            source_account = receipt.intermediary_company.account
        else:
            source_account = receipt.cash_box.account
            
        # Custom description for cash invoices
        is_cash_invoice = bool(receipt.reference and receipt.reference.startswith("Settlement for"))
        debit_desc = f'فاتورة كاش - {receipt.customer.name}' if is_cash_invoice else f'تحصيل من عميل {receipt.customer.name}'
        credit_desc = f'فاتورة كاش رقم {receipt.reference.replace("Settlement for ", "")}' if is_cash_invoice else f'سند قبض رقم {receipt.number}'
        
        # Debit Bank/Cash
        lines.append({
            'account': source_account,
            'debit': receipt.amount,
            'credit': 0,
            'description': debit_desc
        })
        
        # Credit Customer
        lines.append({
            'account': receipt.customer.account,
            'debit': 0,
            'credit': receipt.amount,
            'description': credit_desc
        })
        
        entry = JournalService.create_entry(
            date_val=receipt.date,
            entry_type=JournalEntry.EntryType.RECEIPT,
            description=credit_desc,
            lines=lines,
            source_document=receipt,
            created_by=posted_by,
        )
        
        receipt.journal_entry = entry
        receipt.save()

        # Update paid_amount in related invoices with row lock
        for allocation in receipt.receiptallocation_set.select_related('invoice').all():
            invoice = SalesInvoice.objects.select_for_update().get(pk=allocation.invoice.pk)
            invoice.paid_amount += allocation.amount
            if invoice.paid_amount > invoice.total:
                invoice.paid_amount = invoice.total
            invoice.save(update_fields=['paid_amount'])
        
        AuditService.log(posted_by, 'Record', receipt, f'تسجيل سند قبض رقم {receipt.number}')
        
        return entry

    @staticmethod
    @transaction.atomic
    def collect_cheque(receipt, bank_account, collection_date, created_by) -> JournalEntry:
        """
        Journal Entry for Cheque Collection:
        DR  Bank Account                → receipt.amount
        CR  Cheques Under Collection    → receipt.amount
        """
        receipt = CustomerReceipt.objects.select_for_update().get(pk=receipt.pk)

        if receipt.payment_method != 'cheque':
            raise ValueError("هذا السند ليس شيكاً")

        if receipt.cheque_status == CustomerReceipt.ChequeStatus.COLLECTED:
            raise ValueError("هذا الشيك محصل بالفعل")
        if receipt.cheque_status == CustomerReceipt.ChequeStatus.BOUNCED:
            raise ValueError("هذا الشيك مرتجع ولا يمكن تحصيله")

        collection_account = Account.objects.get(code=getattr(settings, 'CHEQUES_UNDER_COLLECTION_ACCOUNT', '1151'))

        lines = [
            {
                'account': bank_account.account,
                'debit': receipt.amount,
                'credit': 0,
                'description': f'تحصيل شيك رقم {receipt.cheque_number} من عميل {receipt.customer.name}'
            },
            {
                'account': collection_account,
                'debit': 0,
                'credit': receipt.amount,
                'description': f'إقفال شيك رقم {receipt.cheque_number} (تحصيل)'
            }
        ]

        entry = JournalService.create_entry(
            date_val=collection_date,
            entry_type=JournalEntry.EntryType.BANK,
            description=f'تحصيل شيك رقم {receipt.cheque_number}',
            lines=lines,
            source_document=receipt,
            created_by=created_by,
        )

        receipt.cheque_status = CustomerReceipt.ChequeStatus.COLLECTED
        receipt.collected_at = collection_date
        receipt.reference += f" | محصل بتاريخ {collection_date}"
        receipt.save(update_fields=['cheque_status', 'collected_at', 'reference'])

        return entry

    @staticmethod
    @transaction.atomic
    def bounce_cheque(receipt, bounce_date, created_by, penalty_amount=0) -> JournalEntry:
        """
        Reverse Entry for a Bounced Cheque:
        DR  Customer Account                 → receipt.amount
        CR  Cheques Under Collection         → receipt.amount
        (Optional) DR Customer Account       → penalty_amount (غرامة)
        (Optional) CR Penalty Income Account  → penalty_amount
        """
        receipt = CustomerReceipt.objects.select_for_update().get(pk=receipt.pk)

        if receipt.payment_method != 'cheque':
            raise ValueError("هذا السند ليس شيكاً")
        if receipt.cheque_status != CustomerReceipt.ChequeStatus.COLLECTED:
            raise ValueError("هذا الشيك لم يتم تحصيله بعد أو ملغي بالفعل")

        collection_account = Account.objects.get(code=getattr(settings, 'CHEQUES_UNDER_COLLECTION_ACCOUNT', '1151'))

        lines = [
            {
                'account': receipt.customer.account,
                'debit': receipt.amount,
                'credit': 0,
                'description': f'إرجاع شيك رقم {receipt.cheque_number} (مرتجع)'
            },
            {
                'account': collection_account,
                'debit': 0,
                'credit': receipt.amount,
                'description': f'إقفال شيك رقم {receipt.cheque_number} (إرجاع)'
            }
        ]

        if penalty_amount > 0:
            penalty_account = Account.objects.get(code=getattr(settings, 'PENALTY_INCOME_ACCOUNT', '42'))
            lines.append({
                'account': receipt.customer.account,
                'debit': penalty_amount,
                'credit': 0,
                'description': f'غرامة شيك مرتجع رقم {receipt.cheque_number}'
            })
            lines.append({
                'account': penalty_account,
                'debit': 0,
                'credit': penalty_amount,
                'description': f'إيراد غرامة شيك مرتجع رقم {receipt.cheque_number}'
            })

        reversal_entry = JournalService.create_entry(
            date_val=bounce_date,
            entry_type=JournalEntry.EntryType.ADJUSTMENT,
            description=f'إرجاع شيك مرتجع رقم {receipt.cheque_number}',
            lines=lines,
            source_document=receipt,
            created_by=created_by,
        )

        receipt.cheque_status = CustomerReceipt.ChequeStatus.BOUNCED
        receipt.save(update_fields=['cheque_status'])

        for allocation in receipt.receiptallocation_set.select_related('invoice').all():
            invoice = SalesInvoice.objects.select_for_update().get(pk=allocation.invoice.pk)
            invoice.paid_amount -= allocation.amount
            if invoice.paid_amount < 0:
                invoice.paid_amount = 0
            invoice.save(update_fields=['paid_amount'])

        AuditService.log(created_by, 'Bounce', receipt, f'إرجاع شيك مرتجع رقم {receipt.cheque_number}')

        return reversal_entry


class RepSettlementService:

    REP_RECEIVABLE_PARENT = getattr(settings, 'SALES_REP_RECEIVABLE_PARENT', '1141')

    @staticmethod
    @transaction.atomic
    def create_rep_account(rep: 'SalesRepresentative') -> 'Account':
        """
        ينشئ حساب ذمة للمندوب تحت شجرة 1141
        يُستدعى عند إنشاء المندوب لأول مرة
        """
        parent = Account.objects.select_for_update().get(
            code=RepSettlementService.REP_RECEIVABLE_PARENT
        )
        last_code = Account.objects.filter(parent=parent).aggregate(Max('code'))['code__max']
        if last_code:
            try:
                next_seq = int(last_code[len(parent.code):]) + 1
            except (ValueError, TypeError):
                next_seq = Account.objects.filter(parent=parent).count() + 1
        else:
            next_seq = 1
        account = Account.objects.create(
            code=f'{parent.code}{next_seq:03d}',
            name=f'ذمة مندوب — {rep.name}',
            account_type='asset',
            parent=parent,
            is_leaf=True,
        )
        return account

    @staticmethod
    def get_unsettled_invoices(rep: 'SalesRepresentative', date) -> list:
        """
        يجيب الفواتير النقدية للمندوب في يوم معين
        اللي لم تدرج في تسوية مُرحَّلة بعد
        """
        settled_invoice_ids = RepSettlementInvoice.objects.filter(
            settlement__sales_rep=rep,
            settlement__status='posted',
            settlement__date=date,
        ).values_list('invoice_id', flat=True)

        return SalesInvoice.objects.filter(
            sales_rep=rep,
            date=date,
            payment_type=SalesInvoice.PaymentType.CASH,
            status=SalesInvoice.Status.POSTED,
        ).exclude(id__in=settled_invoice_ids)

    @staticmethod
    @transaction.atomic
    def post_settlement(settlement, posted_by) -> 'JournalEntry':
        """
        ترحيل تسوية المندوب.
        """
        settlement = RepDailySettlement.objects.select_for_update().get(pk=settlement.pk)
        if settlement.status == 'posted':
            raise ValueError('هذه التسوية مرحلة مسبقاً')

        rep  = settlement.sales_rep

        # حساب المجاميع
        settlement.calculate_totals()

        # تحديد حساب وجهة الاستلام
        if settlement.to_cash_box:
            dest_account = settlement.to_cash_box.account
        elif settlement.to_bank:
            dest_account = settlement.to_bank.account
        elif settlement.to_wallet:
            dest_account = settlement.to_wallet.account
        else:
            raise ValueError('يجب تحديد الخزنة، البنك أو المحفظة التي استلمت النقدية')

        rep_cashbox_account = rep.cash_box.account
        rep_receivable_account = rep.account  # حساب ذمة المندوب
        
        if not rep_receivable_account:
            raise ValueError(f'المندوب {rep.name} ليس له حساب ذمة — يرجى إنشاء الحساب أولاً')

        lines = []

        # 1. قيد استلام النقدية من خزنة المندوب للخزنة الرئيسية
        if settlement.cash_delivered > 0:
            lines.append({
                'account': dest_account,
                'debit': settlement.cash_delivered,
                'credit': 0,
                'description': f'استلام نقدية من مندوب {rep.name}',
            })

        diff = settlement.total_sales - settlement.cash_delivered

        if diff > 0:
            # المندوب سلم أقل → فرق يُحمَّل على ذمته
            lines.append({
                'account': rep_receivable_account,
                'debit': diff,
                'credit': 0,
                'description': f'فرق ذمة مندوب {rep.name} — تسوية {settlement.number}',
            })
            lines.append({
                'account': rep_cashbox_account,
                'debit': 0,
                'credit': settlement.total_sales,
                'description': f'تسوية خزنة مندوب {rep.name}',
            })

        elif diff < 0:
            # المندوب سلم أكثر → الفرق دائن على ذمته (سيُستكمل لاحقاً)
            lines.append({
                'account': rep_cashbox_account,
                'debit': 0,
                'credit': settlement.total_sales,
                'description': f'تسوية خزنة مندوب {rep.name}',
            })
            lines.append({
                'account': rep_receivable_account,
                'debit': 0,
                'credit': abs(diff),
                'description': f'مبلغ زائد من مندوب {rep.name} — تسوية {settlement.number}',
            })

        else:
            # المندوب سلم بالضبط
            if settlement.total_sales > 0:
                lines.append({
                    'account': rep_cashbox_account,
                    'debit': 0,
                    'credit': settlement.total_sales,
                    'description': f'تسوية خزنة مندوب {rep.name}',
                })

        if not lines:
            raise ValueError("لا توجد مبيعات أو فروقات نقدية لتسويتها في هذا اليوم")

        entry = JournalService.create_entry(
            date_val=settlement.date,
            entry_type=JournalEntry.EntryType.RECEIPT,
            description=f'تسوية مندوب {rep.name} — {settlement.date}',
            lines=lines,
            source_document=settlement,
            created_by=posted_by,
        )

        settlement.difference   = diff
        settlement.journal_entry = entry
        settlement.status        = 'posted'
        settlement.save()

        AuditService.log(
            posted_by, 'Post', settlement,
            f'ترحيل تسوية مندوب {rep.name} بتاريخ {settlement.date}'
        )
        return entry

    @staticmethod
    @transaction.atomic
    def collect_rep_receivable(rep: 'SalesRepresentative', amount, dest_account, date, created_by):
        """
        تحصيل ذمة متراكمة على مندوب (من تسويات سابقة):
        DR  الخزنة الرئيسية / البنك     amount
        CR  ذمة المندوب                 amount
        """
        lines = [
            {
                'account': dest_account,
                'debit': amount,
                'credit': 0,
                'description': f'تحصيل ذمة مندوب {rep.name}',
            },
            {
                'account': rep.account,
                'debit': 0,
                'credit': amount,
                'description': f'سداد ذمة مندوب {rep.name}',
            },
        ]
        return JournalService.create_entry(
            date_val=date,
            entry_type=JournalEntry.EntryType.RECEIPT,
            description=f'تحصيل ذمة مندوب {rep.name}',
            lines=lines,
            created_by=created_by,
        )
