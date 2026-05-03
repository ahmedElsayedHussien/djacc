from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from .models import Item, Warehouse, StockMovement, ItemLedger, LoadingOrder, LoadingOrderLine

class InventoryService:
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
        total_cost = quantity * unit_cost
        
        # Get or create ledger with lock
        ledger, created = ItemLedger.objects.select_for_update().get_or_create(
            item=item, 
            warehouse=warehouse,
            defaults={'quantity_on_hand': 0, 'total_value': 0}
        )
        
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
        if ledger.quantity_on_hand <= 0:
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
    def reduce_stock(invoice) -> None:
        """
        Reduces stock based on sales invoice lines.
        """
        for line in invoice.lines.all():
            # Get current cost for COGS
            cost = InventoryService.get_item_cost(line.item, line.warehouse)
            
            # Convert quantity to base unit if unit is specified
            base_qty = line.quantity
            if hasattr(line, 'unit') and line.unit:
                base_qty = line.item.convert_to_base(line.quantity, line.unit)

            InventoryService.record_movement(
                date_val=invoice.date,
                item=line.item,
                warehouse=line.warehouse,
                movement_type=StockMovement.MovementType.SALES_ISSUE,
                quantity=-base_qty,  # Negative for reduction
                unit_cost=cost,
                source=invoice,
                reference=f'Invoice {invoice.number}'
            )

    @staticmethod
    @transaction.atomic
    def restore_stock(invoice) -> None:
        """
        Restores stock by reversing the movements created by reduce_stock.
        Used when an invoice is cancelled/reversed.
        """
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(invoice)
        
        for line in invoice.lines.all():
            # Try to find the exact cost used during reduction
            try:
                movement = StockMovement.objects.filter(
                    content_type=ct,
                    object_id=invoice.id,
                    item=line.item,
                    warehouse=line.warehouse,
                    quantity__lt=0
                ).latest('id')
                cost = movement.unit_cost
            except StockMovement.DoesNotExist:
                cost = line.cost or Decimal('0')

            base_qty = line.quantity
            if hasattr(line, 'unit') and line.unit:
                base_qty = line.item.convert_to_base(line.quantity, line.unit)

            InventoryService.record_movement(
                date_val=timezone.now().date(),
                item=line.item,
                warehouse=line.warehouse,
                movement_type=StockMovement.MovementType.ADJUSTMENT_IN,
                quantity=base_qty,  # Positive to restore
                unit_cost=cost,
                source=invoice,
                reference=f'Reverse {invoice.number}'
            )

    @staticmethod
    @transaction.atomic
    def increase_stock(invoice) -> None:
        """
        Increases stock based on purchase invoice lines.
        """
        for line in invoice.lines.all():
            # Convert quantity to base unit if unit is specified
            base_qty = line.quantity
            if hasattr(line, 'unit') and line.unit:
                base_qty = line.item.convert_to_base(line.quantity, line.unit)

            InventoryService.record_movement(
                date_val=invoice.date,
                item=line.item,
                warehouse=line.warehouse,
                movement_type=StockMovement.MovementType.PURCHASE_RECEIPT,
                quantity=base_qty,
                unit_cost=line.unit_cost,
                source=invoice,
                reference=f'Purchase {invoice.number}'
            )

    @staticmethod
    @transaction.atomic
    def process_transfer(transfer) -> None:
        """
        Records two stock movements:
        1. Out from source warehouse
        2. In to destination warehouse
        """
        # Get current cost from source warehouse
        cost = InventoryService.get_item_cost(transfer.item, transfer.from_warehouse)
        
        # 1. Outgoing from source
        InventoryService.record_movement(
            date_val=transfer.date,
            item=transfer.item,
            warehouse=transfer.from_warehouse,
            movement_type=StockMovement.MovementType.TRANSFER_OUT,
            quantity=-transfer.quantity,
            unit_cost=cost,
            source=transfer,
            reference=f'Transfer {transfer.number}'
        )
        
        # 2. Incoming to destination
        InventoryService.record_movement(
            date_val=transfer.date,
            item=transfer.item,
            warehouse=transfer.to_warehouse,
            movement_type=StockMovement.MovementType.TRANSFER_IN,
            quantity=transfer.quantity,
            unit_cost=cost,
            source=transfer,
            reference=f'Transfer {transfer.number}'
        )
        
        transfer.status = 'posted'
        transfer.save()

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
        return order

    @staticmethod
    @transaction.atomic
    def issue_loading(order, issued_by):
        """تنفيذ الصرف الفعلي - تحويل المخزون من الرئيسي لمخزن المندوب"""
        if order.status != LoadingOrder.Status.APPROVED:
            raise ValueError("يمكن فقط صرف الطلبات التي تم اعتمادها مسبقاً")
            
        for line in order.lines.all():
            qty = line.approved_qty or line.requested_qty
            
            # الحصول على التكلفة الحالية من المخزن الرئيسي
            cost = InventoryService.get_item_cost(line.item, order.from_warehouse)
            
            # 1. صرف من المخزن الرئيسي
            InventoryService.record_movement(
                date_val=order.date,
                item=line.item,
                warehouse=order.from_warehouse,
                movement_type=StockMovement.MovementType.LOADING_OUT,
                quantity=-qty,
                unit_cost=cost,
                reference=order.number,
                source=order
            )
            
            # 2. إضافة لمخزن المندوب
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
            
            line.issued_qty = qty
            line.save()
            
        order.status = LoadingOrder.Status.ISSUED
        order.issued_at = timezone.now()
        order.save()
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

        journal_lines = []
        total_value = Decimal('0')

        for line in voucher.lines.all():
            if voucher.voucher_type == StockVoucher.VoucherType.ISSUE:
                # Issue: Negative quantity, calculate cost
                cost = InventoryService.get_item_cost(line.item, voucher.warehouse)
                qty = -line.quantity
                line.unit_cost = cost
                line.total_cost = line.quantity * cost
                line.save()
                
                mov_type = StockMovement.MovementType.ADJUSTMENT_OUT
                
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
                qty = line.quantity
                cost = line.unit_cost
                line.total_cost = line.quantity * cost
                line.save()
                
                mov_type = StockMovement.MovementType.ADJUSTMENT_IN
                
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

            # Record Inventory Movement
            InventoryService.record_movement(
                date_val=voucher.date,
                item=line.item,
                warehouse=voucher.warehouse,
                movement_type=mov_type,
                quantity=qty,
                unit_cost=cost,
                reference=voucher.number,
                source=voucher
            )

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
            # Simply record the opposite movement
            InventoryService.record_movement(
                date_val=timezone.now().date(),
                item=line.item,
                warehouse=voucher.warehouse,
                movement_type='adjustment_in' if voucher.voucher_type == StockVoucher.VoucherType.ISSUE else 'adjustment_out',
                quantity=-line.quantity if voucher.voucher_type == StockVoucher.VoucherType.ISSUE else -line.quantity,
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
