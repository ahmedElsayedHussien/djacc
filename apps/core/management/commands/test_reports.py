from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.conf import settings

from apps.core.models import Account, FiscalYear, JournalEntry, JournalLine, TaxType
from apps.core.services import JournalService
from apps.inventory.models import (
    Warehouse, ItemCategory, UnitOfMeasure, Item, ItemLedger, StockMovement,
    StockVoucher, StockVoucherLine,
)
from apps.inventory.services import StockVoucherService
from apps.treasury.models import CashBox, BankAccount
from apps.reports.services import ReportService

class Command(BaseCommand):
    help = 'اختبار التقارير المالية الأساسية'

    def handle(self, *args, **options):
        today = date.today()
        fy_start = date(today.year, 1, 1)
        User = get_user_model()
        admin = User.objects.filter(is_superuser=True).first()
        if not admin:
            self.stdout.write(self.style.ERROR('لا يوجد مستخدم superuser'))
            return

        # ==================== CLEANUP ====================
        from apps.sales.models import (
            SalesInvoice, SalesInvoiceLine, SalesReturn, SalesReturnLine,
            Customer, CustomerReceipt, ReceiptAllocation, RepDailySettlement,
        )
        from apps.purchases.models import (
            PurchaseInvoice, PurchaseInvoiceLine, PurchaseReturn, PurchaseReturnLine,
        )
        from apps.expenses.models import Expense
        from apps.hr.models import PayrollPeriod
        from apps.pos.models import POSOrderLine, POSOrder, POSPayment, POSSession, POSStation
        from apps.purchases.models import (
            PurchaseInvoice, PurchaseInvoiceLine, PurchaseReturn, PurchaseReturnLine,
        )
        for m in [
            POSPayment, POSOrderLine, POSOrder, POSSession, POSStation,
            Expense, PayrollPeriod,
            ReceiptAllocation, CustomerReceipt,
            SalesReturnLine, SalesReturn, SalesInvoiceLine, SalesInvoice,
            PurchaseReturnLine, PurchaseReturn, PurchaseInvoiceLine, PurchaseInvoice,
            RepDailySettlement,
        ]:
            m.objects.all().delete()
        for m in [StockMovement, ItemLedger, StockVoucherLine, StockVoucher,
                  Item, UnitOfMeasure, ItemCategory, Warehouse]:
            m.objects.all().delete()
        JournalLine.objects.all().delete()
        JournalEntry.objects.all().delete()
        self.stdout.write('تم مسح بيانات الاختبار السابقة')

        # ==================== FISCAL YEAR ====================
        fy = FiscalYear.objects.filter(start_date__lte=today, end_date__gte=today).first()
        if not fy:
            fy = FiscalYear.objects.create(
                name=f'سنة مالية {today.year}',
                start_date=fy_start, end_date=date(today.year, 12, 31),
                is_closed=False,
            )

        # ==================== ACCOUNTS ====================
        acc = {}
        for code in ['111101', '111201', '1121', '1131',
                     '21211', '2125', '2132', '2133',
                     '31', '411', '511', '5211', '5212']:
            a = Account.objects.get(code=code)
            acc[code] = a
            self.stdout.write(f'  {a.code} {a.name}')

        # ==================== TAX ====================
        vat_type, _ = TaxType.objects.get_or_create(
            name='ضريبة القيمة المضافة 14%',
            defaults={'category': TaxType.Category.VAT, 'rate': Decimal('14.00'),
                      'account': acc['21211'], 'is_active': True},
        )

        # ==================== CASH BOX ====================
        cashbox, _ = CashBox.objects.get_or_create(
            account=acc['111101'],
            defaults={'code': 'CASH-RPT', 'name': 'الخزينة النقدية',
                      'responsible_user': admin, 'is_active': True},
        )

        # ==================== OPENING ENTRIES ====================
        self.stdout.write('\n===== 1. قيود افتتاحية =====')
        JournalService.create_entry(
            date_val=fy_start, entry_type=JournalEntry.EntryType.OPENING,
            description='قيد افتتاحي للسنة المالية',
            lines=[
                {'account': acc['111101'], 'debit': Decimal('10000.00'), 'credit': Decimal('0')},
                {'account': acc['1131'], 'debit': Decimal('5000.00'), 'credit': Decimal('0')},
                {'account': Account.objects.get(code='1121002'), 'debit': Decimal('3000.00'), 'credit': Decimal('0')},
                {'account': acc['31'], 'debit': Decimal('0'), 'credit': Decimal('18000.00')},
            ],
            source_document=None, created_by=admin,
        )
        self.stdout.write('  تم إنشاء القيود الافتتاحية')

        # ==================== WAREHOUSE + ITEMS ====================
        cat, _ = ItemCategory.objects.get_or_create(code='RPT-CAT', defaults={'name': 'أصناف'})
        unit, _ = UnitOfMeasure.objects.get_or_create(code='RPT-PC', defaults={'name': 'قطعة'})
        wh, _ = Warehouse.objects.get_or_create(
            code='WH-RPT', defaults={'name': 'مخزن', 'gl_account': acc['1131'], 'is_active': True},
        )

        item, _ = Item.objects.get_or_create(code='RPT-ITEM', defaults={
            'name': 'منتج', 'category': cat, 'base_unit': unit,
            'inventory_account': acc['1131'], 'cogs_account': acc['511'],
            'standard_price': Decimal('100.00'),
        })

        voucher = StockVoucher.objects.create(
            number='VCH-OPEN-RPT', date=fy_start,
            voucher_type=StockVoucher.VoucherType.RECEIPT,
            warehouse=wh, offset_account=acc['1131'],
            notes='فيد افتتاحي', created_by=admin,
        )
        StockVoucherLine.objects.create(voucher=voucher, item=item, quantity=50, unit_cost=Decimal('100.00'))
        StockVoucherService.post_voucher(voucher, admin)
        led = ItemLedger.objects.get(item=item, warehouse=wh)
        self.stdout.write(f'  المخزون الافتتاحي: {led.quantity_on_hand} × ${led.total_value}')

        # ==================== SALES TRANSACTIONS ====================
        self.stdout.write('\n===== 2. معاملات بيع =====')
        from apps.sales.models import SalesInvoice, SalesInvoiceLine, Customer
        from apps.sales.services import SalesService, CustomerService

        customer = CustomerService.create_customer({
            'name': 'عميل', 'is_taxable': True, 'customer_type': 'individual',
        })
        self.stdout.write(f'  العميل: {customer.name}')

        inv = SalesInvoice.objects.create(
            number='RPT-SINV-001', date=today, customer=customer,
            payment_type=SalesInvoice.PaymentType.CREDIT,
            due_date=today, status=SalesInvoice.Status.DRAFT,
            subtotal=Decimal('0'), discount_amount=Decimal('0'),
            tax_amount=Decimal('0'), total=Decimal('0'),
            created_by=admin,
        )
        line = SalesInvoiceLine.objects.create(
            invoice=inv, item=item, warehouse=wh, unit=unit,
            quantity=Decimal('10'), base_quantity=Decimal('10'),
            unit_price=Decimal('150.00'), discount_percent=Decimal('0'),
            tax_type=vat_type, tax_percent=vat_type.rate,
            total=Decimal('1710.00'), cost=Decimal('0'),
            revenue_account=acc['411'], cost_of_goods_account=acc['511'],
        )
        inv.subtotal = Decimal('1500.00')
        inv.tax_amount = Decimal('210.00')
        inv.total = Decimal('1710.00')
        inv.save()
        SalesService.post_invoice(inv, admin)
        self.stdout.write(f'  فاتورة مبيعات: ${inv.total}')

        # Receipt (full payment)
        receipt = CustomerReceipt.objects.create(
            number='RPT-RCPT-001', date=today, customer=customer,
            amount=inv.total, payment_method='cash', cash_box=cashbox,
            reference=f'سداد {inv.number}',
        )
        from apps.sales.models import ReceiptAllocation
        ReceiptAllocation.objects.create(receipt=receipt, invoice=inv, amount=inv.total)
        SalesService.record_receipt(receipt, admin)
        self.stdout.write(f'  سند قبض: ${receipt.amount}')

        # ==================== EXPENSE ====================
        self.stdout.write('\n===== 3. مصروفات =====')
        JournalService.create_entry(
            date_val=today, entry_type=JournalEntry.EntryType.EXPENSE,
            description='مصروف إيجار',
            lines=[
                {'account': Account.objects.get(code='5211'), 'debit': Decimal('500.00'), 'credit': Decimal('0')},
                {'account': acc['111101'], 'debit': Decimal('0'), 'credit': Decimal('500.00')},
            ],
            source_document=None, created_by=admin,
        )
        JournalService.create_entry(
            date_val=today, entry_type=JournalEntry.EntryType.EXPENSE,
            description='مصروف كهرباء',
            lines=[
                {'account': Account.objects.get(code='5212'), 'debit': Decimal('300.00'), 'credit': Decimal('0')},
                {'account': acc['111101'], 'debit': Decimal('0'), 'credit': Decimal('300.00')},
            ],
            source_document=None, created_by=admin,
        )
        self.stdout.write('  تم ترحيل المصروفات')

        # ==================== RUN REPORTS ====================
        # ---- TRIAL BALANCE ----
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write('\n===== ميزان المراجعة =====')
        tb = ReportService.trial_balance(fy_start, today)
        tb_op_dr = sum(r['op_debit'] for r in tb)
        tb_op_cr = sum(r['op_credit'] for r in tb)
        tb_mov_dr = sum(r['mov_debit'] for r in tb)
        tb_mov_cr = sum(r['mov_credit'] for r in tb)
        tb_cl_dr = sum(r['cl_debit'] for r in tb)
        tb_cl_cr = sum(r['cl_credit'] for r in tb)

        self.stdout.write(f'  فتح: مدين={tb_op_dr} دائن={tb_op_cr} {"✓" if tb_op_dr == tb_op_cr else "✗"}')
        self.stdout.write(f'  حركة: مدين={tb_mov_dr} دائن={tb_mov_cr} {"✓" if tb_mov_dr == tb_mov_cr else "✗"}')
        self.stdout.write(f'  ختام: مدين={tb_cl_dr} دائن={tb_cl_cr} {"✓" if tb_cl_dr == tb_cl_cr else "✗"}')

        for r in tb:
            d = r['cl_debit'] or r['cl_credit']
            self.stdout.write(f'  {r["account"].code:>6} {r["account"].name[:30]:<30} '
                              f'دائن={r["cl_credit"]:>8} مدين={r["cl_debit"]:>8}')

        tb_ok = (tb_op_dr == tb_op_cr and tb_mov_dr == tb_mov_cr and tb_cl_dr == tb_cl_cr)
        if tb_ok:
            self.stdout.write(self.style.SUCCESS('  ✓ ميزان المراجعة متوازن'))
        else:
            self.stdout.write(self.style.ERROR('  ✗ ميزان المراجعة غير متوازن!'))

        # ---- INCOME STATEMENT ----
        self.stdout.write('\n===== قائمة الدخل =====')
        inc = ReportService.income_statement(fy_start, today)

        def fmt(val):
            return f'${val:>8}'

        self.stdout.write(f'  المبيعات:               {fmt(inc["sales"])}')
        self.stdout.write(f'  مردودات المبيعات:       {fmt(inc["sales_returns"])}')
        self.stdout.write(f'  خصم مبيعات:             {fmt(inc["sales_discount"])}')
        self.stdout.write(f'  صافي المبيعات:          {fmt(inc["net_sales"])}')
        self.stdout.write(f'  تكلفة المبيعات:          {fmt(inc["cogs_total"])}')
        self.stdout.write(f'  مجمل الربح:              {fmt(inc["gross_profit"])}')

        self.stdout.write(f'  مصروفات تشغيل:           {fmt(inc["total_op_expenses"])}')
        self.stdout.write(f'  الربح التشغيلي:          {fmt(inc["operating_profit"])}')

        self.stdout.write(f'  إيرادات أخرى:            {fmt(inc["total_other_rev"])}')
        self.stdout.write(f'  مصروفات تمويل:           {fmt(inc["total_finance_exp"])}')
        self.stdout.write(f'  مصروفات أخرى:            {fmt(inc["total_other_exp"])}')
        self.stdout.write(f'  صافي الإيرادات الأخرى:   {fmt(inc["net_other"])}')

        self.stdout.write(f'  صافي الربح قبل الضريبة:  {fmt(inc["net_profit_before_tax"])}')
        self.stdout.write(f'  ضريبة الدخل:             {fmt(inc["tax_exp"])}')
        self.stdout.write(f'  صافي الربح:              {fmt(inc["net_income"])}')

        # Verify income statement math
        inc_ok = True
        expected_net_sales = inc['sales'] - inc['sales_returns'] - inc['sales_discount']
        if inc['net_sales'] != expected_net_sales:
            self.stdout.write(self.style.ERROR(f'  ✗ صافي المبيعات غير متطابق: {inc["net_sales"]} != {expected_net_sales}'))
            inc_ok = False
        expected_gp = inc['net_sales'] - inc['cogs_total']
        if inc['gross_profit'] != expected_gp:
            self.stdout.write(self.style.ERROR(f'  ✗ مجمل الربح غير متطابق: {inc["gross_profit"]} != {expected_gp}'))
            inc_ok = False
        expected_op = inc['gross_profit'] - inc['total_op_expenses']
        if inc['operating_profit'] != expected_op:
            self.stdout.write(self.style.ERROR(f'  ✗ الربح التشغيلي غير متطابق: {inc["operating_profit"]} != {expected_op}'))
            inc_ok = False
        expected_nt = inc['total_other_rev'] - inc['total_finance_exp'] - inc['total_other_exp']
        if inc['net_other'] != expected_nt:
            self.stdout.write(self.style.ERROR(f'  ✗ صافي الإيرادات الأخرى غير متطابق: {inc["net_other"]} != {expected_nt}'))
            inc_ok = False
        expected_npbt = inc['operating_profit'] + inc['net_other']
        if inc['net_profit_before_tax'] != expected_npbt:
            self.stdout.write(self.style.ERROR(f'  ✗ الربح قبل الضريبة غير متطابق: {inc["net_profit_before_tax"]} != {expected_npbt}'))
            inc_ok = False
        expected_ni = inc['net_profit_before_tax'] - inc['tax_exp']
        if inc['net_income'] != expected_ni:
            self.stdout.write(self.style.ERROR(f'  ✗ صافي الربح غير متطابق: {inc["net_income"]} != {expected_ni}'))
            inc_ok = False

        if inc_ok:
            self.stdout.write(self.style.SUCCESS('  ✓ قائمة الدخل متطابقة رياضياً'))

        # ---- BALANCE SHEET ----
        self.stdout.write('\n===== الميزانية =====')
        bs = ReportService.balance_sheet(today)

        self.stdout.write(f'  الأصول:                  {fmt(bs["total_assets"])}')
        for a in bs['assets']:
            self.stdout.write(f'    {a["name"][:30]:<30} {fmt(a["balance"])}')
        self.stdout.write(f'  الخصوم:                  {fmt(bs["total_liabilities"])}')
        for l in bs['liabilities']:
            self.stdout.write(f'    {l["name"][:30]:<30} {fmt(l["balance"])}')
        self.stdout.write(f'  حقوق الملكية:            {fmt(bs["total_equity"])}')
        for e in bs['equity']:
            self.stdout.write(f'    {e["name"][:30]:<30} {fmt(e["balance"])}')

        ls_total = bs['total_liabilities'] + bs['total_equity']
        self.stdout.write(f'  خصوم + حقوق ملكية:       {fmt(ls_total)}')
        bs_ok = bs['total_assets'] == ls_total
        if bs_ok:
            self.stdout.write(self.style.SUCCESS(f'  ✓ الميزانية متوازنة: {bs["total_assets"]} = {ls_total}'))
        else:
            self.stdout.write(self.style.ERROR(f'  ✗ الميزانية غير متوازنة: {bs["total_assets"]} != {ls_total}'))

        # ==================== VERDICT ====================
        self.stdout.write('\n' + '=' * 60)
        if tb_ok and inc_ok and bs_ok:
            self.stdout.write(self.style.SUCCESS('\n✓ تم بنجاح! جميع التقارير المالية متطابقة'))
        else:
            fails = []
            if not tb_ok: fails.append('ميزان المراجعة')
            if not inc_ok: fails.append('قائمة الدخل')
            if not bs_ok: fails.append('الميزانية')
            self.stdout.write(self.style.ERROR(f'\n✗ فشل: {", ".join(fails)}'))
