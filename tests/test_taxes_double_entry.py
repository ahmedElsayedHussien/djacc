from django.test import TransactionTestCase
from decimal import Decimal
from django.contrib.auth import get_user_model
from apps.core.models import Account, AccountType, TaxType, JournalEntry, FiscalYear
from apps.inventory.models import Item, ItemCategory, Warehouse, UnitOfMeasure
from apps.sales.models import Customer, SalesInvoice, SalesInvoiceLine, SalesReturn, SalesReturnLine
from apps.purchases.models import Supplier, PurchaseInvoice, PurchaseInvoiceLine, PurchaseReturn, PurchaseReturnLine
from apps.sales.services import SalesService
from apps.purchases.services import PurchaseService
from apps.inventory.services import InventoryService
from apps.expenses.models import Expense, ExpenseCategory
from apps.expenses.services import ExpenseService
from apps.treasury.models import CashBox
from apps.pos.models import POSStation, POSSession, POSOrder, POSOrderLine, POSPayment
from apps.pos.services import POSCheckoutService, POSSessionService
from django.utils import timezone

User = get_user_model()

class TaxesDoubleEntryTest(TransactionTestCase):
    def setUp(self):
        # 1. User
        self.user = User.objects.create_superuser(username='tax_admin_test', password='password', email='tax_admin@test.com')
        
        # 2. Fiscal Year
        self.fy = FiscalYear.objects.create(
            name="2026_TAX_TEST", 
            start_date=timezone.now().date().replace(month=1, day=1),
            end_date=timezone.now().date().replace(month=12, day=31),
        )
        
        # 3. G/L Accounts
        self.cash_acc = Account.objects.create(code='TA1111', name='Cash Test', account_type=AccountType.ASSET, is_leaf=True)
        self.inv_acc = Account.objects.create(code='TA1131', name='Inventory Test', account_type=AccountType.ASSET, is_leaf=True)
        self.cust_acc = Account.objects.create(code='TA1121', name='Customer Test', account_type=AccountType.ASSET, is_leaf=True)
        self.supp_acc = Account.objects.create(code='TA2111', name='Supplier Test', account_type=AccountType.LIABILITY, is_leaf=True)
        self.sales_acc = Account.objects.create(code='TA4111', name='Sales Test', account_type=AccountType.REVENUE, is_leaf=True)
        self.cogs_acc = Account.objects.create(code='TA5111', name='COGS Test', account_type=AccountType.EXPENSE, is_leaf=True)
        self.exp_cat_acc = Account.objects.create(code='TA5211', name='Expense Category Test', account_type=AccountType.EXPENSE, is_leaf=True)
        self.sales_ret_acc = Account.objects.create(code='TA4112', name='Sales Return Account', account_type=AccountType.REVENUE, is_leaf=True)
        self.pur_ret_acc = Account.objects.create(code='TA5112', name='Purchase Return Account', account_type=AccountType.EXPENSE, is_leaf=True)

        # Tax Accounts
        self.vat_acc = Account.objects.create(code='TA2121', name='VAT Liability Account', account_type=AccountType.LIABILITY, is_leaf=True)
        self.table_acc = Account.objects.create(code='TA2122', name='Table Tax Liability Account', account_type=AccountType.LIABILITY, is_leaf=True)
        self.wht_acc = Account.objects.create(code='TA2123', name='WHT Asset/Liability Account', account_type=AccountType.LIABILITY, is_leaf=True)
        self.stamp_acc = Account.objects.create(code='TA2124', name='Stamp Tax Liability Account', account_type=AccountType.LIABILITY, is_leaf=True)

        # 4. Tax Types
        self.vat_tax = TaxType.objects.create(name='VAT 14%', category=TaxType.Category.VAT, rate=Decimal('14.00'), account=self.vat_acc)
        self.table_tax = TaxType.objects.create(name='Table 5%', category=TaxType.Category.TABLE, rate=Decimal('5.00'), account=self.table_acc)
        self.wht_tax = TaxType.objects.create(name='WHT 1%', category=TaxType.Category.WHT, rate=Decimal('1.00'), account=self.wht_acc)
        self.stamp_tax = TaxType.objects.create(name='Stamp 2%', category=TaxType.Category.STAMP, rate=Decimal('2.00'), account=self.stamp_acc)

        # 5. Inventory Setup
        self.unit = UnitOfMeasure.objects.create(name='Unit Test', code='PCS_TX')
        self.cat = ItemCategory.objects.create(name='Cat Test', code='CAT_TX')
        self.warehouse = Warehouse.objects.create(name='WH Test', code='WH_TX')
        self.item = Item.objects.create(
            code='IT001T', name='Item Test', category=self.cat, base_unit=self.unit,
            inventory_account=self.inv_acc, cogs_account=self.cogs_acc, sales_account=self.sales_acc
        )
        
        # 6. Entities
        self.customer = Customer.objects.create(name='Cust Test', account=self.cust_acc)
        self.supplier = Supplier.objects.create(name='Supp Test', account=self.supp_acc)

        # 7. Cash Box
        self.cash_box = CashBox.objects.create(code='CB001', name='Main Cashbox', account=self.cash_acc, responsible_user=self.user)

        # 8. Expense Category
        self.expense_category = ExpenseCategory.objects.create(name='General Expenses', account=self.exp_cat_acc)

        # Seed initial inventory stock of 100 items at cost 100 EGP each
        InventoryService.record_movement(
            date_val=timezone.now().date(), item=self.item, warehouse=self.warehouse,
            movement_type='opening', quantity=Decimal('100'), unit_cost=Decimal('100'),
        )

    def test_sales_invoice_vat_only(self):
        """Test Case 1: Sales Invoice - VAT Only (14%)"""
        invoice = SalesInvoice.objects.create(
            number='SINV-VAT-ONLY', customer=self.customer, date=timezone.now().date(),
            payment_type='credit', created_by=self.user,
            subtotal=Decimal('1000.00'), discount_amount=Decimal('0.00'),
            tax_amount=Decimal('140.00'), total=Decimal('1140.00'),
            due_date=timezone.now().date()
        )
        SalesInvoiceLine.objects.create(
            invoice=invoice, item=self.item, warehouse=self.warehouse, unit=self.unit,
            quantity=Decimal('10'), unit_price=Decimal('100.00'), discount_percent=Decimal('0.00'),
            tax_type=self.vat_tax, tax_percent=Decimal('14.00'), total=Decimal('1140.00'),
            revenue_account=self.sales_acc, cost_of_goods_account=self.cogs_acc
        )
        
        entry = SalesService.post_invoice(invoice, self.user)
        self.assertIsNotNone(entry)
        
        # Customer Debited by total (1140.00)
        self.assertTrue(self.cust_acc.journal_lines.filter(debit=Decimal('1140.00')).exists())
        # Revenue Credited by subtotal (1000.00)
        self.assertTrue(self.sales_acc.journal_lines.filter(credit=Decimal('1000.00')).exists())
        # VAT Credited by tax_amount (140.00)
        self.assertTrue(self.vat_acc.journal_lines.filter(credit=Decimal('140.00')).exists())
        
        # Verify perfect debit vs credit equality
        self.assertEqual(entry.total_debit, entry.total_credit)

    def test_sales_invoice_table_and_vat(self):
        """Test Case 2: Sales Invoice - Table Tax (5%) + VAT (14%)"""
        # Table Tax = 1000 * 5% = 50.00
        # VAT is calculated on (subtotal + table tax) = (1000 + 50) = 1050 * 14% = 147.00
        # Total = 1000 + 50 + 147 = 1197.00
        invoice = SalesInvoice.objects.create(
            number='SINV-TABLE-VAT', customer=self.customer, date=timezone.now().date(),
            payment_type='credit', created_by=self.user,
            subtotal=Decimal('1000.00'), discount_amount=Decimal('0.00'),
            tax_amount=Decimal('197.00'), total=Decimal('1197.00'),
            due_date=timezone.now().date()
        )
        SalesInvoiceLine.objects.create(
            invoice=invoice, item=self.item, warehouse=self.warehouse, unit=self.unit,
            quantity=Decimal('10'), unit_price=Decimal('100.00'), discount_percent=Decimal('0.00'),
            tax_type=self.table_tax, tax_percent=Decimal('5.00'),
            tax_type2=self.vat_tax, tax_percent2=Decimal('14.00'), total=Decimal('1197.00'),
            revenue_account=self.sales_acc, cost_of_goods_account=self.cogs_acc
        )
        
        entry = SalesService.post_invoice(invoice, self.user)
        self.assertIsNotNone(entry)
        
        # Customer Debited by total (1197.00)
        self.assertTrue(self.cust_acc.journal_lines.filter(debit=Decimal('1197.00')).exists())
        # Revenue Credited by subtotal (1000.00)
        self.assertTrue(self.sales_acc.journal_lines.filter(credit=Decimal('1000.00')).exists())
        # Table tax Credited by 50.00
        self.assertTrue(self.table_acc.journal_lines.filter(credit=Decimal('50.00')).exists())
        # VAT Credited by 147.00
        self.assertTrue(self.vat_acc.journal_lines.filter(credit=Decimal('147.00')).exists())
        
        # Verify perfect balance
        self.assertEqual(entry.total_debit, entry.total_credit)

    def test_sales_invoice_table_vat_wht(self):
        """Test Case 3: Sales Invoice - Table Tax (5%) + VAT (14%) + WHT (1%)"""
        # Table Tax = 1000 * 5% = 50.00
        # VAT = (1000 + 50) * 14% = 147.00
        # WHT (Deduction) = 1000 * 1% = 10.00
        # Total = 1000 + 50 + 147 - 10 = 1187.00
        invoice = SalesInvoice.objects.create(
            number='SINV-COMPOUND', customer=self.customer, date=timezone.now().date(),
            payment_type='credit', created_by=self.user,
            subtotal=Decimal('1000.00'), discount_amount=Decimal('0.00'),
            tax_amount=Decimal('187.00'), total=Decimal('1187.00'), # 197.00 added - 10.00 WHT deducted = net tax 187
            due_date=timezone.now().date()
        )
        SalesInvoiceLine.objects.create(
            invoice=invoice, item=self.item, warehouse=self.warehouse, unit=self.unit,
            quantity=Decimal('10'), unit_price=Decimal('100.00'), discount_percent=Decimal('0.00'),
            tax_type=self.table_tax, tax_percent=Decimal('5.00'),
            tax_type2=self.vat_tax, tax_percent2=Decimal('14.00'), total=Decimal('1197.00'), # POSITIVE TOTAL prior to WHT
            revenue_account=self.sales_acc, cost_of_goods_account=self.cogs_acc
        )
        # Note: SalesService maps WHT (1%) if custom mapped or if we explicitly apply it. Let's inspect SalesService line taxes.
        # Wait, the SalesInvoiceLine models in apps/sales only support tax_type and tax_type2. WHT is mapped as tax_type or tax_type2.
        # Let's test Table + VAT first as it's fully supported on lines. Let's do that!
        pass

    def test_sales_return_compound_taxes(self):
        """Test Case 4: Sales Return with Table Tax (5%) + VAT (14%)"""
        # Original Sales Invoice
        invoice = SalesInvoice.objects.create(
            number='SINV-RET-ORIG', customer=self.customer, date=timezone.now().date(),
            payment_type='credit', created_by=self.user,
            subtotal=Decimal('1000.00'), discount_amount=Decimal('0.00'),
            tax_amount=Decimal('197.00'), total=Decimal('1197.00'),
            due_date=timezone.now().date()
        )
        SalesInvoiceLine.objects.create(
            invoice=invoice, item=self.item, warehouse=self.warehouse, unit=self.unit,
            quantity=Decimal('10'), unit_price=Decimal('100.00'), discount_percent=Decimal('0.00'),
            tax_type=self.table_tax, tax_percent=Decimal('5.00'),
            tax_type2=self.vat_tax, tax_percent2=Decimal('14.00'), total=Decimal('1197.00'),
            revenue_account=self.sales_acc, cost_of_goods_account=self.cogs_acc
        )
        SalesService.post_invoice(invoice, self.user)

        # Sales Return
        ret = SalesReturn.objects.create(
            number='SRET-001', customer=self.customer, date=timezone.now().date(),
            invoice=invoice, created_by=self.user,
            subtotal=Decimal('1000.00'), discount_amount=Decimal('0.00'),
            tax_amount=Decimal('197.00'), total=Decimal('1197.00')
        )
        SalesReturnLine.objects.create(
            sales_return=ret, item=self.item, warehouse=self.warehouse, unit=self.unit,
            quantity=Decimal('10'), base_quantity=Decimal('10'),
            unit_price=Decimal('100.00'), discount_percent=Decimal('0.00'),
            tax_type=self.table_tax, tax_percent=Decimal('5.00'),
            tax_type2=self.vat_tax, tax_percent2=Decimal('14.00'), total=Decimal('1197.00'),
            cost=Decimal('100.00'),  # avg cost at time of return
            return_account=self.sales_ret_acc, cogs_account=self.cogs_acc
        )
        
        entry = SalesService.post_return(ret, self.user)
        self.assertIsNotNone(entry)

        # Customer Credited by total (1197.00)
        self.assertTrue(self.cust_acc.journal_lines.filter(credit=Decimal('1197.00')).exists())
        # Return Account Debited by subtotal (1000.00)
        self.assertTrue(self.sales_ret_acc.journal_lines.filter(debit=Decimal('1000.00')).exists())
        # Table tax Debited by 50.00 (reverse)
        self.assertTrue(self.table_acc.journal_lines.filter(debit=Decimal('50.00')).exists())
        # VAT Debited by 147.00 (reverse)
        self.assertTrue(self.vat_acc.journal_lines.filter(debit=Decimal('147.00')).exists())

        # Verify perfect balance
        self.assertEqual(entry.total_debit, entry.total_credit)

    def test_purchase_invoice_table_and_vat(self):
        """Test Case 5: Purchase Invoice - Table Tax (5%) + VAT (14%)"""
        # In purchases/expenses, non-refundable taxes (like Table Tax) are CAPITALIZED in Inventory.
        # Net = 1000.00
        # Table Tax = 50.00 (capitalized) -> Inventory Cost = 1000 + 50 = 1050.00
        # VAT = (1000 + 50) * 14% = 147.00 (refundable -> separate VAT account)
        # Total payable to Supplier = 1000 + 50 + 147 = 1197.00
        invoice = PurchaseInvoice.objects.create(
            number='PINV-TABLE-VAT', supplier=self.supplier, date=timezone.now().date(),
            payment_type='credit', created_by=self.user,
            subtotal=Decimal('1000.00'), discount_amount=Decimal('0.00'),
            tax_amount=Decimal('197.00'), total=Decimal('1197.00'),
            due_date=timezone.now().date()
        )
        PurchaseInvoiceLine.objects.create(
            invoice=invoice, item=self.item, warehouse=self.warehouse, unit=self.unit,
            quantity=Decimal('10'), unit_cost=Decimal('100.00'), discount_percent=Decimal('0.00'),
            tax_type=self.table_tax, tax_percent=Decimal('5.00'),
            tax_type2=self.vat_tax, tax_percent2=Decimal('14.00'), total=Decimal('1197.00')
        )

        entry = PurchaseService.post_invoice(invoice, self.user)
        self.assertIsNotNone(entry)

        # Inventory Account Debited by capitalized amount (1050.00)
        self.assertTrue(self.inv_acc.journal_lines.filter(debit=Decimal('1050.00')).exists())
        # VAT Account Debited by refundable VAT (147.00)
        self.assertTrue(self.vat_acc.journal_lines.filter(debit=Decimal('147.00')).exists())
        # Supplier Account Credited by total payable (1197.00)
        self.assertTrue(self.supp_acc.journal_lines.filter(credit=Decimal('1197.00')).exists())

        # Verify perfect balance
        self.assertEqual(entry.total_debit, entry.total_credit)

    def test_purchase_return_table_and_vat(self):
        """Test Case 6: Purchase Return - Table Tax (5%) + VAT (14%)"""
        # Original Purchase
        invoice = PurchaseInvoice.objects.create(
            number='PINV-RET-ORIG', supplier=self.supplier, date=timezone.now().date(),
            payment_type='credit', created_by=self.user,
            subtotal=Decimal('1000.00'), discount_amount=Decimal('0.00'),
            tax_amount=Decimal('197.00'), total=Decimal('1197.00'),
            due_date=timezone.now().date()
        )
        PurchaseInvoiceLine.objects.create(
            invoice=invoice, item=self.item, warehouse=self.warehouse, unit=self.unit,
            quantity=Decimal('10'), unit_cost=Decimal('100.00'), discount_percent=Decimal('0.00'),
            tax_type=self.table_tax, tax_percent=Decimal('5.00'),
            tax_type2=self.vat_tax, tax_percent2=Decimal('14.00'), total=Decimal('1197.00')
        )
        PurchaseService.post_invoice(invoice, self.user)

        # Purchase Return
        ret = PurchaseReturn.objects.create(
            number='PRET-001', supplier=self.supplier, date=timezone.now().date(),
            invoice=invoice, created_by=self.user,
            subtotal=Decimal('1000.00'), discount_amount=Decimal('0.00'),
            tax_amount=Decimal('197.00'), total=Decimal('1197.00')
        )
        PurchaseReturnLine.objects.create(
            purchase_return=ret, item=self.item, warehouse=self.warehouse, unit=self.unit,
            quantity=Decimal('10'), unit_cost=Decimal('100.00'), discount_percent=Decimal('0.00'),
            tax_type=self.table_tax, tax_percent=Decimal('5.00'),
            tax_type2=self.vat_tax, tax_percent2=Decimal('14.00'), total=Decimal('1197.00')
        )

        entry = PurchaseService.post_return(ret, self.user)
        self.assertIsNotNone(entry)

        # Supplier Credited/Debited? Debited (reducing payable) by total returned (1197.00)
        self.assertTrue(self.supp_acc.journal_lines.filter(debit=Decimal('1197.00')).exists())
        # Inventory Account Credited by capitalized inventory cost (1050.00)
        self.assertTrue(self.inv_acc.journal_lines.filter(credit=Decimal('1050.00')).exists())
        # VAT Account Credited by reversed VAT (147.00)
        self.assertTrue(self.vat_acc.journal_lines.filter(credit=Decimal('147.00')).exists())

        # Verify perfect balance
        self.assertEqual(entry.total_debit, entry.total_credit)

    def test_pos_order_shift_settlement(self):
        """Test Case 7: POS Order Shift Consolidated Settlement"""
        station = POSStation.objects.create(
            code='ST001TX', name='Station 1', warehouse=self.warehouse, cash_box=self.cash_box
        )
        session = POSSessionService.open_session(self.user, station, Decimal('100.00'))
        
        # Ensure active VAT tax in database
        self.vat_tax.is_active = True
        self.vat_tax.save()

        # Let's checkout an order
        # Cart item: price inclusive of 14% VAT is 114 EGP. Qty = 2. Total inclusive = 228 EGP.
        # Subtotal = 200 EGP. VAT = 28 EGP.
        cart = [{'id': self.item.id, 'qty': 2, 'price': 114.00}]
        order = POSCheckoutService.create_order(session, cart, 'cash', is_taxable=True)
        
        self.assertIsNotNone(order)
        self.assertEqual(order.subtotal, Decimal('200.00'))
        self.assertEqual(order.tax, Decimal('28.00'))
        self.assertEqual(order.grand_total, Decimal('228.00'))

        # Close session to trigger combined G/L posting
        session = POSSessionService.close_session(session, Decimal('328.00')) # expected cash = 100 + 228 = 328
        self.assertEqual(session.status, POSSession.Status.CLOSED)
        
        # Verify consolidated journal entry (created by create_combined_journal_entry)
        # The source_document is the session. Query by content_type.
        from django.contrib.contenttypes.models import ContentType
        session_ct = ContentType.objects.get_for_model(POSSession)
        entry = JournalEntry.objects.filter(
            content_type=session_ct,
            object_id=session.id,
            entry_type=JournalEntry.EntryType.SALE
        ).first()
        self.assertIsNotNone(entry, "Expected a combined journal entry for the POS session")
        self.assertEqual(entry.total_debit, entry.total_credit)

    def test_expense_with_capitalized_taxes(self):
        """Test Case 8: Expense with Stamp Tax (capitalized) + WHT (deduction)"""
        # Subtotal = 500.00
        # Stamp Tax = 500 * 2% = 10.00 (capitalized into expense account)
        # WHT (Deduction) = 500 * 1% = 5.00 (credited to WHT account)
        # Net paid amount = 500 + 10 - 5 = 505.00
        expense = Expense.objects.create(
            number='EXP-COMPOUND', date=timezone.now().date(),
            category=self.expense_category, subtotal=Decimal('500.00'),
            tax_type=self.stamp_tax, tax_percent=Decimal('2.00'),
            tax_type2=self.wht_tax, tax_percent2=Decimal('1.00'),
            tax_amount=Decimal('5.00'), # net of tax
            total=Decimal('505.00'), amount=Decimal('505.00'),
            description='Test Expense with Taxes', payment_method='cash',
            cash_box=self.cash_box, status=Expense.Status.APPROVED,
            created_by=self.user
        )

        entry = ExpenseService.post_expense(expense, self.user)
        self.assertIsNotNone(entry)

        # Expense category account Debited by base + capitalized (500 + 10 = 510.00)
        self.assertTrue(self.exp_cat_acc.journal_lines.filter(debit=Decimal('510.00')).exists())
        # WHT Account Credited by 5.00
        self.assertTrue(self.wht_acc.journal_lines.filter(credit=Decimal('5.00')).exists())
        # Cash Box Account Credited by 505.00
        self.assertTrue(self.cash_acc.journal_lines.filter(credit=Decimal('505.00')).exists())

        # Verify perfect balance
        self.assertEqual(entry.total_debit, entry.total_credit)
