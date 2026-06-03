from datetime import date
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.conf import settings

from apps.core.models import Account, FiscalYear, JournalEntry, JournalLine, TaxType
from apps.core.services import DocumentService
from apps.inventory.models import Warehouse, ItemCategory, UnitOfMeasure, Item, ItemLedger, StockMovement
from apps.inventory.services import InventoryService, StockVoucherService
from apps.inventory.models import StockVoucher, StockVoucherLine
from apps.treasury.models import CashBox, BankAccount, MobileWallet
from apps.treasury.services import TreasuryService
from apps.sales.models import SalesRepresentative, RepDailySettlement
from apps.pos.models import POSStation, POSSession, POSOrder, POSOrderLine, POSPayment
from apps.pos.services import POSCheckoutService, POSSessionService

class Command(BaseCommand):
    help = 'اختبار دورة نقاط البيع كاملة'

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
        from apps.purchases.models import PurchaseInvoice, PurchaseInvoiceLine, PurchaseReturn, PurchaseReturnLine
        from apps.sales.models import SalesInvoice, SalesInvoiceLine, SalesReturn, SalesReturnLine
        from apps.inventory.models import StockVoucherLine, StockVoucher, WarehouseTransferLine, WarehouseTransfer
        POSPayment.objects.all().delete()
        POSOrderLine.objects.all().delete()
        POSOrder.objects.all().delete()
        POSSession.objects.all().delete()
        POSStation.objects.all().delete()
        RepDailySettlement.objects.all().delete()
        for m in [PurchaseReturnLine, PurchaseReturn, PurchaseInvoiceLine, PurchaseInvoice,
                  SalesReturnLine, SalesReturn, SalesInvoiceLine, SalesInvoice]:
            m.objects.all().delete()
        SalesRepresentative.objects.all().delete()
        for m in [StockMovement, ItemLedger, StockVoucherLine, StockVoucher,
                  WarehouseTransferLine, WarehouseTransfer,
                  Item, UnitOfMeasure, ItemCategory, Warehouse]:
            m.objects.all().delete()
        JournalLine.objects.filter(entry__entry_type__in=['sale', 'receipt', 'inventory']).delete()
        JournalEntry.objects.filter(entry_type__in=['sale', 'receipt', 'inventory']).delete()
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
        revenue_account = Account.objects.get(code='411')
        cogs_account = Account.objects.get(code='511')
        cashbox_account = Account.objects.get(code='111101')
        bank_gl_account = Account.objects.get(code='111201')
        vat_output_account = Account.objects.get(code='21211')
        shortage_account = Account.objects.get(code='544')
        self.stdout.write(f'حسابات: مخزون={inv_account.code} إيراد={revenue_account.code} '
                          f'تكلفة={cogs_account.code} خزينة={cashbox_account.code} '
                          f'بنك={bank_gl_account.code} ضريبة مخرجات={vat_output_account.code}')

        # ==================== TAX ====================
        vat_type, _ = TaxType.objects.get_or_create(
            name='ضريبة القيمة المضافة 14%',
            defaults={
                'category': TaxType.Category.VAT,
                'rate': Decimal('14.00'),
                'account': vat_output_account,
                'is_active': True,
            }
        )
        self.stdout.write(f'ضريبة: {vat_type.name} (@ {vat_type.rate}%)')

        # ==================== WAREHOUSE ====================
        wh, _ = Warehouse.objects.get_or_create(
            code='WH-POS',
            defaults={'name': 'مخزن نقاط البيع', 'gl_account': inv_account, 'is_active': True}
        )

        # ==================== CATEGORIES, UNITS, ITEMS ====================
        cat, _ = ItemCategory.objects.get_or_create(code='POS-CAT', defaults={'name': 'أصناف POS'})
        unit_pc, _ = UnitOfMeasure.objects.get_or_create(code='POS-PC', defaults={'name': 'قطعة'})

        item1, _ = Item.objects.get_or_create(code='POS-ITEM-001', defaults={
            'name': 'منتج POS 1', 'category': cat, 'base_unit': unit_pc,
            'inventory_account': inv_account, 'cogs_account': cogs_account,
            'sales_account': revenue_account,
            'standard_price': Decimal('50.00'),
        })
        item2, _ = Item.objects.get_or_create(code='POS-ITEM-002', defaults={
            'name': 'منتج POS 2', 'category': cat, 'base_unit': unit_pc,
            'inventory_account': inv_account, 'cogs_account': cogs_account,
            'sales_account': revenue_account,
            'standard_price': Decimal('100.00'),
        })
        self.stdout.write(f'الأصناف: {item1.name} (@ ${item1.standard_price}), '
                          f'{item2.name} (@ ${item2.standard_price})')

        # Opening stock: 50 units each @ $30
        voucher = StockVoucher.objects.create(
            number='VCH-OPEN-POS', date=today,
            voucher_type=StockVoucher.VoucherType.RECEIPT,
            warehouse=wh, offset_account=inv_account,
            notes='رصيد افتتاحي POS', created_by=admin,
        )
        StockVoucherLine.objects.create(voucher=voucher, item=item1, quantity=50, unit_cost=Decimal('30.00'))
        StockVoucherLine.objects.create(voucher=voucher, item=item2, quantity=50, unit_cost=Decimal('30.00'))
        StockVoucherService.post_voucher(voucher, admin)
        for itm in [item1, item2]:
            led = ItemLedger.objects.get(item=itm, warehouse=wh)
            self.stdout.write(f'  {itm.name}: الكمية={led.quantity_on_hand} × القيمة=${led.total_value}')

        # ==================== CASH BOX + BANK ====================
        pos_cashbox, _ = CashBox.objects.get_or_create(
            account=cashbox_account,
            defaults={
                'code': 'CASH-POS', 'name': 'خزينة POS',
                'responsible_user': admin, 'is_active': True,
            }
        )
        pos_bank = BankAccount.objects.filter(account=bank_gl_account).first()
        if not pos_bank:
            pos_bank = BankAccount.objects.create(
                code='BANK-POS', name='حساب بنك POS',
                bank_name='بنك اختبار', account_number='POS-12345',
                account=bank_gl_account,
            )
        self.stdout.write(f'خزينة: {pos_cashbox.name} | بنك: {pos_bank.name} (حساب {bank_gl_account.code})')

        # ==================== POS STATION ====================
        station = POSStation.objects.create(
            code='ST-001', name='نقطة بيع اختبار',
            warehouse=wh, cash_box=pos_cashbox, bank_account=pos_bank,
            is_active=True,
        )
        self.stdout.write(f'نقطة البيع: {station.name}')

        # ==================== 1. OPEN SESSION ====================
        self.stdout.write('\n===== 1. فتح وردية =====')
        session = POSSessionService.open_session(
            user=admin, station=station, opening_cash=Decimal('500.00')
        )
        self.stdout.write(f'  الوردية #{session.id} مفتوحة (عهدة: ${session.opening_cash})')

        # ==================== 2. CHECKOUT CASH ====================
        self.stdout.write('\n===== 2. فاتورة نقدية (كاش) =====')
        cart_cash = [
            {'id': item1.id, 'qty': 3, 'price': 60.00, 'unit_type': 'base'},
            {'id': item2.id, 'qty': 2, 'price': 120.00, 'unit_type': 'base'},
        ]
        order1 = POSCheckoutService.create_order(
            session=session, cart_items=cart_cash,
            payment_method='cash', customer_id=None, is_taxable=True,
        )
        self.stdout.write(f'  الفاتورة: {order1.receipt_number} — الإجمالي=${order1.grand_total}')
        self.stdout.write(f'  (متوقع: 3×$60={(3*60):.2f} + 2×$120={(2*120):.2f} = ${3*60+2*120:.2f} شامل الضريبة)')

        session.refresh_from_db()
        self.stdout.write(f'  النقدية المتوقعة: ${session.expected_cash} (عهدة ${500} + مبيعات ${order1.grand_total})')

        # ==================== 3. CHECKOUT CARD ====================
        self.stdout.write('\n===== 3. فاتورة شبكة (بطاقة) =====')
        cart_card = [
            {'id': item1.id, 'qty': 1, 'price': 55.00, 'unit_type': 'base'},
        ]
        order2 = POSCheckoutService.create_order(
            session=session, cart_items=cart_card,
            payment_method='card', customer_id=None, is_taxable=True,
        )
        self.stdout.write(f'  الفاتورة: {order2.receipt_number} — الإجمالي=${order2.grand_total}')

        # ==================== 4. CANCEL ORDER ====================
        self.stdout.write('\n===== 4. إلغاء فاتورة =====')
        order3 = POSCheckoutService.create_order(
            session=session,
            cart_items=[{'id': item1.id, 'qty': 1, 'price': 70.00, 'unit_type': 'base'}],
            payment_method='cash', customer_id=None, is_taxable=True,
        )
        self.stdout.write(f'  تم إنشاء فاتورة للإلغاء: {order3.receipt_number}')
        POSCheckoutService.cancel_order(order3, admin)
        self.stdout.write(f'  تم إلغاء الفاتورة بنجاح')
        order3.refresh_from_db()
        self.stdout.write(f'  الحالة: {order3.status}')

        session.refresh_from_db()
        self.stdout.write(f'  النقدية المتوقعة بعد الإلغاء: ${session.expected_cash}')

        # ==================== VERIFY STOCK ====================
        self.stdout.write('\n===== التحقق من المخزون =====')
        for itm in [item1, item2]:
            led = ItemLedger.objects.get(item=itm, warehouse=wh)
            self.stdout.write(f'  {itm.name}: الكمية={led.quantity_on_hand}')

        # ==================== 5. CLOSE SESSION ====================
        self.stdout.write('\n===== 5. إغلاق الوردية =====')

        def check(label, code, expected):
            acc = Account.objects.get(code=code)
            bal = Account.objects.get(pk=acc.pk).get_balance(today)
            status = '✓' if bal == expected else '✗'
            self.stdout.write(f'  {status} {label}: ${bal} (متوقع: ${expected})')
            return bal == expected

        all_ok = True
        session.refresh_from_db()
        expected_cash = session.expected_cash
        self.stdout.write(f'  النقدية المتوقعة: ${expected_cash}')
        closed_session = POSSessionService.close_session(session, actual_cash=expected_cash, notes='غلق اختبار')
        self.stdout.write(f'  الوردية مغلقة — الفرق: ${closed_session.difference}')
        self.stdout.write(f'  حالة الوردية: {closed_session.status}')

        sale_entries = JournalEntry.objects.filter(entry_type='sale').order_by('date', 'id')
        self.stdout.write(f'\n  ---- قيد المبيعات ----')
        entry = sale_entries.first()
        self.print_entry(entry)

        all_ok &= sum((l.debit or 0) for l in entry.lines.all()) == sum((l.credit or 0) for l in entry.lines.all())

        for o in POSOrder.objects.filter(session=session):
            self.stdout.write(f'  الفاتورة {o.receipt_number}: {o.status}')

        # ==================== 6. RETURN + REFUND (separate session) ====================
        self.stdout.write('\n===== 6. مرتجع جزئي في وردية منفصلة =====')
        session_r = POSSessionService.open_session(
            user=admin, station=station, opening_cash=Decimal('200.00')
        )
        order_r = POSCheckoutService.create_order(
            session=session_r,
            cart_items=[{'id': item1.id, 'qty': 3, 'price': 60.00, 'unit_type': 'base'}],
            payment_method='cash', customer_id=None, is_taxable=True,
        )
        self.stdout.write(f'  الفاتورة: {order_r.receipt_number} — ${order_r.grand_total}')

        # partial return of 1 unit
        line_r = order_r.lines.filter(item=item1).first()
        refund = POSCheckoutService.return_items(order_r, [{'line_id': line_r.id, 'qty': 1}], admin)
        self.stdout.write(f'  مرتجع قطعة: ${refund}')

        session_r.refresh_from_db()
        expected_r = session_r.expected_cash
        self.stdout.write(f'  النقدية المتوقعة: ${expected_r} (200 + 180 - 60 = 320)')
        POSSessionService.close_session(session_r, actual_cash=expected_r, notes='غلق مع مرتجع')
        session_r.refresh_from_db()
        self.stdout.write(f'  الوردية مغلقة — الفرق: ${session_r.difference}')

        sale_entry2 = JournalEntry.objects.filter(entry_type='sale').order_by('-id').first()
        if sale_entry2 and sale_entry2.id != entry.id:
            self.stdout.write(f'  قيد الوردية الثانية:')
            self.print_entry(sale_entry2)

        # ==================== 7. SHORTAGE + COLLECTION ====================
        self.stdout.write('\n===== 7. تحصيل عجز =====')
        session3 = POSSessionService.open_session(
            user=admin, station=station, opening_cash=Decimal('100.00')
        )
        order_s = POSCheckoutService.create_order(
            session=session3,
            cart_items=[{'id': item1.id, 'qty': 2, 'price': 60.00, 'unit_type': 'base'}],
            payment_method='cash', customer_id=None, is_taxable=True,
        )
        self.stdout.write(f'  فاتورة ${order_s.grand_total}')

        session3.refresh_from_db()
        self.stdout.write(f'  النقدية المتوقعة: ${session3.expected_cash}')
        POSSessionService.close_session(session3, actual_cash=Decimal('200.00'), notes='غلق بعجز $20')
        session3.refresh_from_db()
        self.stdout.write(f'  الوردية مغلقة — العجز: ${session3.difference}')

        short_entry = POSSessionService.collect_shortage(session3, admin)
        self.stdout.write(f'  قيد تحصيل العجز #{short_entry.id}')
        self.print_entry(short_entry)
        session3.refresh_from_db()
        self.stdout.write(f'  تم التحصيل في: {session3.shortage_collected_at}')
        all_ok &= short_entry is not None

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

        self.stdout.write(f'\nالورديات:')
        for s in POSSession.objects.all().order_by('start_time'):
            self.stdout.write(f'  #{s.id}: status={s.status}, opening=${s.opening_cash}, '
                              f'expected=${s.expected_cash}, actual=${s.actual_cash}, diff=${s.difference}')

        if balanced == all_entries.count() and all_entries.count() > 0:
            self.stdout.write(self.style.SUCCESS('\n✓ تم بنجاح! جميع القيود متوازنة'))
        else:
            self.stdout.write(self.style.ERROR('\n✗ يوجد خلل في القيود المحاسبية!'))
