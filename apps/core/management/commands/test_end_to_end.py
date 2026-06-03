from datetime import date
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from apps.core.models import Account, FiscalYear, JournalEntry, JournalLine, TaxType
from apps.inventory.models import (
    Warehouse, ItemCategory, UnitOfMeasure, Item, ItemLedger, StockMovement,
    StockVoucher, StockVoucherLine,
)
from apps.inventory.services import StockVoucherService, InventoryService
from apps.treasury.models import CashBox
from apps.sales.models import (
    Customer, SalesRepresentative, SalesInvoice, SalesInvoiceLine,
    SalesReturn, SalesReturnLine, CustomerReceipt, ReceiptAllocation,
    RepDailySettlement, RepSettlementInvoice,
)
from apps.sales.services import SalesService, CustomerService, RepSettlementService
from apps.purchases.models import (
    Supplier, PurchaseInvoice, PurchaseInvoiceLine,
    PurchaseReturn, PurchaseReturnLine,
    SupplierPayment, PaymentAllocation,
)
from apps.purchases.services import PurchaseService, SupplierService

class Command(BaseCommand):
    help = 'اختبار متكامل: مخزون ← مبيعات ← مشتريات + فحص حسابات العملاء والموردين'

    def handle(self, *args, **options):
        today = date.today()
        User = get_user_model()
        admin = User.objects.filter(is_superuser=True).first()
        if not admin:
            self.stdout.write(self.style.ERROR('لا يوجد مستخدم superuser'))
            return

        # ==================== FULL CLEANUP ====================
        from apps.inventory.models import (
            StockVoucherLine, StockVoucher, WarehouseTransferLine, WarehouseTransfer,
            LoadingOrderLine, LoadingOrder,
        )
        from apps.sales.models import (
            SalesInvoiceLine, SalesInvoice, SalesReturnLine, SalesReturn, SalesRepresentative,
            CustomerReceipt, ReceiptAllocation, RepSettlementInvoice, RepDailySettlement, Customer,
        )
        from apps.purchases.models import PurchaseInvoiceLine, PurchaseInvoice, PurchaseReturnLine, PurchaseReturn

        RepSettlementInvoice.objects.all().delete()
        RepDailySettlement.objects.all().delete()
        ReceiptAllocation.objects.all().delete()
        CustomerReceipt.objects.all().delete()
        SalesReturnLine.objects.all().delete()
        SalesReturn.objects.all().delete()
        SalesInvoiceLine.objects.all().delete()
        SalesInvoice.objects.all().delete()
        SalesRepresentative.objects.all().delete()
        Customer.objects.all().delete()
        PaymentAllocation.objects.all().delete()
        SupplierPayment.objects.all().delete()
        PurchaseReturnLine.objects.all().delete()
        PurchaseReturn.objects.all().delete()
        PurchaseInvoiceLine.objects.all().delete()
        PurchaseInvoice.objects.all().delete()
        Supplier.objects.all().delete()
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
        JournalLine.objects.all().delete()
        JournalEntry.objects.all().delete()
        self.stdout.write('تم مسح جميع البيانات')

        # ==================== SETUP ====================
        fy, _ = FiscalYear.objects.get_or_create(
            name=f'سنة مالية {today.year}',
            defaults=dict(start_date=date(today.year, 1, 1), end_date=date(today.year, 12, 31), is_closed=False),
        )
        inv_acc = Account.objects.get(code='1131')
        rev_acc = Account.objects.get(code='411')
        cogs_acc = Account.objects.get(code='511')
        vat_acc = Account.objects.get(code='21211')
        cust_ar = Account.objects.get(code='1121')
        rep_cashbox_acc = Account.objects.get(code='111102')
        main_cashbox_acc = Account.objects.get(code='111101')

        vat, _ = TaxType.objects.get_or_create(
            name='VAT 14%',
            defaults=dict(category=TaxType.Category.VAT, rate=Decimal('14.00'), account=vat_acc, is_active=True),
        )
        main_cash, _ = CashBox.objects.get_or_create(
            code='CASH-MAIN',
            defaults=dict(name='الخزينة الرئيسية', account=main_cashbox_acc, responsible_user=admin, is_active=True),
        )
        wh, _ = Warehouse.objects.get_or_create(
            code='WH-MAIN',
            defaults=dict(name='المخزن الرئيسي', gl_account=inv_acc, is_active=True),
        )
        cat, _ = ItemCategory.objects.get_or_create(code='1', defaults=dict(name='عام'))
        unit, _ = UnitOfMeasure.objects.get_or_create(code='PC', defaults=dict(name='قطعة'))
        item, _ = Item.objects.get_or_create(code='ITEM', defaults=dict(
            name='منتج', category=cat, base_unit=unit,
            inventory_account=inv_acc, cogs_account=cogs_acc, standard_price=Decimal('150'),
        ))

        # Opening stock
        v = StockVoucher.objects.create(number='OPEN', date=today, voucher_type='receipt', warehouse=wh, offset_account=Account.objects.get(code='35'), notes='', created_by=admin)
        StockVoucherLine.objects.create(voucher=v, item=item, quantity=100, unit_cost=Decimal('100'))
        StockVoucherService.post_voucher(v, admin)
        self.stdout.write('المخزون الافتتاحي: 100 وحدة @ $100 = $10,000')

        # Customer
        customer = CustomerService.create_customer(dict(name='عميل'))

        # Sales Rep
        rep_code = 'sr-test-e2e'
        rep = SalesRepresentative.objects.filter(code=rep_code).first()
        if not rep:
            rep_cash, _ = CashBox.objects.get_or_create(
                account=rep_cashbox_acc,
                defaults=dict(code='CASH-REP', name='خزينة المندوب', responsible_user=admin, is_active=True),
            )
            rep_account, _ = Account.objects.get_or_create(
                code='1141002',
                defaults=dict(name='عهدة مندوب الاختبار', account_type='current_asset', parent=Account.objects.get(code='1141')),
            )
            rep = SalesRepresentative.objects.create(
                code=rep_code, name='مندوب اختبار', user=admin,
                warehouse=wh, cash_box=rep_cash, account=rep_account,
            )

        # Supplier
        supplier = SupplierService.create_supplier(dict(name='مورد'))

        def bal(code):
            lines = JournalLine.objects.filter(account=Account.objects.get(code=code))
            dr = sum((l.debit or 0) for l in lines)
            cr = sum((l.credit or 0) for l in lines)
            return dr - cr  # positive=debit, negative=credit

        def check(label, code, expected):
            actual = bal(code)
            ok = '✓' if actual == expected else '✗'
            self.stdout.write(f'  {ok} {label}: ${actual} (متوقع: ${expected})')

        # ==================== 1. SALES ====================
        self.stdout.write('\n===== 1. دورة البيع =====')

        # Credit invoice: 10 units @ $120 + 14% VAT = $1,368
        inv = SalesInvoice.objects.create(
            number='E2E-SINV-001',
            date=today, customer=customer, sales_rep=rep,
            payment_type='credit', due_date=today, status='draft',
            subtotal=Decimal('0'), discount_amount=Decimal('0'),
            tax_amount=Decimal('0'), total=Decimal('0'), created_by=admin,
        )
        SalesInvoiceLine.objects.create(invoice=inv, item=item, warehouse=wh, unit=unit,
            quantity=10, base_quantity=10, unit_price=Decimal('120'), discount_percent=Decimal('0'),
            tax_type=vat, tax_percent=vat.rate, total=Decimal('1368.00'),
            cost=Decimal('0'), revenue_account=rev_acc, cost_of_goods_account=cogs_acc,
        )
        inv.subtotal = Decimal('1200.00')
        inv.tax_amount = Decimal('168.00')
        inv.total = Decimal('1368.00')
        inv.save()
        SalesService.post_invoice(inv, admin)
        self.stdout.write(f'  1.1 فاتورة آجلة $1,368')
        check('   العميل (1121xxx)', customer.account.code, Decimal('1368.00'))
        check('   الإيرادات (411)', '411', Decimal('-1200.00'))  # credit balance
        check('   تكلفة المبيعات (511)', '511', Decimal('1000.00'))
        check('   المخزون (1131)', '1131', Decimal('9000.00'))  # 10000 - 1000

        # Cash invoice: 5 units @ $120 + 14% VAT = $684 → auto-receipt to rep's cash box
        rep_cash = rep.cash_box
        inv2 = SalesInvoice.objects.create(
            number='E2E-SINV-002',
            date=today, customer=customer, sales_rep=rep,
            payment_type='cash', cash_box=rep_cash,
            due_date=today, status='draft',
            subtotal=Decimal('0'), discount_amount=Decimal('0'),
            tax_amount=Decimal('0'), total=Decimal('0'), created_by=admin,
        )
        SalesInvoiceLine.objects.create(invoice=inv2, item=item, warehouse=wh, unit=unit,
            quantity=5, base_quantity=5, unit_price=Decimal('120'), discount_percent=Decimal('0'),
            tax_type=vat, tax_percent=vat.rate, total=Decimal('684.00'),
            cost=Decimal('0'), revenue_account=rev_acc, cost_of_goods_account=cogs_acc,
        )
        inv2.subtotal = Decimal('600.00')
        inv2.tax_amount = Decimal('84.00')
        inv2.total = Decimal('684.00')
        inv2.save()
        SalesService.post_invoice(inv2, admin)
        self.stdout.write(f'  1.2 فاتورة نقدية $684 + سند قبض تلقائي لخزينة المندوب')
        tot_customer = Decimal('1368.00') + Decimal('684.00') - Decimal('684.00')  # inv1 + inv2 - auto-receipt
        check('   العميل (1121xxx)', customer.account.code, tot_customer)
        check('   الخزينة الرئيسية (111101)', '111101', Decimal('0.00'))  # unchanged
        check('   خزينة المندوب (111102)', '111102', Decimal('684.00'))
        check('   المخزون (1131)', '1131', Decimal('8500.00'))

        # Manual receipt for credit invoice: $1,368
        rcp = CustomerReceipt.objects.create(
            number='E2E-RCP-001', date=today, customer=customer, amount=Decimal('1368.00'),
            payment_method='cash', cash_box=main_cash, reference='',
        )
        ReceiptAllocation.objects.create(receipt=rcp, invoice=inv, amount=Decimal('1368.00'))
        SalesService.record_receipt(rcp, admin)
        self.stdout.write(f'  1.3 سند قبض $1,368')
        check('   العميل (1121xxx)', customer.account.code, Decimal('0.00'))  # cleared
        check('   الخزينة الرئيسية (111101)', '111101', Decimal('1368.00'))  # 0 + 1368
        inv.refresh_from_db()
        self.stdout.write(f'  1.4 الفاتورة الآجلة مدفوعة: ${inv.paid_amount}')

        # Sales return: 2 units from credit invoice → $273.60
        ret = SalesReturn.objects.create(
            number='E2E-SRET-001', date=today, invoice=inv, customer=customer, sales_rep=rep,
            payment_type='credit', status='draft',
            subtotal=Decimal('240.00'), discount_amount=Decimal('0.00'),
            tax_amount=Decimal('33.60'), total=Decimal('273.60'), created_by=admin,
        )
        SalesReturnLine.objects.create(sales_return=ret, item=item, warehouse=wh, unit=unit,
            quantity=2, base_quantity=2, unit_price=Decimal('120'), discount_percent=Decimal('0'),
            tax_type=vat, tax_percent=vat.rate, total=Decimal('273.60'),
            cost=Decimal('100'), return_account=Account.objects.get(code='413'), cogs_account=cogs_acc,
        )
        SalesService.post_return(ret, admin)
        self.stdout.write(f'  1.5 مرتجع مبيعات $273.60')
        check('   العميل (1121xxx)', customer.account.code, Decimal('-273.60'))  # credit balance
        check('   المخزون (1131)', '1131', Decimal('8700.00'))
        check('   مردودات (413)', '413', Decimal('240.00'))

        # Rep settlement
        settle = RepDailySettlement.objects.create(
            date=today, sales_rep=rep, total_sales=Decimal('0'),
            cash_delivered=Decimal('0'), difference=Decimal('0'),
            to_cash_box=main_cash, notes='', created_by=admin,
        )
        RepSettlementInvoice.objects.create(settlement=settle, invoice=inv2)
        settle.calculate_totals()
        settle.cash_delivered = settle.total_sales
        settle.save()
        RepSettlementService.post_settlement(settle, admin)
        self.stdout.write(f'  1.6 تسوية مندوب: $684 من خزينة المندوب ← خزينة رئيسية')
        check('   خزينة الرئيسية (111101)', '111101', Decimal('2052.00'))  # 1368 + 684
        check('   خزينة المندوب (111102)', '111102', Decimal('0.00'))  # 684 - 684

        # ==================== 2. PURCHASES ====================
        self.stdout.write('\n===== 2. دورة المشتريات =====')

        # Credit purchase: 20 units @ $80 + 14% = $1,824
        pinv = PurchaseInvoice.objects.create(
            number='E2E-PINV-001',
            date=today, supplier=supplier, payment_type='credit',
            due_date=today, status='draft',
            subtotal=Decimal('0'), discount_amount=Decimal('0'),
            tax_amount=Decimal('0'), total=Decimal('0'), created_by=admin,
        )
        PurchaseInvoiceLine.objects.create(invoice=pinv, item=item, warehouse=wh, unit=unit,
            quantity=20, base_quantity=20, unit_cost=Decimal('80'), discount_percent=Decimal('0'),
            tax_type=vat, tax_percent=vat.rate, total=Decimal('1824.00'),
        )
        pinv.subtotal = Decimal('1600.00')
        pinv.tax_amount = Decimal('224.00')
        pinv.total = Decimal('1824.00')
        pinv.save()
        PurchaseService.post_invoice(pinv, admin)
        self.stdout.write(f'  2.1 فاتورة مشتريات آجلة $1,824')
        check('   المورد (2111xxx)', supplier.account.code, Decimal('-1824.00'))  # negative = credit balance
        check('   المخزون (1131)', '1131', Decimal('10300.00'))  # 8700 + 1600

        # Cash purchase: 10 units @ $80 + 14% = $912 → auto-payment
        pinv2 = PurchaseInvoice.objects.create(
            number='E2E-PINV-002',
            date=today, supplier=supplier, payment_type='cash',
            payment_method='cash', cash_box=main_cash,
            due_date=today, status='draft',
            subtotal=Decimal('0'), discount_amount=Decimal('0'),
            tax_amount=Decimal('0'), total=Decimal('0'), created_by=admin,
        )
        PurchaseInvoiceLine.objects.create(invoice=pinv2, item=item, warehouse=wh, unit=unit,
            quantity=10, base_quantity=10, unit_cost=Decimal('80'), discount_percent=Decimal('0'),
            tax_type=vat, tax_percent=vat.rate, total=Decimal('912.00'),
        )
        pinv2.subtotal = Decimal('800.00')
        pinv2.tax_amount = Decimal('112.00')
        pinv2.total = Decimal('912.00')
        pinv2.save()
        PurchaseService.post_invoice(pinv2, admin)
        self.stdout.write(f'  2.2 فاتورة مشتريات نقدية $912 + سند صرف تلقائي')
        check('   المخزون (1131)', '1131', Decimal('11100.00'))  # 10300 + 800
        tot_supplier = Decimal('-1824.00') + Decimal('-912.00') + Decimal('912.00')  # inv1 + inv2 - auto-payment
        check('   المورد (2111xxx)', supplier.account.code, tot_supplier)
        check('   الخزينة الرئيسية (111101)', '111101', Decimal('1140.00'))  # 2052 - 912

        # Manual payment for credit invoice: $1,824
        pay = SupplierPayment.objects.create(
            date=today, supplier=supplier, amount=Decimal('1824.00'),
            payment_method='cash', cash_box=main_cash, reference='', created_by=admin,
        )
        PaymentAllocation.objects.create(payment=pay, invoice=pinv, amount=Decimal('1824.00'))
        PurchaseService.record_payment(pay, admin)
        self.stdout.write(f'  2.3 سند صرف $1,824')
        check('   المورد (2111xxx)', supplier.account.code, Decimal('0.00'))  # fully paid
        check('   الخزينة الرئيسية (111101)', '111101', Decimal('-684.00'))  # 1140 - 1824

        # Purchase return: 3 units → $273.60
        pret = PurchaseReturn.objects.create(
            date=today, invoice=pinv, supplier=supplier, status='draft',
            subtotal=Decimal('240.00'), discount_amount=Decimal('0.00'),
            tax_amount=Decimal('33.60'), total=Decimal('273.60'), created_by=admin,
        )
        PurchaseReturnLine.objects.create(purchase_return=pret, item=item, warehouse=wh, unit=unit,
            quantity=3, base_quantity=3, unit_cost=Decimal('80'), discount_percent=Decimal('0'),
            tax_type=vat, tax_percent=vat.rate, total=Decimal('273.60'),
        )
        PurchaseService.post_return(pret, admin)
        self.stdout.write(f'  2.4 مرتجع مشتريات $273.60')
        check('   المخزون (1131)', '1131', Decimal('10860.00'))  # 11100 - 240
        check('   المورد (2111xxx)', supplier.account.code, Decimal('273.60'))  # supplier owes us

        # ==================== 3. FINAL VERIFICATION ====================
        self.stdout.write('\n' + '=' * 50)
        all_entries = JournalEntry.objects.all().order_by('date', 'id')
        balanced = 0
        for e in all_entries:
            lines = e.lines.all()
            dr = sum((l.debit or 0) for l in lines)
            cr = sum((l.credit or 0) for l in lines)
            if dr == cr:
                balanced += 1
            else:
                self.stdout.write(f'  ✗ قيد #{e.id} غير متوازن: مدين={dr} دائن={cr}')

        self.stdout.write(f'القيود: {balanced}/{all_entries.count()} متوازنة')
        self.stdout.write(f'المخزون: {ItemLedger.objects.get(item=item, warehouse=wh).quantity_on_hand} وحدة')
        self.stdout.write(f'عدد حركات المخزون: {StockMovement.objects.count()}')

        self.stdout.write('\n===== الأرصدة النهائية =====')
        check('المخزون (1131)', '1131', Decimal('10860.00'))
        check('العميل', customer.account.code, Decimal('-273.60'))
        check('المورد', supplier.account.code, Decimal('273.60'))
        check('الخزينة الرئيسية (111101)', '111101', Decimal('-684.00'))
        check('خزينة المندوب (111102)', '111102', Decimal('0.00'))
        check('الإيرادات (411)', '411', Decimal('-1800.00'))  # credit balance
        check('تكلفة المبيعات (511)', '511', Decimal('1300.00'))
        check('مردودات (413)', '413', Decimal('240.00'))  # debit balance (contra-revenue)

        if balanced == all_entries.count():
            self.stdout.write(self.style.SUCCESS('\n✓ نجاح: جميع القيود متوازنة'))
        else:
            self.stdout.write(self.style.ERROR(f'\n✗ يوجد {all_entries.count() - balanced} قيد غير متوازن'))
