from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from .models import Item, Warehouse, StockMovement, ItemLedger, LoadingOrder, LoadingOrderLine
from apps.core.services import AuditService

class InventoryService:
    @staticmethod
    def generate_item_code():
        from .models import Item
        codes = Item.objects.values_list('code', flat=True)
        numeric_codes = []
        for code in codes:
            if code and str(code).isdigit():
                numeric_codes.append(int(code))
        
        next_num = max(numeric_codes) + 1 if numeric_codes else 1
        while Item.objects.filter(code=str(next_num)).exists():
            next_num += 1
        return str(next_num)

    @staticmethod
    def generate_unit_code():
        from .models import UnitOfMeasure
        codes = UnitOfMeasure.objects.values_list('code', flat=True)
        numeric_codes = []
        for code in codes:
            if code and code.isdigit():
                numeric_codes.append(int(code))
        
        if numeric_codes:
            return str(max(numeric_codes) + 1)
        return "1"

    @staticmethod
    def generate_category_code():
        from .models import ItemCategory
        # Find all categories with numeric codes
        codes = ItemCategory.objects.values_list('code', flat=True)
        numeric_codes = []
        for code in codes:
            if code and code.isdigit():
                numeric_codes.append(int(code))
        
        if numeric_codes:
            return str(max(numeric_codes) + 1)
        return "1"

    @staticmethod
    def get_item_cost(item: Item, warehouse: Warehouse) -> Decimal:
        """
        Returns the current average cost of an item in a warehouse.
        """
        try:
            ledger = ItemLedger.objects.get(item=item, warehouse=warehouse)
            return ledger.average_cost
        except ItemLedger.DoesNotExist:
            return Decimal('0')

    @staticmethod
    @transaction.atomic
    def record_movement(
        date_val, 
        item, 
        warehouse, 
        movement_type, 
        quantity, 
        unit_cost, 
        source=None, 
        reference=''
    ) -> StockMovement:
        """
        Central method to record stock movements and update ledger.
        """
        if quantity == 0:
            raise ValueError("لا يمكن تسجيل حركة مخزنية بكمية صفرية") # ✅ Fix: منع الحركات الصفرية برفع خطأ بدلاً من إرجاع None
        # Get or create ledger with lock
        ledger, created = ItemLedger.objects.select_for_update().get_or_create(
            item=item, 
            warehouse=warehouse,
            defaults={'quantity_on_hand': 0, 'total_value': 0}
        )
        
        # ✅ Fix #4: إذا لم يتم تمرير تكلفة (في حالة الصرف)، نستخدم التكلفة الحالية من الـ ledger بعد القفل
        if unit_cost is None:
            unit_cost = ledger.average_cost
            
        total_cost = quantity * unit_cost
        
        # Update ledger
        new_quantity = ledger.quantity_on_hand + quantity

        
        if new_quantity < 0:
            from django.conf import settings
            allow_negative = getattr(settings, 'ALLOW_NEGATIVE_STOCK', False)
            if not allow_negative:
                raise ValueError(
                    f'المخزون غير كافي - الصنف: {item.name} | المستودع: {warehouse.name} | '
                    f'المتاح: {ledger.quantity_on_hand} | المطلوب: {abs(quantity)}'
                )
        
        ledger.quantity_on_hand = new_quantity
        ledger.total_value += total_cost
        
        # Prevent residual value when stock is zero
        if ledger.quantity_on_hand == 0:
            ledger.total_value = Decimal('0')

        ledger.save()
        
        # Create movement record
        movement = StockMovement.objects.create(
            date=date_val,
            item=item,
            warehouse=warehouse,
            movement_type=movement_type,
            quantity=quantity,
            unit_cost=unit_cost,
            total_cost=total_cost,
            reference=reference,
            source=source,
            running_quantity=ledger.quantity_on_hand,
            running_value=ledger.total_value
        )
        
        return movement

    @staticmethod
    @transaction.atomic
    def recalculate_item_ledger(item, warehouse):
        """
        ✅ Fix #3: إعادة حساب أرصدة الـ Ledger وكافة الـ Running Balances في جدول الحركات 
        في حالة إضافة حركات تاريخية أو حدوث خلل في الأرقام.
        """
        movements = StockMovement.objects.filter(
            item=item, 
            warehouse=warehouse
        ).order_by('date', 'id').select_for_update()
        
        current_qty = Decimal('0')
        current_val = Decimal('0')
        
        for mov in movements:
            current_qty += mov.quantity
            current_val += mov.total_cost
            
            # تحديث الحركة نفسها
            mov.running_quantity = current_qty
            mov.running_value = current_val
            mov.save(update_fields=['running_quantity', 'running_value'])
            
        # تحديث سجل الأستاذ المساعد (Ledger)
        ledger, _ = ItemLedger.objects.select_for_update().get_or_create(item=item, warehouse=warehouse)
        ledger.quantity_on_hand = current_qty
        ledger.total_value = current_val
        
        # تصفير القيمة إذا كان المخزون صفر
        if ledger.quantity_on_hand == 0:
            ledger.total_value = Decimal('0')
            
        ledger.save()
        return current_qty


    @staticmethod
    @transaction.atomic
    def reduce_stock(invoice) -> dict:
        """
        Reduces stock based on sales invoice lines.
        ✅ Fix #4 & #2: يتم جلب التكلفة داخل record_movement ويرجع القاموس بالنتائج لتوحيدها مع القيد.
        """
        line_costs = {}
        for line in invoice.lines.all():
            # Convert quantity to base unit if unit is specified
            base_qty = line.quantity
            if hasattr(line, 'unit') and line.unit:
                base_qty = line.item.convert_to_base(line.quantity, line.unit)

            movement = InventoryService.record_movement(
                date_val=invoice.date,
                item=line.item,
                warehouse=line.warehouse,
                movement_type=StockMovement.MovementType.SALES_ISSUE,
                quantity=-base_qty,  # Negative for reduction
                unit_cost=None,      # سيتم حسابه تلقائياً بعد القفل لضمان الدقة
                source=invoice,
                reference=f'Invoice {invoice.number}'
            )
            line_costs[line.id] = movement.unit_cost
            
            # تحديث التكلفة في السطر لضمان بقائها كمرجع
            line.cost = movement.unit_cost
            line.save(update_fields=['cost'])
            
        return line_costs

    @staticmethod
    @transaction.atomic
    def restore_stock(invoice) -> None:
        """
        Restores stock when a sales invoice is reversed/cancelled.
        ✅ Fix #1: إعادة الكميات للمخازن بناءً على الفاتورة المعكوسة.
        """
        for line in invoice.lines.all():
            base_qty = getattr(line, 'base_quantity', line.quantity)
            if not hasattr(line, 'base_quantity') and hasattr(line, 'unit') and line.unit:
                base_qty = line.item.convert_to_base(line.quantity, line.unit)

            InventoryService.record_movement(
                date_val=timezone.now().date(),
                item=line.item,
                warehouse=line.warehouse,
                movement_type=StockMovement.MovementType.SALES_RETURN, # استخدام نوع حركة مرتجع/إعادة
                quantity=base_qty,  # Positive for restoration
                unit_cost=line.cost, # استخدام نفس التكلفة التي خصمت
                source=invoice,
                reference=f'Reversal of {invoice.number}'
            )


    @staticmethod
    @transaction.atomic
    def increase_stock(invoice) -> None:
        """
        Increases stock based on purchase invoice lines.
        ✅ Fix #2 & #3: تحويل سعر الوحدة لوحدة الأساس (Piece) ليتناسب مع الكمية المحولة.
        """
        for line in invoice.lines.all():
            # Convert quantity to base unit if unit is specified
            base_qty = getattr(line, 'base_quantity', line.quantity)
            if not base_qty and hasattr(line, 'unit') and line.unit:
                base_qty = line.item.convert_to_base(line.quantity, line.unit)
            elif not base_qty:
                base_qty = line.quantity

            # سعر وحدة الأساس = سعر وحدة الشراء / معامل التحويل
            # نستخدم purchase_conversion_factor حصرياً للمشتريات
            conversion = Decimal('1')
            if hasattr(line, 'unit') and line.unit and line.unit == line.item.purchase_unit:
                conversion = line.item.purchase_conversion_factor or Decimal('1')
            
            unit_cost_base = line.unit_cost / conversion

            InventoryService.record_movement(
                date_val=invoice.date,
                item=line.item,
                warehouse=line.warehouse,
                movement_type=StockMovement.MovementType.PURCHASE_RECEIPT,
                quantity=base_qty,
                unit_cost=unit_cost_base,
                source=invoice,
                reference=f'Purchase {invoice.number}'
            )

    @staticmethod
    @transaction.atomic
    def process_transfer(transfer, processed_by) -> None:
        """
        Records two stock movements for each line:
        1. Out from source warehouse
        2. In to destination warehouse
        """
        if transfer.status == 'posted':
            raise ValueError("هذا التحويل مرحّل بالفعل")

        if transfer.from_warehouse == transfer.to_warehouse:
            raise ValueError("لا يمكن التحويل لنفس المستودع. يرجى اختيار مستودعين مختلفين.")

        if not transfer.lines.exists():
            raise ValueError("لا يمكن ترحيل طلب تحويل بدون أصناف.")

        journal_lines = []
        
        for line in transfer.lines.all():
            # 1. Outgoing from source
            out_movement = InventoryService.record_movement(
                date_val=transfer.date,
                item=line.item,
                warehouse=transfer.from_warehouse,
                movement_type=StockMovement.MovementType.TRANSFER_OUT,
                quantity=-line.quantity,
                unit_cost=None, # auto-calculate cost
                source=transfer,
                reference=f'Transfer {transfer.number}'
            )
            
            cost = out_movement.unit_cost
            line.unit_cost = cost
            line.save(update_fields=['unit_cost'])
            
            line_total_val = line.quantity * cost

            # 2. Incoming to destination
            InventoryService.record_movement(
                date_val=transfer.date,
                item=line.item,
                warehouse=transfer.to_warehouse,
                movement_type=StockMovement.MovementType.TRANSFER_IN,
                quantity=line.quantity,
                unit_cost=cost,
                source=transfer,
                reference=f'Transfer {transfer.number}'
            )

            # 3. Prepare GL Entry lines if accounts differ
            acc_from = transfer.from_warehouse.gl_account or line.item.inventory_account
            acc_to = transfer.to_warehouse.gl_account or line.item.inventory_account
            
            if acc_from != acc_to:
                journal_lines.append({
                    'account': acc_to, 'debit': line_total_val, 'credit': 0, 
                    'description': f'تحويل وارد - {line.item.name} ({transfer.number})'
                })
                journal_lines.append({
                    'account': acc_from, 'debit': 0, 'credit': line_total_val, 
                    'description': f'تحويل صادر - {line.item.name} ({transfer.number})'
                })
        
        # 4. Create GL Entry if needed
        if journal_lines:
            from apps.core.services import JournalService
            from apps.core.models import JournalEntry
            JournalService.create_entry(
                date_val=transfer.date,
                entry_type=JournalEntry.EntryType.INVENTORY,
                description=f'تحويل مخزني رقم {transfer.number}',
                lines=journal_lines,
                created_by=processed_by
            )
        
        transfer.status = 'posted'
        transfer.save()

        AuditService.log(processed_by, 'Post', transfer, f'ترحيل تحويل مخزني رقم {transfer.number}')


    @staticmethod
    @transaction.atomic
    def reverse_transfer(transfer, reversed_by) -> None:
        """
        عكس تحويل مخزني (إنشاء حركات عكسية)
        """
        if transfer.status != 'posted':
            raise ValueError("يمكن عكس التحويلات المرحلة فقط")

        for line in transfer.lines.all():
            # 1. Reverse outgoing (was negative, now positive into from_warehouse)
            InventoryService.record_movement(
                date_val=timezone.now().date(),
                item=line.item,
                warehouse=transfer.from_warehouse,
                movement_type=StockMovement.MovementType.TRANSFER_IN,
                quantity=line.quantity,
                unit_cost=line.unit_cost, # استخدام التكلفة الأصلية المخزنة في السطر
                source=transfer,
                reference=f'Reversal of {transfer.number}'
            )

            # 2. Reverse incoming (was positive, now negative out of to_warehouse)
            InventoryService.record_movement(
                date_val=timezone.now().date(),
                item=line.item,
                warehouse=transfer.to_warehouse,
                movement_type=StockMovement.MovementType.TRANSFER_OUT,
                quantity=-line.quantity,
                unit_cost=line.unit_cost, # استخدام التكلفة الأصلية المخزنة في السطر
                source=transfer,
                reference=f'Reversal of {transfer.number}'
            )

        # 3. GL Entry Reversal
        from apps.core.models import JournalEntry
        entries = JournalEntry.objects.filter(
            description__contains=f'تحويل مخزني رقم {transfer.number}',
            entry_type=JournalEntry.EntryType.INVENTORY
        )
        from apps.core.services import JournalService
        for entry in entries:
            JournalService.reverse_entry(entry, timezone.now().date(), reversed_by)

        transfer.status = 'cancelled'
        transfer.save()

        AuditService.log(reversed_by, 'Reverse', transfer, f'عكس تحويل مخزني رقم {transfer.number}')


class LoadingService:
    @staticmethod
    @transaction.atomic
    def approve_loading(order, approved_by):
        """اعتماد طلب التحميل وتثبيت الكميات المعتمدة"""
        if order.status != LoadingOrder.Status.PENDING:
            raise ValueError("يمكن فقط اعتماد الطلبات التي في حالة 'في انتظار الاعتماد'")
            
        for line in order.lines.all():
            if line.approved_qty is None:
                line.approved_qty = line.requested_qty
            line.save()
            
        order.status = LoadingOrder.Status.APPROVED
        order.approved_by = approved_by
        order.approved_at = timezone.now()
        order.save()
        
        AuditService.log(approved_by, 'Approve', order, f'اعتماد طلب تحميل رقم {order.number}')
        return order

    @staticmethod
    @transaction.atomic
    def issue_loading(order, issued_by):
        """تنفيذ الصرف الفعلي - تحويل المخزون من الرئيسي لمخزن المندوب"""
        if order.status != LoadingOrder.Status.APPROVED:
            raise ValueError("يمكن فقط صرف الطلبات التي تم اعتمادها مسبقاً")
            
        journal_lines = []
        
        for line in order.lines.all():
            # ✅ Fix #3: التعامل الصحيح مع الصفر في الكمية المعتمدة
            qty = line.approved_qty if line.approved_qty is not None else line.requested_qty
            
            if qty <= 0:
                continue

            
            # 1. صرف من المخزن الرئيسي (يتكفل record_movement بحساب التكلفة بعد القفل لتجنب Race Condition)
            out_movement = InventoryService.record_movement(
                date_val=order.date,
                item=line.item,
                warehouse=order.from_warehouse,
                movement_type=StockMovement.MovementType.LOADING_OUT,
                quantity=-qty,
                unit_cost=None, # auto-calculate cost
                reference=order.number,
                source=order
            )
            
            cost = out_movement.unit_cost
            line_total_value = qty * cost
            
            # 2. إضافة لمخزن المندوب بنفس التكلفة
            InventoryService.record_movement(
                date_val=order.date,
                item=line.item,
                warehouse=order.to_warehouse,
                movement_type=StockMovement.MovementType.LOADING_IN,
                quantity=qty,
                unit_cost=cost,
                reference=order.number,
                source=order
            )
            
            # 3. التحضير لقيد اليومية إذا كانت الحسابات مختلفة
            acc_from = order.from_warehouse.gl_account or line.item.inventory_account
            acc_to = order.to_warehouse.gl_account or line.item.inventory_account
            
            if acc_from != acc_to:
                journal_lines.append({
                    'account': acc_to, 'debit': line_total_value, 'credit': 0,
                    'description': f'تحميل وارد - {line.item.name} ({order.number})'
                })
                journal_lines.append({
                    'account': acc_from, 'debit': 0, 'credit': line_total_value,
                    'description': f'تحميل صادر - {line.item.name} ({order.number})'
                })

            line.issued_qty = qty
            line.save()
            
        # إنشاء قيد اليومية إذا وجد اختلاف في الحسابات
        if journal_lines:
            from apps.core.services import JournalService
            from apps.core.models import JournalEntry
            entry = JournalService.create_entry(
                date_val=order.date,
                entry_type=JournalEntry.EntryType.INVENTORY,
                description=f'تحميل بضاعة للمندوب رقم {order.number}',
                lines=journal_lines,
                created_by=issued_by
            )
            order.journal_entry = entry

        order.status = LoadingOrder.Status.ISSUED
        order.issued_at = timezone.now()
        order.save()
        
        AuditService.log(issued_by, 'Issue', order, f'صرف طلب تحميل رقم {order.number}')
        return order

    @staticmethod
    @transaction.atomic
    def cancel_loading(order, cancelled_by):
        """
        ✅ Fix #4: إلغاء طلب تحميل لم يصرف بعد
        """
        if order.status == LoadingOrder.Status.ISSUED:
            raise ValueError("لا يمكن إلغاء طلب تم صرفه فعلياً. يجب عمل حركة عكسية بدلاً من ذلك.")
        
        if order.status == LoadingOrder.Status.CANCELLED:
            return order

        order.status = LoadingOrder.Status.CANCELLED
        order.save()
        
        AuditService.log(cancelled_by, 'Cancel', order, f'إلغاء طلب تحميل رقم {order.number}')
        return order

class StockVoucherService:
    @staticmethod
    @transaction.atomic
    def post_voucher(voucher, posted_by):
        from .models import StockVoucher, StockMovement
        from apps.core.services import JournalService
        from apps.core.models import JournalEntry
        
        if voucher.status != StockVoucher.Status.DRAFT:
            raise ValueError("يمكن ترحيل المسودات فقط")

        if not voucher.lines.exists():
            raise ValueError("لا يمكن ترحيل إذن بدون أسطر")

        # ✅ Fix #2: منع الترحيل بدون حساب مقابل لضمان توازن الحسابات المالية مع المخزون
        if not voucher.offset_account:
            raise ValueError("يجب تحديد الحساب المقابل لإتمام الترحيل لضمان دقة التقارير المالية.")

        journal_lines = []
        total_value = Decimal('0')

        for line in voucher.lines.all():
            if voucher.voucher_type == StockVoucher.VoucherType.ISSUE:
                # Issue: Negative quantity
                qty = -line.quantity
                
                # ✅ Fix #2: جلب التكلفة داخل record_movement بعد القفل مباشرة لتجنب السباق (Race Condition)
                movement = InventoryService.record_movement(
                    date_val=voucher.date,
                    item=line.item,
                    warehouse=voucher.warehouse,
                    movement_type=StockMovement.MovementType.ADJUSTMENT_OUT,
                    quantity=qty,
                    unit_cost=None, # auto-calculate cost after lock
                    reference=voucher.number,
                    source=voucher
                )
                
                cost = movement.unit_cost
                line.unit_cost = cost
                line.total_cost = line.quantity * cost
                line.save()
                
                # Financial entry for ISSUE
                if voucher.offset_account:
                    total_value += line.total_cost
                    journal_lines.append({
                        'account': voucher.offset_account, 'debit': line.total_cost, 'credit': 0,
                        'description': f'صرف - {line.item.name}'
                    })
                    journal_lines.append({
                        'account': line.item.inventory_account, 'debit': 0, 'credit': line.total_cost,
                        'description': f'نقص مخزون - {line.item.name}'
                    })

            else:
                # Receipt: Positive quantity, cost is already in the line
                # ✅ Fix #6: منع إضافة مخزون بتكلفة صفرية (إلا إذا كانت عينات مقصودة)
                if line.unit_cost <= 0:
                    raise ValueError(f'يجب إدخال تكلفة موجبة للصنف: {line.item.name} في إذن الإضافة.')

                qty = line.quantity
                cost = line.unit_cost
                line.total_cost = line.quantity * cost
                line.save()
                
                # Record Inventory Movement
                InventoryService.record_movement(
                    date_val=voucher.date,
                    item=line.item,
                    warehouse=voucher.warehouse,
                    movement_type=StockMovement.MovementType.ADJUSTMENT_IN,
                    quantity=qty,
                    unit_cost=cost,
                    reference=voucher.number,
                    source=voucher
                )
                
                # Financial entry for RECEIPT
                if voucher.offset_account:
                    total_value += line.total_cost
                    journal_lines.append({
                        'account': line.item.inventory_account, 'debit': line.total_cost, 'credit': 0,
                        'description': f'إضافة مخزون - {line.item.name}'
                    })
                    journal_lines.append({
                        'account': voucher.offset_account, 'debit': 0, 'credit': line.total_cost,
                        'description': f'إضافة - {line.item.name}'
                    })

        # Create Journal Entry if there are lines
        if journal_lines:
            entry = JournalService.create_entry(
                date_val=voucher.date,
                entry_type=JournalEntry.EntryType.INVENTORY,
                description=f'قيد {voucher.get_voucher_type_display()} رقم {voucher.number}',
                lines=journal_lines,
                source_document=voucher,
                created_by=posted_by
            )
            voucher.journal_entry = entry

        voucher.status = StockVoucher.Status.POSTED
        voucher.save()

        # Audit Log
        from apps.core.services import AuditService
        AuditService.log(posted_by, 'Post', voucher, f'ترحيل إذن مخزني رقم {voucher.number}')

        return voucher

    @staticmethod
    @transaction.atomic
    def reverse_voucher(voucher, reversed_by):
        """
        عكس إذن مخزني (إنشاء حركات عكسية وقيد عكسي)
        """
        if voucher.status != StockVoucher.Status.POSTED:
            raise ValueError("يمكن عكس الأذونات المرحلة فقط")
        
        # 1. Reverse Inventory Movements
        for line in voucher.lines.all():
            # ✅ Fix #1: تصحيح نوع الحركة والكمية عند العكس
            # عكس ISSUE (خروج) → إضافة (IN) | عكس RECEIPT (دخول) → سحب (OUT)
            if voucher.voucher_type == StockVoucher.VoucherType.ISSUE:
                mov_type = StockMovement.MovementType.ADJUSTMENT_IN
                qty = line.quantity # نرجع اللي خرج (كان سالباً في الحركة الأصلية)
            else:
                mov_type = StockMovement.MovementType.ADJUSTMENT_OUT
                qty = -line.quantity # نسحب اللي دخل

            InventoryService.record_movement(
                date_val=timezone.now().date(),
                item=line.item,
                warehouse=voucher.warehouse,
                movement_type=mov_type,
                quantity=qty,
                unit_cost=line.unit_cost,
                reference=f"عكس {voucher.number}",
                source=voucher
            )

        # 2. Reverse Journal Entry
        if voucher.journal_entry:
            from apps.core.services import JournalService
            JournalService.reverse_entry(
                entry=voucher.journal_entry,
                date_val=timezone.now().date(),
                created_by=reversed_by
            )

        voucher.status = StockVoucher.Status.CANCELLED
        voucher.save()

        from apps.core.services import AuditService
        AuditService.log(reversed_by, 'Reverse', voucher, f'عكس إذن مخزني رقم {voucher.number}')
        
        return voucher
