from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.conf import settings
from django.utils import timezone
from .models import (
    Item, Warehouse, StockMovement, ItemLedger, LoadingOrder, LoadingOrderLine,
    UnitOfMeasure, ItemCategory, WarehouseTransfer, WarehouseTransferLine,
    StockVoucher, StockVoucherLine,
)
from apps.core.services import AuditService, JournalService
from apps.core.models import JournalEntry
from apps.sales.models import SalesInvoiceLine, SalesReturnLine

class InventoryService:
    @staticmethod
    @transaction.atomic
    def generate_item_code():
        from django.db.models import Max
        max_code = (
            Item.objects
            .select_for_update()
            .filter(code__regex=r'^\d+$')
            .aggregate(Max('code'))['code__max']
        )
        if max_code:
            next_num = int(max_code) + 1
        else:
            next_num = 1
        while Item.objects.filter(code=str(next_num)).exists():
            next_num += 1
        return str(next_num)

    @staticmethod
    @transaction.atomic
    def generate_unit_code():
        last_unit = (
            UnitOfMeasure.objects
            .select_for_update()
            .filter(code__regex=r'^\d+$')
            .order_by('-code')
            .first()
        )
        if last_unit:
            return str(int(last_unit.code) + 1)
        return "1"

    @staticmethod
    @transaction.atomic
    def generate_category_code():
        last_category = (
            ItemCategory.objects
            .select_for_update()
            .filter(code__regex=r'^\d+$')
            .order_by('-code')
            .first()
        )
        if last_category:
            return str(int(last_category.code) + 1)
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
    def recalculate_item_ledger(item, warehouse, visited=None):
        """
        إعادة حساب أرصدة الـ Ledger وكافة الـ Running Balances في جدول الحركات 
        باستخدام معادلة متوسط التكلفة المرجح (WAC) ونشر التحديثات للحركات اللاحقة والمستندات المرتبطة بها.
        """
        if visited is None:
            visited = set()
            
        key = (item.id, warehouse.id)
        if key in visited:
            return Decimal('0')
        visited.add(key)

        movements = StockMovement.objects.filter(
            item=item, 
            warehouse=warehouse
        ).order_by('date', 'id').select_for_update()
        
        current_qty = Decimal('0')
        current_val = Decimal('0')
        
        for mov in movements:
            if mov.quantity > 0:
                # حركة واردة: نعتمد التكلفة الإجمالية للحركة
                # ونضيفها للقيم التراكمية مباشرة
                current_qty += mov.quantity
                current_val += mov.total_cost
            elif mov.quantity < 0:
                # حركة صادرة: يجب حساب متوسط التكلفة الجاري قبل هذه الحركة
                if current_qty > 0:
                    avg_cost = (current_val / current_qty).quantize(Decimal('0.00'))
                else:
                    avg_cost = Decimal('0')
                
                # تحديث تكلفة الحركة بناءً على المتوسط الجاري
                mov.unit_cost = avg_cost
                mov.total_cost = (mov.quantity * avg_cost).quantize(Decimal('0.00'))
                mov.save(update_fields=['unit_cost', 'total_cost'])
                
                # إضافة الكمية والقيمة الصادرة (السالبة) للتراكمي
                current_qty += mov.quantity
                current_val += mov.total_cost
            
            # تصفير القيمة عند صفرية المخزون لتجنب الفروق العشرية العائمة
            if current_qty == 0:
                current_val = Decimal('0')
                
            # تحديث الأرصدة الجارية في الحركة نفسها
            mov.running_quantity = current_qty
            mov.running_value = current_val
            mov.save(update_fields=['running_quantity', 'running_value'])
            
            # نشر التعديلات للمستندات المرتبطة بكل حركة صادرة تم تعديل تكلفتها
            if mov.quantity < 0:
                InventoryService._propagate_cost_change(mov, visited)
            
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
    def _propagate_cost_change(mov, visited):
        """
        نشر تحديثات التكلفة للمستندات الأصلية (فواتير، تحويلات، تحميل، أذون صرف) وقيودها اليومية المحاسبية.
        """
        
        # 1. صرف مبيعات (Sales Invoice)
        if mov.movement_type == StockMovement.MovementType.SALES_ISSUE and mov.source:
            invoice = mov.source
            lines_to_update = SalesInvoiceLine.objects.filter(
                invoice=invoice,
                item=mov.item,
                warehouse=mov.warehouse
            )
            for line in lines_to_update:
                line.cost = mov.unit_cost
                line.save(update_fields=['cost'])
                
                # تحديث قيد اليومية
                entry = invoice.journal_entry
                if entry:
                    base_qty = getattr(line, 'base_quantity', line.quantity) or line.quantity
                    new_cogs_value = (mov.unit_cost * base_qty).quantize(Decimal('0.00'))
                    
                    # مدين تكلفة المبيعات
                    cogs_lines = entry.lines.filter(
                        account=line.cost_of_goods_account,
                        description__contains=mov.item.name
                    )
                    for gl_line in cogs_lines:
                        gl_line.debit = new_cogs_value
                        gl_line.save(update_fields=['debit'])
                        
                    # دائن المخزون
                    inv_lines = entry.lines.filter(
                        account=line.item.inventory_account,
                        description__contains=mov.item.name
                    )
                    for gl_line in inv_lines:
                        gl_line.credit = new_cogs_value
                        gl_line.save(update_fields=['credit'])

        # 2. تحويل صادر (Warehouse Transfer Out)
        elif mov.movement_type == StockMovement.MovementType.TRANSFER_OUT and mov.source:
            transfer = mov.source
            
            # تحديث سطر التحويل المخزني
            transfer_lines = WarehouseTransferLine.objects.filter(
                transfer=transfer,
                item=mov.item
            )
            for line in transfer_lines:
                line.unit_cost = mov.unit_cost
                line.save(update_fields=['unit_cost'])
                
                # تحديث حركة الوارد في المخزن الوجهة
                in_mov = StockMovement.objects.filter(
                    content_type=mov.content_type,
                    object_id=mov.object_id,
                    item=mov.item,
                    movement_type=StockMovement.MovementType.TRANSFER_IN,
                    warehouse=transfer.to_warehouse
                ).first()
                if in_mov:
                    in_mov.unit_cost = mov.unit_cost
                    in_mov.total_cost = (in_mov.quantity * mov.unit_cost).quantize(Decimal('0.00'))
                    in_mov.save(update_fields=['unit_cost', 'total_cost'])
                    
                    # استدعاء إعادة الحساب للمخزن الوجهة لنشر التحديثات فيه
                    InventoryService.recalculate_item_ledger(mov.item, transfer.to_warehouse, visited)
                
                # تحديث القيد المحاسبي
                entries = JournalEntry.objects.filter(
                    description__contains=f'تحويل مخزني رقم {transfer.number}',
                    entry_type=JournalEntry.EntryType.INVENTORY
                )
                for entry in entries:
                    acc_from = transfer.from_warehouse.gl_account or mov.item.inventory_account
                    acc_to = transfer.to_warehouse.gl_account or mov.item.inventory_account
                    new_val = (line.quantity * mov.unit_cost).quantize(Decimal('0.00'))
                    
                    # DR lines (Incoming to destination)
                    to_lines = entry.lines.filter(
                        account=acc_to,
                        description__contains=mov.item.name
                    )
                    for gl_line in to_lines:
                        gl_line.debit = new_val
                        gl_line.save(update_fields=['debit'])
                        
                    # CR lines (Outgoing from source)
                    from_lines = entry.lines.filter(
                        account=acc_from,
                        description__contains=mov.item.name
                    )
                    for gl_line in from_lines:
                        gl_line.credit = new_val
                        gl_line.save(update_fields=['credit'])

        # 3. تحميل صادر (Loading Out to rep)
        elif mov.movement_type == StockMovement.MovementType.LOADING_OUT and mov.source:
            order = mov.source
            
            # تحديث حركة الوارد في مخزن المندوب
            in_mov = StockMovement.objects.filter(
                content_type=mov.content_type,
                object_id=mov.object_id,
                item=mov.item,
                movement_type=StockMovement.MovementType.LOADING_IN,
                warehouse=order.to_warehouse
            ).first()
            if in_mov:
                in_mov.unit_cost = mov.unit_cost
                in_mov.total_cost = (in_mov.quantity * mov.unit_cost).quantize(Decimal('0.00'))
                in_mov.save(update_fields=['unit_cost', 'total_cost'])
                
                # استدعاء إعادة الحساب لمخزن المندوب لنشر التحديثات فيه
                InventoryService.recalculate_item_ledger(mov.item, order.to_warehouse, visited)
            
            # تحديث القيد المحاسبي
            entry = order.journal_entry
            if entry:
                line = order.lines.filter(item=mov.item).first()
                if line:
                    qty = line.issued_qty if line.issued_qty is not None else (line.approved_qty if line.approved_qty is not None else line.requested_qty)
                    new_val = (qty * mov.unit_cost).quantize(Decimal('0.00'))
                    
                    acc_from = order.from_warehouse.gl_account or mov.item.inventory_account
                    acc_to = order.to_warehouse.gl_account or mov.item.inventory_account
                    
                    # DR lines (Incoming)
                    to_lines = entry.lines.filter(
                        account=acc_to,
                        description__contains=mov.item.name
                    )
                    for gl_line in to_lines:
                        gl_line.debit = new_val
                        gl_line.save(update_fields=['debit'])
                        
                    # CR lines (Outgoing)
                    from_lines = entry.lines.filter(
                        account=acc_from,
                        description__contains=mov.item.name
                    )
                    for gl_line in from_lines:
                        gl_line.credit = new_val
                        gl_line.save(update_fields=['credit'])

        # 4. إذن صرف مخزني (Adjustment Out)
        elif mov.movement_type == StockMovement.MovementType.ADJUSTMENT_OUT and mov.source:
            voucher = mov.source
            voucher_lines = StockVoucherLine.objects.filter(
                voucher=voucher,
                item=mov.item
            )
            for line in voucher_lines:
                line.unit_cost = mov.unit_cost
                line.total_cost = (line.quantity * mov.unit_cost).quantize(Decimal('0.00'))
                line.save(update_fields=['unit_cost', 'total_cost'])
                
                # تحديث القيد المحاسبي
                entry = voucher.journal_entry
                if entry:
                    acc_offset = voucher.offset_account
                    acc_inv = mov.item.inventory_account
                    new_val = (line.quantity * mov.unit_cost).quantize(Decimal('0.00'))
                    
                    if acc_offset:
                        # DR lines (Offset Account Debit)
                        offset_lines = entry.lines.filter(
                            account=acc_offset,
                            description__contains=mov.item.name
                        )
                        for gl_line in offset_lines:
                            gl_line.debit = new_val
                            gl_line.save(update_fields=['debit'])
                            
                    # CR lines (Inventory Account Credit)
                    inv_lines = entry.lines.filter(
                        account=acc_inv,
                        description__contains=mov.item.name
                    )
                    for gl_line in inv_lines:
                        gl_line.credit = new_val
                        gl_line.save(update_fields=['credit'])



    @staticmethod
    @transaction.atomic
    def reduce_stock(invoice) -> dict:
        """
        Reduces stock based on sales invoice lines.
        ✅ Fix #4 & #2: يتم جلب التكلفة داخل record_movement ويرجع القاموس بالنتائج لتوحيدها مع القيد.
        """
        line_costs = {}
        for line in invoice.lines.all():
            # استخدم base_quantity المحفوظ إن وجد، وإلا احسبها
            base_qty = getattr(line, 'base_quantity', line.quantity) or line.quantity
            if not base_qty and hasattr(line, 'unit') and line.unit:
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
            base_qty = getattr(line, 'base_quantity', line.quantity) or line.quantity
            if not base_qty and hasattr(line, 'unit') and line.unit:
                base_qty = line.item.convert_to_base(line.quantity, line.unit)

            InventoryService.record_movement(
                date_val=timezone.now().date(),
                item=line.item,
                warehouse=line.warehouse,
                movement_type=StockMovement.MovementType.SALE_RETURN, # استخدام نوع حركة مرتجع/إعادة
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
            conversion = Decimal('1')
            if hasattr(line, 'unit') and line.unit:
                if line.unit == line.item.purchase_unit:
                    conversion = line.item.purchase_conversion_factor or Decimal('1')
                elif line.unit == line.item.sales_unit:
                    conversion = line.item.conversion_factor or Decimal('1')
            
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
        transfer = WarehouseTransfer.objects.select_for_update().get(pk=transfer.pk)
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
                quantity=-line.base_quantity,
                unit_cost=None, # auto-calculate cost
                source=transfer,
                reference=f'Transfer {transfer.number}'
            )
            
            cost = out_movement.unit_cost
            line.unit_cost = cost
            line.save(update_fields=['unit_cost'])
            
            line_total_val = line.base_quantity * cost

            # 2. Incoming to destination
            InventoryService.record_movement(
                date_val=transfer.date,
                item=line.item,
                warehouse=transfer.to_warehouse,
                movement_type=StockMovement.MovementType.TRANSFER_IN,
                quantity=line.base_quantity,
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
        transfer = WarehouseTransfer.objects.select_for_update().get(pk=transfer.pk)
        if transfer.status != 'posted':
            if transfer.status == 'cancelled':
                raise ValueError("هذا التحويل تم إلغاؤه/عكسه مسبقاً")
            raise ValueError("يمكن عكس التحويلات المرحلة فقط")

        for line in transfer.lines.all():
            # 1. Reverse outgoing (was TRANSFER_OUT negative, now TRANSFER_IN positive)
            InventoryService.record_movement(
                date_val=timezone.now().date(),
                item=line.item,
                warehouse=transfer.from_warehouse,
                movement_type=StockMovement.MovementType.TRANSFER_IN,
                quantity=line.base_quantity,
                unit_cost=line.unit_cost,
                source=transfer,
                reference=f'Reversal of {transfer.number}'
            )

            # 2. Reverse incoming (was TRANSFER_IN positive, now TRANSFER_OUT negative)
            InventoryService.record_movement(
                date_val=timezone.now().date(),
                item=line.item,
                warehouse=transfer.to_warehouse,
                movement_type=StockMovement.MovementType.TRANSFER_OUT,
                quantity=-line.base_quantity,
                unit_cost=line.unit_cost,
                source=transfer,
                reference=f'Reversal of {transfer.number}'
            )

        # 3. GL Entry Reversal
        entries = JournalEntry.objects.filter(
            description__contains=f'تحويل مخزني رقم {transfer.number}',
            entry_type=JournalEntry.EntryType.INVENTORY
        )
        for entry in entries:
            if entry.is_reversed:
                continue
            JournalService.reverse_entry(entry, timezone.now().date(), reversed_by)

        transfer.status = 'cancelled'
        transfer.save()

        AuditService.log(reversed_by, 'Reverse', transfer, f'عكس تحويل مخزني رقم {transfer.number}')


class LoadingService:
    @staticmethod
    @transaction.atomic
    def approve_loading(order, approved_by):
        """اعتماد طلب التحميل وتثبيت الكميات المعتمدة"""
        order = LoadingOrder.objects.select_for_update().get(pk=order.pk)
        if order.status != LoadingOrder.Status.PENDING:
            raise ValueError("يمكن فقط اعتماد الطلبات التي في حالة 'في انتظار الاعتماد'")

        for line in order.lines.all():
            if line.approved_qty is None:
                line.approved_qty = line.requested_qty

            # Calculate base approved quantity
            base_approved_qty = line.item.convert_to_base(line.approved_qty, line.unit) if line.unit else line.approved_qty

            ledger = (
                ItemLedger.objects
                .select_for_update()
                .filter(item=line.item, warehouse=order.from_warehouse)
                .first()
            )
            on_hand = ledger.quantity_on_hand if ledger else Decimal('0')
            if base_approved_qty > on_hand:
                raise ValueError(
                    f"الكمية المعتمدة للصنف '{line.item.name}' ({line.approved_qty} بوحدتها) "
                    f"تتجاوز المخزون المتاح في المستودع المصدر ({on_hand})."
                )
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
        order = LoadingOrder.objects.select_for_update().get(pk=order.pk)
        if order.status != LoadingOrder.Status.APPROVED:
            raise ValueError("يمكن فقط صرف الطلبات التي تم اعتمادها مسبقاً")
            
        journal_lines = []
        
        for line in order.lines.all():
            # ✅ Fix #3: التعامل الصحيح مع الصفر في الكمية المعتمدة
            qty = line.approved_qty if line.approved_qty is not None else line.requested_qty
            
            if qty <= 0:
                continue

            # التحقق من أن الكمية المصروفة لا تتجاوز الكمية المعتمدة
            if line.issued_qty is not None and line.issued_qty > qty:
                raise ValueError(
                    f"الكمية المصروفة للصنف '{line.item.name}' ({line.issued_qty}) "
                    f"تتجاوز الكمية المعتمدة ({qty})"
                )

            # Calculate base quantity for actual movement
            actual_qty = line.issued_qty if line.issued_qty is not None else qty
            base_qty = line.item.convert_to_base(actual_qty, line.unit) if line.unit else actual_qty
            
            # 1. صرف من المخزن الرئيسي (يتكفل record_movement بحساب التكلفة بعد القفل لتجنب Race Condition)
            out_movement = InventoryService.record_movement(
                date_val=order.date,
                item=line.item,
                warehouse=order.from_warehouse,
                movement_type=StockMovement.MovementType.LOADING_OUT,
                quantity=-base_qty,
                unit_cost=None, # auto-calculate cost
                reference=order.number,
                source=order
            )
            
            cost = out_movement.unit_cost
            line_total_value = base_qty * cost
            
            # 2. إضافة لمخزن المندوب بنفس التكلفة
            InventoryService.record_movement(
                date_val=order.date,
                item=line.item,
                warehouse=order.to_warehouse,
                movement_type=StockMovement.MovementType.LOADING_IN,
                quantity=base_qty,
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
        order = LoadingOrder.objects.select_for_update().get(pk=order.pk)
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
        voucher = StockVoucher.objects.select_for_update().get(pk=voucher.pk)
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
            base_qty = line.base_quantity
            
            if voucher.voucher_type == StockVoucher.VoucherType.ISSUE:
                # Issue: Negative quantity
                qty = -base_qty
                
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
                line.total_cost = base_qty * cost
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

                qty = base_qty
                cost = line.unit_cost
                line.total_cost = base_qty * cost
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

        AuditService.log(posted_by, 'Post', voucher, f'ترحيل إذن مخزني رقم {voucher.number}')

        return voucher

    @staticmethod
    @transaction.atomic
    def reverse_voucher(voucher, reversed_by):
        """
        عكس إذن مخزني (إنشاء حركات عكسية وقيد عكسي)
        """
        voucher = StockVoucher.objects.select_for_update().get(pk=voucher.pk)
        if voucher.status != StockVoucher.Status.POSTED:
            if voucher.status == StockVoucher.Status.CANCELLED:
                raise ValueError("هذا الإذن تم إلغاؤه/عكسه مسبقاً")
            raise ValueError("يمكن عكس الأذونات المرحلة فقط")
        
        # 1. Reverse Inventory Movements
        for line in voucher.lines.all():
            # ✅ Fix #1: تصحيح نوع الحركة والكمية عند العكس
            # عكس ISSUE (خروج) → إضافة (IN) | عكس RECEIPT (دخول) → سحب (OUT)
            if voucher.voucher_type == StockVoucher.VoucherType.ISSUE:
                mov_type = StockMovement.MovementType.ADJUSTMENT_IN
                qty = line.base_quantity # نرجع اللي خرج (كان سالباً في الحركة الأصلية)
            else:
                mov_type = StockMovement.MovementType.ADJUSTMENT_OUT
                qty = -line.base_quantity # نسحب اللي دخل

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
            if voucher.journal_entry.is_reversed:
                raise ValueError("هذا الإذن تم عكس قيده المحاسبي مسبقاً")
            JournalService.reverse_entry(
                entry=voucher.journal_entry,
                date_val=timezone.now().date(),
                created_by=reversed_by
            )

        voucher.status = StockVoucher.Status.CANCELLED
        voucher.save()

        AuditService.log(reversed_by, 'Reverse', voucher, f'عكس إذن مخزني رقم {voucher.number}')
        
        return voucher
