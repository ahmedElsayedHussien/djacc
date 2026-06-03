from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import date
from decimal import Decimal

from apps.inventory.models import (
    Warehouse, ItemCategory, UnitOfMeasure, Item, ItemLedger, StockMovement,
    LoadingOrder, LoadingOrderLine, WarehouseTransfer, WarehouseTransferLine,
    StockVoucher, StockVoucherLine
)
from apps.inventory.services import (
    InventoryService, LoadingService, StockVoucherService
)
from apps.core.models import Account, FiscalYear, JournalEntry, JournalLine
from apps.sales.models import SalesRepresentative

class Command(BaseCommand):
    help = 'اختبار دورة مخزون كاملة'

    def handle(self, *args, **options):
        today = date.today()

        # ======================== CLEANUP ========================
        # Clean in dependency order (children before parents)
        from apps.pos.models import POSOrderLine, POSOrder, POSPayment, POSSession, POSStation
        from apps.sales.models import SalesInvoiceLine, SalesInvoice, SalesReturnLine, SalesReturn, CustomerReceipt, ReceiptAllocation, RepSettlementInvoice, RepDailySettlement
        from apps.purchases.models import PurchaseInvoiceLine, PurchaseInvoice, PurchaseReturnLine, PurchaseReturn, SupplierPayment, PaymentAllocation
        RepSettlementInvoice.objects.all().delete()
        RepDailySettlement.objects.all().delete()
        SalesReturnLine.objects.all().delete()
        SalesReturn.objects.all().delete()
        ReceiptAllocation.objects.all().delete()
        CustomerReceipt.objects.all().delete()
        SalesInvoiceLine.objects.all().delete()
        SalesInvoice.objects.all().delete()
        PurchaseReturnLine.objects.all().delete()
        PurchaseReturn.objects.all().delete()
        PaymentAllocation.objects.all().delete()
        SupplierPayment.objects.all().delete()
        PurchaseInvoiceLine.objects.all().delete()
        PurchaseInvoice.objects.all().delete()
        JournalLine.objects.all().delete()
        JournalEntry.objects.all().delete()
        POSPayment.objects.all().delete()
        POSOrderLine.objects.all().delete()
        POSOrder.objects.all().delete()
        POSSession.objects.all().delete()
        POSStation.objects.all().delete()
        StockMovement.objects.all().delete()
        ItemLedger.objects.all().delete()
        StockVoucherLine.objects.all().delete()
        StockVoucher.objects.all().delete()
        WarehouseTransferLine.objects.all().delete()
        WarehouseTransfer.objects.all().delete()
        LoadingOrderLine.objects.all().delete()
        LoadingOrder.objects.all().delete()
        Item.objects.all().delete()
        UnitOfMeasure.objects.all().delete()
        ItemCategory.objects.all().delete()
        self.stdout.write('تم مسح بيانات الاختبار السابقة')

        # ======================== SANITY CHECKS ========================
        User = get_user_model()
        admin = User.objects.filter(is_superuser=True).first()
        if not admin:
            self.stdout.write(self.style.ERROR('لا يوجد مستخدم superuser'))
            return

        # Create fiscal year if needed
        fy = FiscalYear.objects.filter(start_date__lte=today, end_date__gte=today).first()
        if not fy:
            fy = FiscalYear.objects.create(
                name=f'سنة مالية {today.year}',
                start_date=date(today.year, 1, 1),
                end_date=date(today.year, 12, 31),
                is_closed=False,
            )
            self.stdout.write(f'تم إنشاء السنة المالية: {fy.name}')

        # Check/create accounts
        inv_account = Account.objects.filter(code='1131').first()
        if not inv_account:
            inv_account = Account.objects.filter(name__contains='مخزون').first()
        # Use leaf account for rep warehouse (child of parent 1134)
        rep_account = Account.objects.filter(code='1134001').first()
        if not rep_account:
            rep_account = Account.objects.filter(code__startswith='1134').exclude(code='1134').first()

        offset_account = Account.objects.filter(code='511').first()
        if not offset_account:
            offset_account = Account.objects.filter(account_type='expense', parent__isnull=False).first()
        
        self.stdout.write(f'مخزون البضاعة: {inv_account.code if inv_account else "---"}')
        self.stdout.write(f'مخازن المناديب: {rep_account.code if rep_account else "---"}')
        self.stdout.write(f'حساب مقابل: {offset_account.code if offset_account else "---"}')

        # ======================== 1. CREATE WAREHOUSES ========================
        main_wh, _ = Warehouse.objects.get_or_create(
            code='WH-MAIN',
            defaults={
                'name': 'المخزن الرئيسي',
                'gl_account': inv_account,
                'is_active': True,
            }
        )
        rep_wh, created = Warehouse.objects.get_or_create(
            code='WH-REP',
            defaults={
                'name': 'مخزن المندوب',
                'gl_account': rep_account or inv_account,
                'is_active': True,
            }
        )
        if not created and rep_wh.gl_account_id != (rep_account.id if rep_account else None):
            rep_wh.gl_account = rep_account or inv_account
            rep_wh.save(update_fields=['gl_account'])
        returns_wh, _ = Warehouse.objects.get_or_create(
            code='WH-RET',
            defaults={
                'name': 'مستودع المرتجعات',
                'gl_account': inv_account,
                'is_active': True,
                'is_returns': True,
            }
        )
        self.stdout.write(f'المخازن: {main_wh.name} | {rep_wh.name} | {returns_wh.name}')

        # ======================== 2. CREATE CATEGORIES & UNITS & ITEMS ========================
        cat, _ = ItemCategory.objects.get_or_create(code='1', defaults={'name': 'عام'})

        unit_pc, _ = UnitOfMeasure.objects.get_or_create(code='PC', defaults={'name': 'قطعة'})
        unit_box, _ = UnitOfMeasure.objects.get_or_create(code='BOX', defaults={'name': 'كرتونة'})

        item1, _ = Item.objects.get_or_create(
            code='ITEM-001',
            defaults={
                'name': 'منتج اختبار ألف',
                'category': cat,
                'base_unit': unit_pc,
                'sales_unit': unit_box,
                'conversion_factor': 12,
                'inventory_account': inv_account or Account.objects.filter(account_type='asset').first(),
                'cogs_account': offset_account or Account.objects.filter(account_type='expense').first(),
                'standard_price': Decimal('150.00'),
            }
        )
        item2, _ = Item.objects.get_or_create(
            code='ITEM-002',
            defaults={
                'name': 'منتج اختبار باء',
                'category': cat,
                'base_unit': unit_pc,
                'sales_unit': unit_box,
                'conversion_factor': 6,
                'inventory_account': inv_account or Account.objects.filter(account_type='asset').first(),
                'cogs_account': offset_account or Account.objects.filter(account_type='expense').first(),
                'standard_price': Decimal('75.00'),
            }
        )
        self.stdout.write(f'الأصناف: {item1.name} (@ ${item1.standard_price}) | {item2.name} (@ ${item2.standard_price})')

        # ======================== 3. OPENING BALANCE via StockVoucher RECEIPT ========================
        self.stdout.write('\n===== 1. إضافة رصيد افتتاحي =====')
        voucher_open = StockVoucher.objects.create(
            number='VCH-OPEN-001',
            date=today,
            voucher_type=StockVoucher.VoucherType.RECEIPT,
            warehouse=main_wh,
            offset_account=inv_account,
            notes='رصيد افتتاحي',
            created_by=admin,
        )
        line1 = StockVoucherLine.objects.create(
            voucher=voucher_open,
            item=item1,
            quantity=100,
            unit_cost=Decimal('100.00'),
            total_cost=Decimal('10000.00'),
        )
        line2 = StockVoucherLine.objects.create(
            voucher=voucher_open,
            item=item2,
            quantity=50,
            unit_cost=Decimal('60.00'),
            total_cost=Decimal('3000.00'),
        )
        StockVoucherService.post_voucher(voucher_open, admin)
        
        # Check ledger
        led1 = ItemLedger.objects.get(item=item1, warehouse=main_wh)
        led2 = ItemLedger.objects.get(item=item2, warehouse=main_wh)
        self.stdout.write(f'  {item1.name}: الكمية={led1.quantity_on_hand}, القيمة={led1.total_value}')
        self.stdout.write(f'  {item2.name}: الكمية={led2.quantity_on_hand}, القيمة={led2.total_value}')

        # ======================== 4. CREATE & ISSUE LOADING ORDER ========================
        self.stdout.write('\n===== 2. طلب تحميل للمندوب =====')
        rep = SalesRepresentative.objects.first()
        if not rep:
            self.stdout.write(self.style.WARNING('لا يوجد مندوب مبيعات'))
        else:
            load = LoadingOrder.objects.create(
                number='LOAD-001',
                date=today,
                sales_rep=rep,
                from_warehouse=main_wh,
                to_warehouse=rep_wh,
                status=LoadingOrder.Status.PENDING,
                requested_by=admin,
                notes='تحميل بضاعة للمندوب',
            )
            LoadingOrderLine.objects.create(
                loading_order=load,
                item=item1,
                requested_qty=24,  # 2 كرتونة
            )
            LoadingOrderLine.objects.create(
                loading_order=load,
                item=item2,
                requested_qty=12,
            )
            self.stdout.write(f'  تم إنشاء طلب التحميل: {load.number}')
            
            # Approve
            LoadingService.approve_loading(load, admin)
            self.stdout.write(f'  تم اعتماد طلب التحميل')
            
            # Issue (execute)
            LoadingService.issue_loading(load, admin)
            self.stdout.write(f'  تم صرف طلب التحميل')

            # Check ledger after loading
            led1_main = ItemLedger.objects.get(item=item1, warehouse=main_wh)
            led1_rep = ItemLedger.objects.get(item=item1, warehouse=rep_wh)
            self.stdout.write(f'  {item1.name}: الرئيسي={led1_main.quantity_on_hand}, المندوب={led1_rep.quantity_on_hand}')
            self.stdout.write(f'  (توقع: الرئيسي 76, المندوب 24)')

        # ======================== 5. WAREHOUSE TRANSFER ========================
        self.stdout.write('\n===== 3. تحويل مخزني =====')
        transfer = WarehouseTransfer.objects.create(
            number='TRF-001',
            date=today,
            from_warehouse=main_wh,
            to_warehouse=returns_wh,
            notes='تحويل لبضاعة تالفة',
        )
        WarehouseTransferLine.objects.create(
            transfer=transfer,
            item=item1,
            quantity=5,
        )
        self.stdout.write(f'  تم إنشاء التحويل: {transfer.number}')
        
        InventoryService.process_transfer(transfer, admin)
        self.stdout.write(f'  تم ترحيل التحويل')
        
        # Check ledger
        led1_main = ItemLedger.objects.get(item=item1, warehouse=main_wh)
        led1_ret = ItemLedger.objects.get(item=item1, warehouse=returns_wh)
        self.stdout.write(f'  {item1.name}: الرئيسي={led1_main.quantity_on_hand}, المرتجعات={led1_ret.quantity_on_hand}')

        # ======================== 6. STOCK VOUCHER ISSUE (صرف/إعدام) ========================
        self.stdout.write('\n===== 4. إذن صرف/إعدام =====')
        voucher_issue = StockVoucher.objects.create(
            number='VCH-ISSUE-001',
            date=today,
            voucher_type=StockVoucher.VoucherType.ISSUE,
            warehouse=main_wh,
            offset_account=offset_account,
            notes='إعدام بضاعة تالفة',
            created_by=admin,
        )
        StockVoucherLine.objects.create(
            voucher=voucher_issue,
            item=item1,
            quantity=3,
        )
        StockVoucherService.post_voucher(voucher_issue, admin)
        self.stdout.write(f'  تم ترحيل إذن الصرف')
        
        led1_main = ItemLedger.objects.get(item=item1, warehouse=main_wh)
        self.stdout.write(f'  {item1.name}: الرئيسي={led1_main.quantity_on_hand}')
        self.stdout.write(f'  (توقع: 68)')

        # ======================== 7. REVERSE TRANSFER ========================
        self.stdout.write('\n===== 5. عكس التحويل المخزني =====')
        InventoryService.reverse_transfer(transfer, admin)
        self.stdout.write(f'  تم عكس التحويل')
        
        led1_main = ItemLedger.objects.get(item=item1, warehouse=main_wh)
        led1_ret = ItemLedger.objects.get(item=item1, warehouse=returns_wh)
        self.stdout.write(f'  {item1.name}: الرئيسي={led1_main.quantity_on_hand}, المرتجعات={led1_ret.quantity_on_hand}')
        self.stdout.write(f'  (توقع: 73, 0)')

        # ======================== 8. CANCEL VOUCHER ISSUE ========================
        self.stdout.write('\n===== 6. عكس إذن الصرف =====')
        StockVoucherService.reverse_voucher(voucher_issue, admin)
        self.stdout.write(f'  تم عكس إذن الصرف')
        
        led1_main = ItemLedger.objects.get(item=item1, warehouse=main_wh)
        self.stdout.write(f'  {item1.name}: الرئيسي={led1_main.quantity_on_hand}')
        self.stdout.write(f'  (توقع: 76 - العودة لما قبل الإعدام)')

        # ======================== 9. RECALCULATE LEDGER ========================
        self.stdout.write('\n===== 7. إعادة حساب الـ Ledger =====')
        InventoryService.recalculate_item_ledger(item1, main_wh)
        led1_main = ItemLedger.objects.get(item=item1, warehouse=main_wh)
        movements_count = StockMovement.objects.filter(item=item1, warehouse=main_wh).count()
        self.stdout.write(f'  {item1.name}@{main_wh.name}: الكمية={led1_main.quantity_on_hand}, القيمة={led1_main.total_value}')
        self.stdout.write(f'  عدد حركات {item1.name}: {movements_count}')

        # ======================== VERIFY JOURNAL ENTRIES ========================
        self.stdout.write('\n===== القيود المحاسبية =====')
        entries = JournalEntry.objects.filter(entry_type='inventory').order_by('date', 'id')
        self.stdout.write(f'عدد القيود: {entries.count()}')
        balanced_ok = 0
        for e in entries:
            lines = e.lines.all()
            total_dr = sum((l.debit or 0) for l in lines)
            total_cr = sum((l.credit or 0) for l in lines)
            status = '✓' if total_dr == total_cr else '✗'
            if total_dr == total_cr:
                balanced_ok += 1
            self.stdout.write(f'  {status} قيد #{e.id} | {e.date} | {e.description}')
            for line in lines:
                dr_str = f'{line.debit:>8}' if line.debit else '       0'
                cr_str = f'{line.credit:>8}' if line.credit else '       0'
                self.stdout.write(f'      {line.account.code} {line.account.name}: مدين={dr_str} دائن={cr_str}')
            self.stdout.write(f'      ── المجموع: مدين={total_dr} دائن={total_cr}')
        
        self.stdout.write(f'\nالقيود المتوازنة: {balanced_ok}/{entries.count()}')

        # ======================== FINAL SUMMARY ========================
        self.stdout.write('\n' + '=' * 50)
        if balanced_ok == entries.count() and entries.count() > 0:
            self.stdout.write(self.style.SUCCESS('تم بنجاح! جميع القيود متوازنة'))
        else:
            self.stdout.write(self.style.ERROR('يوجد خلل في القيود المحاسبية!'))
        self.stdout.write('=' * 50)
        self.stdout.write(f'المخازن: {Warehouse.objects.count()}')
        self.stdout.write(f'الأصناف: {Item.objects.count()}')
        self.stdout.write(f'القيود: {entries.count()}')
        self.stdout.write(f'حركات المخزون: {StockMovement.objects.count()}')
        self.stdout.write(f'سجلات الأستاذ: {ItemLedger.objects.count()}')
