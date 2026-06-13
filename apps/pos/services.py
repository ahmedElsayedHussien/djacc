import logging
from decimal import Decimal
from django.db import models, transaction
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.conf import settings
from apps.core.models import JournalEntry, Account, TaxType, FiscalYear
from apps.core.services import JournalService, DocumentService, AuditService
from apps.inventory.models import Item, StockMovement
from apps.inventory.services import InventoryService
from apps.sales.models import SalesRepresentative, RepDailySettlement, RepSettlementInvoice
from .models import POSSession, POSOrder, POSOrderLine, POSPayment

logger = logging.getLogger(__name__)

class POSCheckoutService:
    @staticmethod
    @transaction.atomic
    def create_order(session, cart_items, payment_method, customer_id=None, is_taxable=True, payment_reference=''):
        """
        Processes checkout for a POS cart:
        1. Creates POSOrder with PAID status.
        2. Creates POSOrderLines.
        3. Records Stock Movements instantly to deduct inventory from station warehouse.
        4. Creates POSPayment.
        5. Adjusts Session Expected Cash if payment is cash.
        """
        session = POSSession.objects.select_for_update().get(pk=session.pk)
        if session.status != POSSession.Status.OPEN:
            raise ValueError("جلسة البيع هذه مغلقة ولا يمكن تسجيل فواتير جديدة عليها.")

        station = session.station
        if payment_method == 'card' and not station.bank_account:
            raise ValueError("نقطة البيع هذه غير مرتبطة بحساب بنكي. لا يمكن الدفع ببطاقة ائتمان.")
        if payment_method == 'wallet' and not station.mobile_wallet:
            raise ValueError("نقطة البيع هذه غير مرتبطة بمحفظة إلكترونية. لا يمكن الدفع بالمحفظة.")

        if not cart_items:
            raise ValueError("سلة المشتريات فارغة.")

        subtotal = Decimal('0')
        tax_amount = Decimal('0')
        grand_total = Decimal('0')
        
        tax_rate = Decimal('0')
        if is_taxable:
            vat_tax = TaxType.objects.filter(category=TaxType.Category.VAT, is_active=True).first()
            if vat_tax:
                tax_rate = Decimal(str(vat_tax.rate)) / Decimal('100')
            else:
                tax_rate = Decimal('0.14')
        
        item_ids = [c.get('id') for c in cart_items]
        items_map = {
            item.id: item for item in Item.objects.filter(id__in=item_ids).select_related(
                'base_unit', 'sales_unit', 'purchase_unit'
            )
        }
        
        lines_data = []
        for c in cart_items:
            item_id = c.get('id')
            qty = Decimal(str(c.get('qty', 0)))
            if qty <= 0:
                raise ValueError("الكمية يجب أن تكون أكبر من الصفر")
            price_exclusive = Decimal(str(c.get('price', 0)))
            unit_type = c.get('unit_type', 'base')
            
            item = items_map.get(item_id)
            if not item:
                raise ValueError(f"الصنف بكود {item_id} غير موجود.")
            
            line_subtotal = qty * price_exclusive
            if tax_rate > 0:
                line_tax = line_subtotal * tax_rate
            else:
                line_tax = Decimal('0')
                
            line_total_with_tax = line_subtotal + line_tax
                
            unit_net_price = line_subtotal / qty if qty > 0 else Decimal('0')
            avg_cost_base = InventoryService.get_item_cost(item, session.station.warehouse)
            
            if unit_type == 'sales' and item.sales_unit:
                current_unit_cost = avg_cost_base * item.conversion_factor
                base_qty = qty * item.conversion_factor
            elif unit_type == 'purchase' and item.purchase_unit:
                current_unit_cost = avg_cost_base * item.purchase_conversion_factor
                base_qty = qty * item.purchase_conversion_factor
            else:
                current_unit_cost = avg_cost_base
                base_qty = qty
            
            if unit_net_price < current_unit_cost:
                if not hasattr(session, '_cost_warnings'):
                    session._cost_warnings = []
                session._cost_warnings.append(
                    f"تحذير: الصنف '{item.name}' تم تسعيره بـ {unit_net_price.quantize(Decimal('0.00'))} "
                    f"بينما تكلفته {current_unit_cost.quantize(Decimal('0.00'))} (بيع بأقل من التكلفة)"
                )
            
            subtotal += line_subtotal
            tax_amount += line_tax
            grand_total += line_total_with_tax
            
            lines_data.append({
                'item': item,
                'qty': qty,
                'base_qty': base_qty,
                'price': price_exclusive,
                'tax_percent': tax_rate * Decimal('100'),
                'total': line_total_with_tax
            })

        now = timezone.now()
        timestamp = int(now.timestamp())
        counter = POSOrder.objects.filter(session=session).count() + 1
        receipt_number = f"POS-{session.id}-{timestamp}-{counter}"

        subtotal = subtotal.quantize(Decimal('0.01'))
        tax_amount = tax_amount.quantize(Decimal('0.01'))
        grand_total = grand_total.quantize(Decimal('0.01'))

        order = POSOrder.objects.create(
            receipt_number=receipt_number,
            session=session,
            customer_id=customer_id,
            subtotal=subtotal,
            tax=tax_amount,
            grand_total=grand_total,
            status=POSOrder.Status.DRAFT
        )

        for line in lines_data:
            item = line['item']
            qty = line['qty']
            base_qty = line['base_qty']
            
            POSOrderLine.objects.create(
                order=order,
                item=item,
                qty=qty,
                price=line['price'],
                tax_percent=line['tax_percent'],
                total=line['total']
            )

            InventoryService.record_movement(
                date_val=timezone.now().date(),
                item=item,
                warehouse=session.station.warehouse,
                movement_type=StockMovement.MovementType.SALES_ISSUE,
                quantity=-base_qty,
                unit_cost=None,
                source=order,
                reference=f'POS Order {receipt_number}'
            )

        order.status = POSOrder.Status.PAID
        order.save(update_fields=['status'])

        POSPayment.objects.create(
            order=order,
            method=payment_method,
            amount=grand_total,
            reference=payment_reference
        )

        if payment_method == 'cash':
            POSSession.objects.filter(pk=session.pk).update(
                expected_cash=models.F('expected_cash') + grand_total
            )

        return order

    @staticmethod
    @transaction.atomic
    def cancel_order(order, cancelled_by):
        """Cancel a paid POS order: reverse stock, void payment, adjust session cash."""
        order = POSOrder.objects.select_for_update().get(pk=order.pk)
        if order.status != POSOrder.Status.PAID:
            raise ValueError("يمكن فقط إلغاء الفواتير المدفوعة.")

        session = POSSession.objects.select_for_update().get(pk=order.session.pk)
        if session.status != POSSession.Status.OPEN:
            raise ValueError("لا يمكن إلغاء فاتورة من وردية مغلقة. استخدم مرتجع مبيعات.")

        pos_ct = ContentType.objects.get_for_model(POSOrder)
        movements = StockMovement.objects.filter(
            content_type=pos_ct, object_id=order.id,
            movement_type=StockMovement.MovementType.SALES_ISSUE
        )
        for mov in movements:
            InventoryService.record_movement(
                date_val=timezone.now().date(),
                item=mov.item,
                warehouse=session.station.warehouse,
                movement_type=StockMovement.MovementType.SALE_RETURN,
                quantity=-mov.quantity,
                unit_cost=mov.unit_cost,
                source=order,
                reference=f'Cancel {order.receipt_number}'
            )

        for payment in order.payments.all():
            if payment.method == 'cash':
                POSSession.objects.filter(pk=session.pk).update(
                    expected_cash=models.F('expected_cash') - payment.amount
                )
            payment.delete()

        order.status = POSOrder.Status.CANCELLED
        order.save(update_fields=['status'])


    @staticmethod
    @transaction.atomic
    def return_items(order, items_data, returned_by):
        """
        Partial return of items from a paid POS order. Creates a Return Order in current session.
        items_data = [{'line_id': 1, 'qty': 2}, ...]
        """
        order = POSOrder.objects.get(pk=order.pk)
        if order.status not in [POSOrder.Status.PAID, POSOrder.Status.POSTED]:
            raise ValueError("يمكن فقط إرجاع أصناف من الفواتير المدفوعة أو المرحّلة.")

        current_session = POSSessionService.get_active_session(returned_by)
        if not current_session:
            raise ValueError("يجب أن يكون لديك وردية مفتوحة لتتمكن من إرجاع فواتير.")

        pos_ct = ContentType.objects.get_for_model(POSOrder)
        total_refund_subtotal = Decimal('0')
        total_refund_tax = Decimal('0')
        total_refund_grand = Decimal('0')

        lines_to_create = []
        stock_moves_to_create = []

        for item_data in items_data:
            line_id = item_data.get('line_id')
            return_qty = Decimal(str(item_data.get('qty', 0)))
            if return_qty <= 0:
                raise ValueError(f"كمية الإرجاع لخط {item_data.get('line_id')} يجب أن تكون أكبر من الصفر")

            try:
                line = POSOrderLine.objects.select_related('item').get(pk=line_id, order=order)
            except POSOrderLine.DoesNotExist:
                raise ValueError(f"السطر {line_id} غير موجود في الفاتورة.")

            if return_qty > line.qty:
                raise ValueError(f"كمية الإرجاع ({return_qty}) أكبر من الكمية الأصلية ({line.qty}) للصنف '{line.item.name}'.")

            movement = StockMovement.objects.filter(
                content_type=pos_ct, object_id=order.id,
                item=line.item, movement_type=StockMovement.MovementType.SALES_ISSUE
            ).first()
            if not movement:
                raise ValueError(f"لا توجد حركة مخزنية للصنف '{line.item.name}' في هذه الفاتورة.")

            base_ratio = abs(movement.quantity) / line.qty if line.qty > 0 else Decimal('1')
            return_base_qty = (return_qty * base_ratio).quantize(Decimal('0.0001'))

            line_unit_price = line.total / line.qty if line.qty > 0 else line.price
            refund_amount = (line_unit_price * return_qty).quantize(Decimal('0.01'))
            
            line_subtotal_ratio = (line.price * line.qty) / line.total if line.total > 0 else Decimal('1')
            line_tax_ratio = (line.tax_percent / Decimal('100'))
            
            # Approximate breakdown for the return order line
            refund_tax = (refund_amount - (refund_amount / (1 + line_tax_ratio))).quantize(Decimal('0.01')) if line.tax_percent > 0 else Decimal('0')
            refund_subtotal = refund_amount - refund_tax

            total_refund_subtotal += refund_subtotal
            total_refund_tax += refund_tax
            total_refund_grand += refund_amount

            lines_to_create.append({
                'item': line.item,
                'qty': return_qty,
                'price': line.price,
                'discount': Decimal('0'),
                'tax_percent': line.tax_percent,
                'total': refund_amount
            })

            stock_moves_to_create.append({
                'item': line.item,
                'quantity': return_base_qty,
                'unit_cost': movement.unit_cost
            })

        if total_refund_grand <= 0:
            return Decimal('0')

        # Create Return Order
        now = timezone.now()
        timestamp = int(now.timestamp())
        counter = POSOrder.objects.filter(session=current_session).count() + 1
        receipt_number = f"RET-{current_session.id}-{timestamp}-{counter}"

        return_order = POSOrder.objects.create(
            receipt_number=receipt_number,
            session=current_session,
            customer=order.customer,
            subtotal=total_refund_subtotal,
            tax=total_refund_tax,
            grand_total=total_refund_grand,
            status=POSOrder.Status.DRAFT,
            is_return=True,
            parent_order=order
        )

        for ld in lines_to_create:
            POSOrderLine.objects.create(
                order=return_order,
                item=ld['item'],
                qty=ld['qty'],
                price=ld['price'],
                discount=ld['discount'],
                tax_percent=ld['tax_percent'],
                total=ld['total']
            )

        return_order.status = POSOrder.Status.PAID
        return_order.save(update_fields=['status'])

        for sm in stock_moves_to_create:
            InventoryService.record_movement(
                date_val=timezone.now().date(),
                item=sm['item'],
                warehouse=current_session.station.warehouse,
                movement_type=StockMovement.MovementType.SALE_RETURN,
                quantity=sm['quantity'],
                unit_cost=sm['unit_cost'],
                source=return_order,
                reference=f'Return for {order.receipt_number}'
            )

        POSPayment.objects.create(
            order=return_order,
            method='cash',
            amount=total_refund_grand,
            reference=f'Refund for {order.receipt_number}'
        )

        POSSession.objects.filter(pk=current_session.pk).update(
            expected_cash=models.F('expected_cash') - total_refund_grand
        )

        return total_refund_grand

class POSSessionService:
    @staticmethod
    def get_active_session(user):
        """Returns the active open session for the user, if any."""
        return POSSession.objects.filter(user=user, status=POSSession.Status.OPEN).first()

    @staticmethod
    @transaction.atomic
    def open_session(user, station, opening_cash):
        """Opens a new POSSession for the user at a specified station."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.select_for_update().get(pk=user.pk)
        
        active = POSSession.objects.filter(
            user=user, status=POSSession.Status.OPEN
        ).select_for_update().first()
        if active:
            raise ValueError(f"لديك بالفعل جلسة مفتوحة بنقطة البيع: {active.station.name}")
            
        session = POSSession.objects.create(
            station=station,
            user=user,
            opening_cash=Decimal(str(opening_cash)),
            expected_cash=Decimal(str(opening_cash)),
            status=POSSession.Status.OPEN
        )
        return session

    @staticmethod
    @transaction.atomic
    def close_session(session, actual_cash, notes=''):
        """
        Closes a POSSession:
        1. Compares expected cash with actual cash, calculating discrepancy.
        2. Changes status to CLOSED.
        3. Creates a single consolidated Journal Entry for all shift transactions to limit database strain.
        4. If the cashier is a Sales Representative, automatically triggers a RepDailySettlement.
        """
        session = POSSession.objects.select_for_update().get(pk=session.pk)
        if session.status != POSSession.Status.OPEN:
            raise ValueError("هذه الجلسة مغلقة بالفعل.")
        if session.settlement_id:
            raise ValueError("هذه الجلسة تم تسويتها بالفعل في الـ ERP ولا يمكن إغلاقها مرة أخرى.")

        actual = Decimal(str(actual_cash))
        expected = session.expected_cash
        difference = actual - expected

        session.actual_cash = actual
        session.difference = difference
        session.end_time = timezone.now()
        session.status = POSSession.Status.CLOSED
        session.save()

        # Create combined Journal Entry
        POSSessionService.create_combined_journal_entry(session, notes)

        # Trigger RepDailySettlement if user has a Sales Representative profile
        rep = SalesRepresentative.objects.filter(user=session.user).first()
        if rep:

            settlement = RepDailySettlement.objects.create(
                number=DocumentService.generate_number(RepDailySettlement, 'RS'),
                date=timezone.now().date(),
                sales_rep=rep,
                total_sales=session.expected_cash,
                cash_delivered=actual,
                difference=-difference, # negative of difference (shortage is positive in RepDailySettlement difference field)
                to_cash_box=session.station.cash_box,
                notes=f"تسوية آلية لوردية الـ POS رقم {session.id}. {notes}",
                status=RepDailySettlement.Status.DRAFT,
                created_by=session.user
            )
            session.settlement = settlement
            session.save(update_fields=['settlement'])

        return session

    @staticmethod
    @transaction.atomic
    def collect_shortage(session, collected_by, settlement_method='cash'):
        """
        تحصيل العجز النقدي من الكاشير بعد غلق الوردية.
        """
        session = POSSession.objects.select_for_update().get(pk=session.pk)
        if session.status not in (POSSession.Status.CLOSED, POSSession.Status.POSTED):
            raise ValueError("يمكن تحصيل العجز فقط للورديات المغلقة.")
        if session.difference >= 0:
            raise ValueError("لا يوجد عجز في هذه الوردية لتحصيله.")
        if session.shortage_collected_at:
            raise ValueError("تم تحصيل عجز هذه الوردية مسبقاً.")

        shortage = abs(session.difference)
        
        shortage_acc_code = getattr(settings, 'CASH_SHORTAGE_ACCOUNT', '544')
        shortage_acc = Account.objects.filter(code=shortage_acc_code).first()
        if not shortage_acc:
            raise ValueError(f"حساب عجز الخزينة (رمز {shortage_acc_code}) غير موجود في شجرة الحسابات.")

        if settlement_method == 'salary_deduction':
            from apps.hr.models import Employee, Loan
            
            employee = Employee.objects.filter(user=session.user).first()
            if not employee:
                raise ValueError("لا يوجد ملف موظف (HR) مرتبط بهذا الكاشير لخصم العجز منه.")
                
            advances_acc_code = getattr(settings, 'EMPLOYEE_LOAN_ACCOUNT', '114')
            debit_account = Account.objects.filter(code=advances_acc_code).first()
            if not debit_account:
                raise ValueError(f"حساب سلف العاملين (رمز {advances_acc_code}) غير موجود في شجرة الحسابات.")
                
            entry = JournalService.create_entry(
                date_val=timezone.now().date(),
                entry_type=JournalEntry.EntryType.JOURNAL,
                description=f"تسوية عجز وردية POS رقم {session.id} بالخصم من راتب {session.user.username}",
                lines=[
                    {
                        'account': debit_account,
                        'debit': shortage,
                        'credit': Decimal('0'),
                        'description': f"سلفة/عجز على كاشير {session.user.username}",
                    },
                    {
                        'account': shortage_acc,
                        'debit': Decimal('0'),
                        'credit': shortage,
                        'description': f"عكس مصروف عجز خزينة وردية POS رقم {session.id}",
                    },
                ],
                source_document=session,
                created_by=collected_by,
            )
            
            # Create Loan record
            Loan.objects.create(
                employee=employee,
                amount=shortage,
                installments_count=1,
                monthly_installment=shortage,
                start_month=timezone.now().date(),
                reason=f"تسوية آلية لعجز وردية نقاط البيع رقم {session.id}",
                status=Loan.Status.APPROVED
            )
            
            AuditService.log(
                user=collected_by,
                action='COLLECT_SHORTAGE',
                obj=session,
                notes=f"تسوية عجز وردية #{session.id} بالخصم من الراتب (سلفة) بقيمة {shortage} — قيد رقم {entry.id}",
            )
            
        else:
            # Default cash settlement
            rep = SalesRepresentative.objects.filter(user=session.user).first()
            cashbox_account = None
            if rep and rep.cash_box and rep.cash_box.account:
                cashbox_account = rep.cash_box.account
            elif session.station.cash_box and session.station.cash_box.account:
                cashbox_account = session.station.cash_box.account

            if not cashbox_account:
                raise ValueError("لا يوجد حساب خزينة مرتبط بهذه الوردية.")

            entry = JournalService.create_entry(
                date_val=timezone.now().date(),
                entry_type=JournalEntry.EntryType.RECEIPT,
                description=f"تحصيل عجز خزينة وردية POS رقم {session.id} — كاشير {session.user.username}",
                lines=[
                    {
                        'account': cashbox_account,
                        'debit': shortage,
                        'credit': Decimal('0'),
                        'description': f"تحصيل عجز من كاشير {session.user.username}",
                    },
                    {
                        'account': shortage_acc,
                        'debit': Decimal('0'),
                        'credit': shortage,
                        'description': f"عكس مصروف عجز خزينة وردية POS رقم {session.id}",
                    },
                ],
                source_document=session,
                created_by=collected_by,
            )

            AuditService.log(
                user=collected_by,
                action='COLLECT_SHORTAGE',
                obj=session,
                notes=f"تحصيل عجز وردية #{session.id} نقداً بقيمة {shortage} — قيد رقم {entry.id}",
            )

        session.shortage_collected_at = timezone.now()
        session.save(update_fields=['shortage_collected_at'])

        return entry

    @staticmethod
    def create_combined_journal_entry(session, notes=''):
        """
        Consolidates all session transactions into one combined Journal Entry:
        DR Cash Box (for Cash Payments)
        DR Bank/Visa Account (for Card Payments)
        DR Cost of Goods Sold (COGS)
        CR Sales Revenue
        CR Inventory Account
        CR VAT Tax Payable (Output VAT)
        """
        orders = POSOrder.objects.filter(session=session, status=POSOrder.Status.PAID)
        if not orders.exists():
            return None

        journal_lines = []

        total_cash = Decimal('0')
        total_card = Decimal('0')
        total_wallet = Decimal('0')
        total_tax = Decimal('0')

        total_refund_cash = Decimal('0')
        total_refund_card = Decimal('0')
        total_refund_wallet = Decimal('0')

        payments = POSPayment.objects.filter(order__in=orders)
        for p in payments:
            if p.order.is_return:
                if p.method == 'cash':
                    total_refund_cash += p.amount
                elif p.method == 'card':
                    total_refund_card += p.amount
                elif p.method == 'wallet':
                    total_refund_wallet += p.amount
            else:
                if p.method == 'cash':
                    total_cash += p.amount
                elif p.method == 'card':
                    total_card += p.amount
                elif p.method == 'wallet':
                    total_wallet += p.amount

        total_tax = sum((o.tax if not o.is_return else -o.tax) for o in orders)

        cogs_by_account = {}
        inventory_by_account = {}
        revenue_by_account = {}

        pos_order_ct = ContentType.objects.get_for_model(POSOrder)
        order_ids = list(orders.values_list('id', flat=True))

        # SALES_ISSUE increases COGS/Inventory
        movements = StockMovement.objects.filter(
            content_type=pos_order_ct,
            object_id__in=order_ids,
            movement_type=StockMovement.MovementType.SALES_ISSUE
        ).select_related('item__cogs_account', 'item__inventory_account')

        for mov in movements:
            item = mov.item
            cost_val = abs(mov.total_cost)

            cogs_acc = item.cogs_account
            cogs_by_account[cogs_acc.id] = cogs_by_account.get(cogs_acc.id, (cogs_acc, Decimal('0')))
            cogs_by_account[cogs_acc.id] = (cogs_acc, cogs_by_account[cogs_acc.id][1] + cost_val)

            inv_acc = item.inventory_account
            inventory_by_account[inv_acc.id] = inventory_by_account.get(inv_acc.id, (inv_acc, Decimal('0')))
            inventory_by_account[inv_acc.id] = (inv_acc, inventory_by_account[inv_acc.id][1] + cost_val)

        # SALE_RETURN decreases COGS/Inventory
        return_movements = StockMovement.objects.filter(
            content_type=pos_order_ct,
            object_id__in=order_ids,
            movement_type=StockMovement.MovementType.SALE_RETURN
        ).select_related('item__cogs_account', 'item__inventory_account')

        for mov in return_movements:
            item = mov.item
            cost_val = abs(mov.total_cost)

            cogs_acc = item.cogs_account
            cogs_by_account[cogs_acc.id] = cogs_by_account.get(cogs_acc.id, (cogs_acc, Decimal('0')))
            cogs_by_account[cogs_acc.id] = (cogs_acc, cogs_by_account[cogs_acc.id][1] - cost_val)

            inv_acc = item.inventory_account
            inventory_by_account[inv_acc.id] = inventory_by_account.get(inv_acc.id, (inv_acc, Decimal('0')))
            inventory_by_account[inv_acc.id] = (inv_acc, inventory_by_account[inv_acc.id][1] - cost_val)

        lines_with_items = POSOrderLine.objects.filter(
            order__in=orders
        ).select_related('item__sales_account', 'order')

        for line in lines_with_items:
            item = line.item
            order = line.order
            if order.grand_total > 0:
                line_net = (line.total / order.grand_total) * order.subtotal
            else:
                line_net = Decimal('0')
                
            if order.is_return:
                line_net = -line_net

            sales_acc = item.sales_account
            if not sales_acc:
                sales_acc = Account.objects.filter(account_type='revenue', is_leaf=True).order_by('code').first()

            if sales_acc:
                revenue_by_account[sales_acc.id] = revenue_by_account.get(sales_acc.id, (sales_acc, Decimal('0')))
                revenue_by_account[sales_acc.id] = (sales_acc, revenue_by_account[sales_acc.id][1] + line_net)

        # Get VAT Output Account
        vat_tax = TaxType.objects.filter(category=TaxType.Category.VAT).first()
        vat_account = vat_tax.account if vat_tax else None
        if not vat_account:
            # Fallback to standard Output VAT account
            vat_account = Account.objects.filter(code='21211').first()

        # Build Journal Entry Lines
        # Determine the correct cashbox account (prioritize Rep's cashbox over Station's default)
        rep = SalesRepresentative.objects.filter(user=session.user).first()
        cashbox_account = None
        if rep and rep.cash_box and rep.cash_box.account:
            cashbox_account = rep.cash_box.account
        elif session.station.cash_box and session.station.cash_box.account:
            cashbox_account = session.station.cash_box.account

        # 1. Debit/Credit Cash Box
        net_cash = total_cash - total_refund_cash
        if net_cash > 0 and cashbox_account:
            journal_lines.append({
                'account': cashbox_account,
                'debit': net_cash,
                'credit': Decimal('0'),
                'description': f"إجمالي المقبوضات النقدية للوردية رقم {session.id}"
            })
        elif net_cash < 0 and cashbox_account:
            journal_lines.append({
                'account': cashbox_account,
                'debit': Decimal('0'),
                'credit': abs(net_cash),
                'description': f"إجمالي مدفوعات نقدية لمرتجعات للوردية رقم {session.id}"
            })

        # 2. Debit Bank Account (Total Card Received)
        net_card = total_card - total_refund_card
        if net_card > 0 and session.station.bank_account and session.station.bank_account.account:
            journal_lines.append({
                'account': session.station.bank_account.account,
                'debit': net_card,
                'credit': Decimal('0'),
                'description': f"إجمالي مقبوضات الشبكة للوردية رقم {session.id}"
            })
        elif net_card < 0 and session.station.bank_account and session.station.bank_account.account:
            journal_lines.append({
                'account': session.station.bank_account.account,
                'debit': Decimal('0'),
                'credit': abs(net_card),
                'description': f"إجمالي مدفوعات الشبكة لمرتجعات للوردية رقم {session.id}"
            })

        # 2.5. Debit Mobile Wallet (Total Wallet Received)
        net_wallet = total_wallet - total_refund_wallet
        if net_wallet != 0:
            wallet_account = None
            if getattr(session.station, 'mobile_wallet', None) and session.station.mobile_wallet.account:
                wallet_account = session.station.mobile_wallet.account
            elif session.station.cash_box and session.station.cash_box.account:
                wallet_account = session.station.cash_box.account
                
            if wallet_account:
                if net_wallet > 0:
                    journal_lines.append({
                        'account': wallet_account,
                        'debit': net_wallet,
                        'credit': Decimal('0'),
                        'description': f"إجمالي مقبوضات المحفظة الإلكترونية للوردية رقم {session.id}"
                    })
                elif net_wallet < 0:
                    journal_lines.append({
                        'account': wallet_account,
                        'debit': Decimal('0'),
                        'credit': abs(net_wallet),
                        'description': f"إجمالي مدفوعات المحفظة الإلكترونية لمرتجعات للوردية رقم {session.id}"
                    })

        # 2.75. Cash Shortage / Excess Adjustment
        diff_amount = getattr(session, 'difference', Decimal('0'))
        if diff_amount < 0:
            shortage = abs(diff_amount)
            shortage_acc_code = getattr(settings, 'CASH_SHORTAGE_ACCOUNT', '544')
            shortage_acc = Account.objects.filter(code=shortage_acc_code).first()
            if shortage_acc and cashbox_account and shortage > 0:
                journal_lines.append({
                    'account': shortage_acc,
                    'debit': shortage,
                    'credit': Decimal('0'),
                    'description': f"عجز خزينة وردية POS رقم {session.id}"
                })
                journal_lines.append({
                    'account': cashbox_account,
                    'debit': Decimal('0'),
                    'credit': shortage,
                    'description': f"تسوية عجز خزينة وردية POS رقم {session.id}"
                })
        elif diff_amount > 0:
            excess = diff_amount
            excess_acc_code = getattr(settings, 'CASH_EXCESS_ACCOUNT', '425')
            excess_acc = Account.objects.filter(code=excess_acc_code).first()
            if excess_acc and cashbox_account and excess > 0:
                journal_lines.append({
                    'account': cashbox_account,
                    'debit': excess,
                    'credit': Decimal('0'),
                    'description': f"زيادة خزينة وردية POS رقم {session.id}"
                })
                journal_lines.append({
                    'account': excess_acc,
                    'debit': Decimal('0'),
                    'credit': excess,
                    'description': f"تسوية زيادة خزينة وردية POS رقم {session.id}"
                })

        # 3. Debit/Credit COGS Accounts
        for acc_id, (acc, amount) in cogs_by_account.items():
            if amount > 0:
                journal_lines.append({
                    'account': acc,
                    'debit': amount,
                    'credit': Decimal('0'),
                    'description': f"تكلفة المبيعات المجمعة للوردية رقم {session.id}"
                })
            elif amount < 0:
                journal_lines.append({
                    'account': acc,
                    'debit': Decimal('0'),
                    'credit': abs(amount),
                    'description': f"تخفيض تكلفة المبيعات للمرتجعات للوردية رقم {session.id}"
                })

        # 4. Credit/Debit Sales Revenue Accounts
        for acc_id, (acc, amount) in revenue_by_account.items():
            if amount > 0:
                journal_lines.append({
                    'account': acc,
                    'debit': Decimal('0'),
                    'credit': amount,
                    'description': f"إيراد المبيعات المجمع للوردية رقم {session.id}"
                })
            elif amount < 0:
                journal_lines.append({
                    'account': acc,
                    'debit': abs(amount),
                    'credit': Decimal('0'),
                    'description': f"تخفيض إيراد المبيعات للمرتجعات للوردية رقم {session.id}"
                })

        # 5. Credit/Debit Inventory Accounts
        for acc_id, (acc, amount) in inventory_by_account.items():
            if amount > 0:
                journal_lines.append({
                    'account': acc,
                    'debit': Decimal('0'),
                    'credit': amount,
                    'description': f"صرف مخزون مجمع للوردية رقم {session.id}"
                })
            elif amount < 0:
                journal_lines.append({
                    'account': acc,
                    'debit': abs(amount),
                    'credit': Decimal('0'),
                    'description': f"إضافة مخزون مرتجعات للوردية رقم {session.id}"
                })

        # 6. Credit/Debit Output VAT
        if total_tax > 0 and vat_account:
            journal_lines.append({
                'account': vat_account,
                'debit': Decimal('0'),
                'credit': total_tax,
                'description': f"ضريبة القيمة المضافة المخرجة لوردية POS رقم {session.id}"
            })
        elif total_tax < 0 and vat_account:
            journal_lines.append({
                'account': vat_account,
                'debit': abs(total_tax),
                'credit': Decimal('0'),
                'description': f"تخفيض ضريبة القيمة المضافة لمرتجعات POS رقم {session.id}"
            })

        fy = FiscalYear.objects.select_for_update(skip_locked=True).filter(is_closed=False).first()
        if not fy:
            today = timezone.now().date()
            fy, created = FiscalYear.objects.get_or_create(
                name=f"FY {today.year}",
                defaults={
                    'start_date': today.replace(month=1, day=1),
                    'end_date': today.replace(month=12, day=31),
                    'is_closed': False
                }
            )
            if created:
                fy = FiscalYear.objects.select_for_update().get(pk=fy.pk)

        # Verify entry balances perfectly before submitting
        debit_sum = sum(x['debit'] for x in journal_lines)
        credit_sum = sum(x['credit'] for x in journal_lines)
        
        # Prevent any fractional rounding issues from causing transaction reject
        diff = debit_sum - credit_sum
        if abs(diff) > 0 and abs(diff) < Decimal('0.05'):
            # Round off the diff to the biggest cash or revenue line
            for line in journal_lines:
                if line['debit'] > 0:
                    line['debit'] -= diff
                    break

        if journal_lines:
            entry = JournalService.create_entry(
                date_val=timezone.now().date(),
                entry_type=JournalEntry.EntryType.SALE,
                description=f"قيد المبيعات اليومي المجمع لوردية نقطة البيع رقم {session.id}",
                lines=journal_lines,
                source_document=session,
                created_by=session.user
            )
            # Mark all orders in the session as POSTED now that financial entry is done
            orders.update(status=POSOrder.Status.POSTED)
            return entry

        return None
