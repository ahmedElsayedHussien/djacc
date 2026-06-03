from datetime import date
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.conf import settings

from apps.core.models import Account, FiscalYear, JournalEntry, JournalLine, TaxType
from apps.core.services import DocumentService
from apps.inventory.models import (
    Warehouse, ItemCategory, UnitOfMeasure, Item, ItemLedger, StockMovement
)
from apps.inventory.services import InventoryService
from apps.treasury.models import CashBox
from apps.sales.models import (
    Customer, SalesRepresentative, PriceList,
    SalesInvoice, SalesInvoiceLine, SalesReturn, SalesReturnLine,
    CustomerReceipt, ReceiptAllocation,
    RepDailySettlement, RepSettlementInvoice
)
from apps.sales.services import SalesService, RepSettlementService, CustomerService

class Command(BaseCommand):
    help = 'اختبار دورة بيع كاملة'

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
        from apps.inventory.models import (
            StockVoucherLine, StockVoucher, WarehouseTransferLine, WarehouseTransfer,
            LoadingOrderLine, LoadingOrder,
        )
        from apps.purchases.models import PurchaseInvoiceLine, PurchaseInvoice, PurchaseReturnLine, PurchaseReturn, SupplierPayment, PaymentAllocation
        PurchaseReturnLine.objects.all().delete()
        PurchaseReturn.objects.all().delete()
        PaymentAllocation.objects.all().delete()
        SupplierPayment.objects.all().delete()
        PurchaseInvoiceLine.objects.all().delete()
        PurchaseInvoice.objects.all().delete()
        RepSettlementInvoice.objects.all().delete()
        for m in [StockMovement, ItemLedger, StockVoucherLine, StockVoucher,
                  WarehouseTransferLine, WarehouseTransfer, LoadingOrderLine, LoadingOrder,
                  CustomerReceipt, ReceiptAllocation,
                  RepDailySettlement,
                  SalesReturnLine, SalesReturn, SalesInvoiceLine, SalesInvoice,
                  Item, UnitOfMeasure, ItemCategory, PriceList, Customer]:
            m.objects.all().delete()
        JournalLine.objects.all().delete()
        JournalEntry.objects.all().delete()
        self.stdout.write('تم مسح بيانات الاختبار السابقة')

        # ==================== FISCAL YEAR ====================
        fy = FiscalYear.objects.filter(start_date__lte=today, end_date__gte=today).first()
        if not fy:
            fy = FiscalYear.objects.create(
                name=f'سنة مالية {today.year}', start_date=date(today.year, 1, 1),
                end_date=date(today.year, 12, 31), is_closed=False,
            )
            self.stdout.write(f'تم إنشاء السنة المالية: {fy.name}')

        # ==================== ACCOUNTS ====================
        inv_account = Account.objects.get(code='1131')
        revenue_account = Account.objects.get(code='411')
        cogs_account = Account.objects.get(code='511')
        discount_account = Account.objects.get(code='414')
        returns_account = Account.objects.get(code='413')
        customer_ar = Account.objects.get(code='1121')
        self.stdout.write(f'حسابات: مخزون={inv_account.code} إيراد={revenue_account.code} '
                          f'تكلفة={cogs_account.code} خصم={discount_account.code} '
                          f'مردودات={returns_account.code} عملاء={customer_ar.code}')

        # ==================== TAX ====================
        vat_type, _ = TaxType.objects.get_or_create(
            name='ضريبة القيمة المضافة 14%',
            defaults={
                'category': TaxType.Category.VAT,
                'rate': Decimal('14.00'),
                'account': Account.objects.get(code='21211'),
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
                'responsible_user': admin,
                'is_active': True,
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
        item1, _ = Item.objects.get_or_create(code='ITEM-001', defaults={
            'name': 'منتج اختبار', 'category': cat, 'base_unit': unit_pc,
            'inventory_account': inv_account, 'cogs_account': cogs_account,
            'standard_price': Decimal('150.00'),
        })
        self.stdout.write(f'الصنف: {item1.name} (@ ${item1.standard_price})')

        # Opening stock: 100 units @ $100
        from apps.inventory.services import StockVoucherService
        from apps.inventory.models import StockVoucher, StockVoucherLine
        voucher = StockVoucher.objects.create(
            number='VCH-OPEN-SALES', date=today,
            voucher_type=StockVoucher.VoucherType.RECEIPT,
            warehouse=main_wh, offset_account=inv_account,
            notes='رصيد افتتاحي للمبيعات', created_by=admin,
        )
        StockVoucherLine.objects.create(voucher=voucher, item=item1, quantity=100, unit_cost=Decimal('100.00'))
        StockVoucherService.post_voucher(voucher, admin)
        led = ItemLedger.objects.get(item=item1, warehouse=main_wh)
        self.stdout.write(f'المخزون الافتتاحي: {led.quantity_on_hand} × ${led.total_value}')

        # ==================== CUSTOMER ====================
        customer = CustomerService.create_customer({
            'name': 'عميل اختبار',
            'is_taxable': True,
            'customer_type': 'individual',
        })
        self.stdout.write(f'العميل: {customer.name} (حساب {customer.account.code})')

        # ==================== SALES REP ====================
        rep = SalesRepresentative.objects.first()
        self.stdout.write(f'مندوب المبيعات: {rep.name if rep else "---"}')

        # ==================== 1. CREDIT INVOICE ====================
        self.stdout.write('\n===== 1. فاتورة آجلة =====')
        inv_credit = SalesInvoice.objects.create(
            number='SINV-CREDIT-001', date=today,
            customer=customer, sales_rep=rep,
            payment_type=SalesInvoice.PaymentType.CREDIT,
            due_date=today, status=SalesInvoice.Status.DRAFT,
            subtotal=Decimal('0'), discount_amount=Decimal('0'),
            tax_amount=Decimal('0'), total=Decimal('0'),
            created_by=admin,
        )
        line_qty = Decimal('10')
        line_price = Decimal('120.00')
        line_total = line_qty * line_price  # 1200
        line_tax = line_total * (vat_type.rate / Decimal('100'))  # 168
        inv_line = SalesInvoiceLine.objects.create(
            invoice=inv_credit,
            item=item1, warehouse=main_wh, unit=unit_pc,
            quantity=line_qty, base_quantity=line_qty,
            unit_price=line_price, discount_percent=Decimal('0'),
            tax_type=vat_type, tax_percent=vat_type.rate,
            total=(line_total + line_tax).quantize(Decimal('0.01')),
            cost=Decimal('0'), revenue_account=revenue_account,
            cost_of_goods_account=cogs_account,
        )
        inv_credit.subtotal = line_total.quantize(Decimal('0.01'))
        inv_credit.tax_amount = line_tax.quantize(Decimal('0.01'))
        inv_credit.total = (line_total + line_tax).quantize(Decimal('0.01'))
        inv_credit.save()

        SalesService.post_invoice(inv_credit, admin)
        self.stdout.write(f'  تم ترحيل فاتورة آجلة: {inv_credit.number} بقيمة ${inv_credit.total}')

        led_after = ItemLedger.objects.get(item=item1, warehouse=main_wh)
        self.stdout.write(f'  المخزون بعد الفاتورة: {led_after.quantity_on_hand}')
        self.stdout.write(f'  (توقع: 90 — 100 ناقص 10)')

        # ==================== 2. CASH INVOICE ====================
        self.stdout.write('\n===== 2. فاتورة نقدية =====')
        inv_cash = SalesInvoice.objects.create(
            number='SINV-CASH-001', date=today,
            customer=customer, sales_rep=rep,
            payment_type=SalesInvoice.PaymentType.CASH,
            cash_box=main_cash,
            due_date=today, status=SalesInvoice.Status.DRAFT,
            subtotal=Decimal('0'), discount_amount=Decimal('0'),
            tax_amount=Decimal('0'), total=Decimal('0'),
            created_by=admin,
        )
        cash_qty = Decimal('5')
        cash_line_total = cash_qty * line_price  # 600
        cash_tax = cash_line_total * (vat_type.rate / Decimal('100'))  # 84
        SalesInvoiceLine.objects.create(
            invoice=inv_cash,
            item=item1, warehouse=main_wh, unit=unit_pc,
            quantity=cash_qty, base_quantity=cash_qty,
            unit_price=line_price, discount_percent=Decimal('0'),
            tax_type=vat_type, tax_percent=vat_type.rate,
            total=(cash_line_total + cash_tax).quantize(Decimal('0.01')),
            cost=Decimal('0'), revenue_account=revenue_account,
            cost_of_goods_account=cogs_account,
        )
        inv_cash.subtotal = cash_line_total.quantize(Decimal('0.01'))
        inv_cash.tax_amount = cash_tax.quantize(Decimal('0.01'))
        inv_cash.total = (cash_line_total + cash_tax).quantize(Decimal('0.01'))
        inv_cash.save()

        SalesService.post_invoice(inv_cash, admin)
        self.stdout.write(f'  تم ترحيل فاتورة نقدية: {inv_cash.number} بقيمة ${inv_cash.total}')
        self.stdout.write(f'  (تم إنشاء سند قبض تلقائي للفاتورة النقدية)')

        led_after2 = ItemLedger.objects.get(item=item1, warehouse=main_wh)
        self.stdout.write(f'  المخزون بعد الفاتورتين: {led_after2.quantity_on_hand}')
        self.stdout.write(f'  (توقع: 85 — 90 ناقص 5)')

        # ==================== 3. RECEIPT FOR CREDIT INVOICE ====================
        self.stdout.write('\n===== 3. سند قبض =====')
        receipt = CustomerReceipt.objects.create(
            number='RCPT-001', date=today,
            customer=customer, amount=inv_credit.total,
            payment_method='cash', cash_box=main_cash,
            reference=f'سداد {inv_credit.number}',
        )
        ReceiptAllocation.objects.create(
            receipt=receipt, invoice=inv_credit, amount=inv_credit.total,
        )
        SalesService.record_receipt(receipt, admin)
        self.stdout.write(f'  تم ترحيل سند القبض: {receipt.number} بقيمة ${receipt.amount}')

        inv_credit.refresh_from_db()
        self.stdout.write(f'  المبلغ المدفوع للفاتورة الآجلة: ${inv_credit.paid_amount}')
        self.stdout.write(f'  (توقع: ${inv_credit.total} — تم السداد بالكامل)')

        # ==================== 4. SALES RETURN ====================
        self.stdout.write('\n===== 4. مرتجع مبيعات =====')
        ret_qty = Decimal('2')
        ret_unit_price = line_price
        ret_line_total = (ret_qty * ret_unit_price).quantize(Decimal('0.00'))
        ret_tax = (ret_line_total * (vat_type.rate / Decimal('100'))).quantize(Decimal('0.00'))
        ret_line_cost = ret_qty * Decimal('100')

        sales_return = SalesReturn.objects.create(
            number='RET-001', date=today,
            invoice=inv_credit, customer=customer, sales_rep=rep,
            payment_type='credit',
            status=SalesReturn.Status.DRAFT,
            subtotal=ret_line_total, discount_amount=Decimal('0.00'),
            tax_amount=ret_tax, total=(ret_line_total + ret_tax).quantize(Decimal('0.00')),
            created_by=admin,
        )
        SalesReturnLine.objects.create(
            sales_return=sales_return,
            item=item1, warehouse=main_wh, unit=unit_pc,
            quantity=ret_qty, base_quantity=ret_qty,
            unit_price=ret_unit_price, discount_percent=Decimal('0'),
            tax_type=vat_type, tax_percent=vat_type.rate,
            total=(ret_line_total + ret_tax).quantize(Decimal('0.00')),
            cost=Decimal('100'), return_account=returns_account,
            cogs_account=cogs_account,
        )
        SalesService.post_return(sales_return, admin)
        self.stdout.write(f'  تم ترحيل مرتجع: {sales_return.number} بقيمة ${sales_return.total}')

        led_after3 = ItemLedger.objects.get(item=item1, warehouse=main_wh)
        self.stdout.write(f'  المخزون بعد المرتجع: {led_after3.quantity_on_hand}')
        self.stdout.write(f'  (توقع: 87 — 85 زائد 2)')

        # ==================== 5. REP SETTLEMENT ====================
        self.stdout.write('\n===== 5. تسوية مندوب =====')
        if rep:
            settlement = RepDailySettlement.objects.create(
                number='SETTLE-001', date=today,
                sales_rep=rep,
                total_sales=Decimal('0'), cash_delivered=Decimal('0'),
                difference=Decimal('0'), notes='تسوية اختبار',
                created_by=admin,
            )
            # Add invoices to settlement (cash-only invoices)
            RepSettlementInvoice.objects.create(settlement=settlement, invoice=inv_cash)
            settlement.calculate_totals()
            settlement.cash_delivered = settlement.total_sales  # rep delivered all cash
            settlement.to_cash_box = main_cash
            settlement.save()

            self.stdout.write(f'  إجمالي مبيعات التسوية: ${settlement.total_sales}')
            if settlement.total_sales == Decimal('0'):
                self.stdout.write(self.style.WARNING('  لم يتم إضافة الفاتورة النقدية للتسوية — قد تم استخدامها مسبقاً في تسوية أخرى'))
            else:
                # Post settlement
                entry = RepSettlementService.post_settlement(settlement, admin)
                self.stdout.write(f'  تم ترحيل التسوية: {settlement.number} (قيد #{entry.id})')
        else:
            self.stdout.write('  (تم تخطي — لا يوجد مندوب مبيعات)')

        # ==================== VERIFICATION ====================
        self.stdout.write('\n' + '=' * 60)
        all_entries = JournalEntry.objects.filter(
            entry_type__in=['sale', 'receipt']
        ).order_by('date', 'id')
        self.stdout.write(f'\nالقيود المحاسبية ({all_entries.count()}):')
        balanced = 0
        for e in all_entries:
            self.print_entry(e)
            lines = e.lines.all()
            if sum((l.debit or 0) for l in lines) == sum((l.credit or 0) for l in lines):
                balanced += 1

        self.stdout.write(f'\nالقيود المتوازنة: {balanced}/{all_entries.count()}')

        self.stdout.write(f'\nحركات المخزون ({StockMovement.objects.count()}):')
        for m in StockMovement.objects.all().order_by('date', 'id'):
            self.stdout.write(f'  {m.movement_type}: {m.item.name} {m.quantity} @ ${m.unit_cost} → {m.warehouse.name}')

        self.stdout.write(f'\nحسابات العملاء:')
        for inv in [inv_credit, inv_cash]:
            inv.refresh_from_db()
            self.stdout.write(f'  {inv.number}: total=${inv.total} paid=${inv.paid_amount} status={inv.status}')

        if balanced == all_entries.count() and all_entries.count() > 0:
            self.stdout.write(self.style.SUCCESS('\n✓ تم بنجاح! جميع القيود متوازنة'))
        else:
            self.stdout.write(self.style.ERROR('\n✗ يوجد خلل في القيود المحاسبية!'))
