from django.test import TransactionTestCase
from decimal import Decimal
from django.contrib.auth import get_user_model
from apps.core.models import Account, AccountType, TaxType, JournalEntry, FiscalYear
from apps.inventory.models import Item, ItemCategory, Warehouse, UnitOfMeasure
from apps.sales.models import Customer, SalesInvoice, SalesInvoiceLine
from apps.purchases.models import Supplier, PurchaseInvoice, PurchaseInvoiceLine
from apps.sales.services import SalesService
from apps.purchases.services import PurchaseService
from apps.inventory.services import InventoryService
from django.utils import timezone

User = get_user_model()

class AccountingLogicTest(TransactionTestCase):
    def setUp(self):
        # 1. User
        self.user = User.objects.create_superuser(username='admin_test', password='password', email='admin_test@test.com')
        
        # 2. Fiscal Year
        self.fy = FiscalYear.objects.create(
            name="2026_TEST", 
            start_date=timezone.now().date().replace(month=1, day=1),
            end_date=timezone.now().date().replace(month=12, day=31),
        )
        
        # 3. Accounts
        self.cash_acc = Account.objects.create(code='T1111', name='Cash Test', account_type=AccountType.ASSET, is_leaf=True)
        self.inv_acc = Account.objects.create(code='T1131', name='Inventory Test', account_type=AccountType.ASSET, is_leaf=True)
        self.cust_acc = Account.objects.create(code='T1121', name='Customer Test', account_type=AccountType.ASSET, is_leaf=True)
        self.vat_acc = Account.objects.create(code='T2121', name='VAT Test', account_type=AccountType.LIABILITY, is_leaf=True)
        self.supp_acc = Account.objects.create(code='T2111', name='Supplier Test', account_type=AccountType.LIABILITY, is_leaf=True)
        self.sales_acc = Account.objects.create(code='T4111', name='Sales Test', account_type=AccountType.REVENUE, is_leaf=True)
        self.cogs_acc = Account.objects.create(code='T5111', name='COGS Test', account_type=AccountType.EXPENSE, is_leaf=True)
        
        # 4. Tax Type
        self.vat_tax = TaxType.objects.create(name='VAT 14% TEST', category='vat', rate=Decimal('14.00'), account=self.vat_acc)
        
        # 5. Inventory Setup
        self.unit = UnitOfMeasure.objects.create(name='Unit Test', code='PCS_T')
        self.cat = ItemCategory.objects.create(name='Cat Test')
        self.warehouse = Warehouse.objects.create(name='WH Test')
        self.item = Item.objects.create(
            code='IT001T', name='Item Test', category=self.cat, base_unit=self.unit,
            inventory_account=self.inv_acc, cogs_account=self.cogs_acc, sales_account=self.sales_acc
        )
        
        # 6. Entities
        self.customer = Customer.objects.create(name='Cust Test', account=self.cust_acc)
        self.supplier = Supplier.objects.create(name='Supp Test', account=self.supp_acc)

    def test_purchase_invoice_and_inventory_valuation(self):
        """Test Case: Purchase -> Stock Increase -> Correct Ledger Entries"""
        invoice = PurchaseInvoice.objects.create(
            number='PUR-T001', supplier=self.supplier, date=timezone.now().date(),
            due_date=timezone.now().date(), created_by=self.user,
            subtotal=Decimal('1000'), total=Decimal('1140'), tax_amount=Decimal('140'),
            supplier_invoice_number='SUP-INV-001'
        )
        line = PurchaseInvoiceLine.objects.create(
            invoice=invoice, item=self.item, warehouse=self.warehouse, unit=self.unit,
            quantity=Decimal('10'), unit_cost=Decimal('100'), 
            tax_type=self.vat_tax, tax_percent=Decimal('14.00'), total=Decimal('1140')
        )
        
        PurchaseService.post_invoice(invoice, self.user)
        
        # Verify Ledger
        self.assertIsNotNone(invoice.journal_entry)
        self.assertTrue(self.inv_acc.journal_lines.filter(debit=1000).exists())
        self.assertTrue(self.vat_acc.journal_lines.filter(debit=140).exists())
        
        # Verify Inventory
        from apps.inventory.models import ItemLedger
        ledger = ItemLedger.objects.get(item=self.item, warehouse=self.warehouse)
        self.assertEqual(ledger.quantity_on_hand, 10)
        self.assertEqual(ledger.total_value, 1000)

    def test_sales_invoice_and_cogs_reversal(self):
        """Test Case: Sales -> Stock Decrease -> COGS Record"""
        # Initial Stock
        InventoryService.record_movement(
            date_val=timezone.now().date(), item=self.item, warehouse=self.warehouse,
            movement_type='opening', quantity=Decimal('10'), unit_cost=Decimal('100'),
        )
        
        invoice = SalesInvoice.objects.create(
            number='INV-T001', customer=self.customer, date=timezone.now().date(),
            payment_type='credit', created_by=self.user,
            subtotal=Decimal('400'), total=Decimal('456'), tax_amount=Decimal('56'),
            due_date=timezone.now().date()
        )
        line = SalesInvoiceLine.objects.create(
            invoice=invoice, item=self.item, warehouse=self.warehouse, unit=self.unit,
            quantity=Decimal('2'), unit_price=Decimal('200'),
            tax_type=self.vat_tax, tax_percent=Decimal('14.00'), total=Decimal('456'),
            revenue_account=self.sales_acc, cost_of_goods_account=self.cogs_acc
        )
        
        SalesService.post_invoice(invoice, self.user)
        
        # COGS check
        self.assertTrue(self.cogs_acc.journal_lines.filter(debit=200).exists())
        
        # Inventory check
        from apps.inventory.models import ItemLedger
        ledger = ItemLedger.objects.get(item=self.item, warehouse=self.warehouse)
        self.assertEqual(ledger.quantity_on_hand, 8)
        self.assertEqual(ledger.total_value, 800)

    def test_inventory_zero_reset(self):
        """Test Case: Ensure valuation is reset when quantity hits zero"""
        InventoryService.record_movement(
            date_val=timezone.now().date(), item=self.item, warehouse=self.warehouse,
            movement_type='opening', quantity=Decimal('1'), unit_cost=Decimal('150.75'),
        )
        
        InventoryService.record_movement(
            date_val=timezone.now().date(), item=self.item, warehouse=self.warehouse,
            movement_type='sales_out', quantity=Decimal('-1'), unit_cost=Decimal('150.75'),
        )
        
        from apps.inventory.models import ItemLedger
        ledger = ItemLedger.objects.get(item=self.item, warehouse=self.warehouse)
        self.assertEqual(ledger.quantity_on_hand, 0)
        self.assertEqual(ledger.total_value, 0)
