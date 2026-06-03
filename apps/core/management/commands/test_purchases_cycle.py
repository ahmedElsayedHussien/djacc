from datetime import date
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from apps.core.models import Account, FiscalYear, JournalEntry, JournalLine, TaxType
from apps.inventory.models import (
    Warehouse, ItemCategory, UnitOfMeasure, Item, ItemLedger, StockMovement,
    StockVoucher, StockVoucherLine,
)
from apps.inventory.services import StockVoucherService
from apps.treasury.models import CashBox
from apps.purchases.models import (
    Supplier, PurchaseInvoice, PurchaseInvoiceLine,
    PurchaseReturn, PurchaseReturnLine,
    SupplierPayment, PaymentAllocation,
)
from apps.purchases.services import PurchaseService, SupplierService

class Command(BaseCommand):
    help = 'اختبار دورة مشتريات كاملة'

    def print_entry(self, e, indent=4):
        lines = e.lines.all()
        total_dr = sum((l.debit or 0) for l in lines)
        total_cr = sum((l.credit or 0) for l in lines)
        status = '✓' if total_dr == total_cr else '✗'
        self.stdout.write(f"{' ' * indent}{status} قيد #{e.id} | {e.date} | {e.description}")
        for line in lines:
            dr_str = f'{line.debit:>8}' if line.debit else '       0'
            cr_str = f'{line.credit:>8}' if line.credit else '       0'
            self.stdout.write(f"{' ' * (indent + 2)}{line.account.code} {line.account.name}: مدين={dr_str} دائن={cr_str}")
        self.stdout.write(f"{' ' * (indent + 2)}── المجموع: مدين={total_dr} دائن={total_cr}")

    def handle(self, *args, **options):
        today = date.today()
        User = get_user_model()
        admin = User.objects.filter(is_superuser=True).first()
        if not admin:
            self.stdout.write(self.style.ERROR('لا يوجد مستخدم superuser'))
            return

        # ==================== CLEANUP ====================
        from apps.purchases.models import PurchaseReturnLine
        from apps.inventory.models import (
            StockVoucherLine, StockVoucher, WarehouseTransferLine, WarehouseTransfer,
            LoadingOrderLine, LoadingOrder,
        )
        from apps.sales.models import SalesInvoiceLine, SalesInvoice, SalesReturnLine, SalesReturn, CustomerReceipt, ReceiptAllocation, RepSettlementInvoice, RepDailySettlement
        RepSettlementInvoice.objects.all().delete()
        RepDailySettlement.objects.all().delete()
        ReceiptAllocation.objects.all().delete()
        CustomerReceipt.objects.all().delete()
        SalesReturnLine.objects.all().delete()
        SalesReturn.objects.all().delete()
        SalesInvoiceLine.objects.all().delete()
        SalesInvoice.objects.all().delete()
        PaymentAllocation.objects.all().delete()
        SupplierPayment.objects.all().delete()
        PurchaseReturnLine.objects.all().delete()
        PurchaseReturn.objects.all().delete()
        PurchaseInvoiceLine.objects.all().delete()
        PurchaseInvoice.objects.all().delete()
        Supplier.objects.all().delete()
        from apps.sales.models import Customer
        Customer.objects.all().delete()
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
        JournalLine.objects.filter(entry__entry_type__in=['purchase', 'payment', 'sale', 'receipt']).delete()
        JournalEntry.objects.filter(entry_type__in=['purchase', 'payment', 'sale', 'receipt']).delete()
        self.stdout.write('تم مسح بيانات الاختبار السابقة')

        # ==================== FISCAL YEAR ====================
        fy = FiscalYear.objects.filter(start_date__lte=today, end_date__gte=today).first()
        if not fy:
            fy = FiscalYear.objects.create(
                name=f'سنة مالية {today.year}', start_date=date(today.year, 1, 1),
                end_date=date(today.year, 12, 31), is_closed=False,
            )

        # ==================== ACCOUNTS ====================
        inv_account = Account.objects.get(code='1131')
        wip_account = Account.objects.get(code='1132')
        self.stdout.write(f'مخزون: {inv_account.code}, اعتمادات: {wip_account.code}')

        # ==================== TAX ====================
        vat_type, _ = TaxType.objects.get_or_create(
            name='ضريبة القيمة المضافة 14%',
            defaults={
                'category': TaxType.Category.VAT, 'rate': Decimal('14.00'),
                'account': Account.objects.get(code='21212'),
                'is_active': True,
            }
        )
        self.stdout.write(f'ضريبة: {vat_type.name} (@ {vat_type.rate}%)')

        # ==================== CASH BOX ====================
        main_cash, _ = CashBox.objects.get_or_create(
            code='CASH-MAIN',
            defaults={
                'name': 'الخزينة الرئيسية',
                'account': Account.objects.get(code='111101'),
                'responsible_user': admin, 'is_active': True,
            }
        )
        self.stdout.write(f'خزينة: {main_cash.name}')

        # ==================== WAREHOUSE ====================
        main_wh, _ = Warehouse.objects.get_or_create(
            code='WH-MAIN',
            defaults={'name': 'المخزن الرئيسي', 'gl_account': inv_account, 'is_active': True}
        )

        # ==================== CATEGORIES, UNITS, ITEMS ====================
        cat, _ = ItemCategory.objects.get_or_create(code='1', defaults={'name': 'عام'})
        unit_pc, _ = UnitOfMeasure.objects.get_or_create(code='PC', defaults={'name': 'قطعة'})
        item, _ = Item.objects.get_or_create(code='ITEM-PUR', defaults={
            'name': 'منتج مشتريات', 'category': cat, 'base_unit': unit_pc,
            'inventory_account': inv_account, 'cogs_account': Account.objects.get(code='511'),
            'standard_price': Decimal('150.00'),
        })
        self.stdout.write(f'الصنف: {item.name}')

        # ==================== SUPPLIER ====================
        supplier = SupplierService.create_supplier({
            'name': 'مورد اختبار',
        })
        self.stdout.write(f'المورد: {supplier.name} (حساب {supplier.account.code})')

        # ==================== 1. CREDIT PURCHASE INVOICE ====================
        self.stdout.write('\n===== 1. فاتورة مشتريات آجلة =====')
        pinv = PurchaseInvoice.objects.create(
            date=today, supplier=supplier,
            payment_type=PurchaseInvoice.PaymentType.CREDIT,
            due_date=today, status=PurchaseInvoice.Status.DRAFT,
            subtotal=Decimal('0'), discount_amount=Decimal('0'),
            tax_amount=Decimal('0'), total=Decimal('0'),
            created_by=admin,
        )
        qty = Decimal('20')
        unit_cost = Decimal('80.00')
        line_total = (qty * unit_cost).quantize(Decimal('0.00'))
        line_tax = (line_total * (vat_type.rate / Decimal('100'))).quantize(Decimal('0.00'))
        PurchaseInvoiceLine.objects.create(
            invoice=pinv, item=item, warehouse=main_wh, unit=unit_pc,
            quantity=qty, base_quantity=qty,
            unit_cost=unit_cost, discount_percent=Decimal('0'),
            tax_type=vat_type, tax_percent=vat_type.rate,
            total=(line_total + line_tax).quantize(Decimal('0.00')),
        )
        pinv.subtotal = line_total
        pinv.tax_amount = line_tax
        pinv.total = (line_total + line_tax).quantize(Decimal('0.00'))
        pinv.save()

        PurchaseService.post_invoice(pinv, admin)
        self.stdout.write(f'  تم ترحيل فاتورة آجلة: {pinv.number} بقيمة ${pinv.total}')

        led = ItemLedger.objects.get(item=item, warehouse=main_wh)
        self.stdout.write(f'  المخزون: {led.quantity_on_hand} × ${led.total_value}')
        self.stdout.write(f'  (توقع: 20 وحدة @ $80 = $1,600)')

        # ==================== 2. CASH PURCHASE INVOICE ====================
        self.stdout.write('\n===== 2. فاتورة مشتريات نقدية =====')
        pinv2 = PurchaseInvoice.objects.create(
            date=today, supplier=supplier,
            payment_type=PurchaseInvoice.PaymentType.CASH,
            payment_method='cash', cash_box=main_cash,
            due_date=today, status=PurchaseInvoice.Status.DRAFT,
            subtotal=Decimal('0'), discount_amount=Decimal('0'),
            tax_amount=Decimal('0'), total=Decimal('0'),
            created_by=admin,
        )
        qty2 = Decimal('10')
        line_total2 = (qty2 * unit_cost).quantize(Decimal('0.00'))
        line_tax2 = (line_total2 * (vat_type.rate / Decimal('100'))).quantize(Decimal('0.00'))
        PurchaseInvoiceLine.objects.create(
            invoice=pinv2, item=item, warehouse=main_wh, unit=unit_pc,
            quantity=qty2, base_quantity=qty2,
            unit_cost=unit_cost, discount_percent=Decimal('0'),
            tax_type=vat_type, tax_percent=vat_type.rate,
            total=(line_total2 + line_tax2).quantize(Decimal('0.00')),
        )
        pinv2.subtotal = line_total2
        pinv2.tax_amount = line_tax2
        pinv2.total = (line_total2 + line_tax2).quantize(Decimal('0.00'))
        pinv2.save()

        PurchaseService.post_invoice(pinv2, admin)
        self.stdout.write(f'  تم ترحيل فاتورة نقدية: {pinv2.number} بقيمة ${pinv2.total}')
        self.stdout.write(f'  (تم إنشاء سند صرف تلقائي)')

        led2 = ItemLedger.objects.get(item=item, warehouse=main_wh)
        self.stdout.write(f'  المخزون: {led2.quantity_on_hand} × ${led2.total_value}')
        self.stdout.write(f'  (توقع: 30 وحدة @ $80 = $2,400)')

        # ==================== 3. PAYMENT FOR CREDIT INVOICE ====================
        self.stdout.write('\n===== 3. سند صرف =====')
        pay = SupplierPayment.objects.create(
            date=today, supplier=supplier, amount=pinv.total,
            payment_method='cash', cash_box=main_cash,
            reference=f'سداد {pinv.number}', created_by=admin,
        )
        PaymentAllocation.objects.create(payment=pay, invoice=pinv, amount=pinv.total)
        PurchaseService.record_payment(pay, admin)
        self.stdout.write(f'  تم ترحيل سند الصرف: {pay.number} بقيمة ${pay.amount}')

        pinv.refresh_from_db()
        self.stdout.write(f'  المبلغ المدفوع: ${pinv.paid_amount}')
        self.stdout.write(f'  (توقع: ${pinv.total} — تم السداد بالكامل)')

        # ==================== 4. PURCHASE RETURN ====================
        self.stdout.write('\n===== 4. مرتجع مشتريات =====')
        ret_qty = Decimal('3')
        ret_line_total = (ret_qty * unit_cost).quantize(Decimal('0.00'))
        ret_tax = (ret_line_total * (vat_type.rate / Decimal('100'))).quantize(Decimal('0.00'))

        pret = PurchaseReturn.objects.create(
            date=today, invoice=pinv, supplier=supplier,
            status=PurchaseReturn.Status.DRAFT,
            subtotal=ret_line_total, discount_amount=Decimal('0.00'),
            tax_amount=ret_tax, total=(ret_line_total + ret_tax).quantize(Decimal('0.00')),
            created_by=admin,
        )
        PurchaseReturnLine.objects.create(
            purchase_return=pret, item=item, warehouse=main_wh, unit=unit_pc,
            quantity=ret_qty, base_quantity=ret_qty,
            unit_cost=unit_cost, discount_percent=Decimal('0'),
            tax_type=vat_type, tax_percent=vat_type.rate,
            total=(ret_line_total + ret_tax).quantize(Decimal('0.00')),
        )
        PurchaseService.post_return(pret, admin)
        self.stdout.write(f'  تم ترحيل مرتجع: {pret.number} بقيمة ${pret.total}')

        led3 = ItemLedger.objects.get(item=item, warehouse=main_wh)
        self.stdout.write(f'  المخزون بعد المرتجع: {led3.quantity_on_hand}')
        self.stdout.write(f'  (توقع: 27 — 30 ناقص 3)')

        # ==================== VERIFICATION ====================
        self.stdout.write('\n' + '=' * 60)
        all_entries = JournalEntry.objects.filter(
            entry_type__in=['purchase', 'payment']
        ).order_by('date', 'id')
        self.stdout.write(f'\nالقيود المحاسبية ({all_entries.count()}):')
        balanced = 0
        for e in all_entries:
            self.print_entry(e)
            if sum((l.debit or 0) for l in e.lines.all()) == sum((l.credit or 0) for l in e.lines.all()):
                balanced += 1

        self.stdout.write(f'\nالقيود المتوازنة: {balanced}/{all_entries.count()}')

        self.stdout.write(f'\nحركات المخزون ({StockMovement.objects.count()}):')
        for m in StockMovement.objects.all().order_by('date', 'id'):
            self.stdout.write(f'  {m.movement_type}: {m.item.name} {m.quantity} @ ${m.unit_cost} → {m.warehouse.name}')

        self.stdout.write(f'\nحسابات الموردين:')
        for inv in [pinv, pinv2]:
            inv.refresh_from_db()
            self.stdout.write(f'  {inv.number}: total=${inv.total} paid=${inv.paid_amount} status={inv.status}')

        if balanced == all_entries.count() and all_entries.count() > 0:
            self.stdout.write(self.style.SUCCESS('\n✓ تم بنجاح! جميع القيود متوازنة'))
        else:
            self.stdout.write(self.style.ERROR('\n✗ يوجد خلل في القيود المحاسبية!'))
