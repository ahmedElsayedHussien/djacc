from django.test import TransactionTestCase, Client
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.urls import reverse
from django.utils import timezone
from apps.inventory.models import (
    Item, ItemCategory, Warehouse, UnitOfMeasure, WarehouseTransfer,
    WarehouseTransferLine, LoadingOrder, LoadingOrderLine, StockVoucher, StockVoucherLine
)
from apps.inventory.forms import (
    WarehouseTransferForm, WarehouseTransferLineFormSet,
    LoadingOrderForm, LoadingOrderLineFormSet,
    StockVoucherForm, StockVoucherLineFormSet
)
from apps.sales.models import SalesRepresentative

User = get_user_model()

class InventoryValidationsTest(TransactionTestCase):
    def setUp(self):
        # 1. Setup superuser
        self.user = User.objects.create_superuser(username='inventory_admin', password='password', email='inv_admin@test.com')
        
        # 2. Setup inventory accounts
        from apps.core.models import Account, AccountType
        self.asset_acc = Account.objects.get_or_create(code='1131', name='Inventory', account_type=AccountType.ASSET, is_leaf=True)[0]
        self.expense_acc = Account.objects.get_or_create(code='511', name='COGS', account_type=AccountType.EXPENSE, is_leaf=True)[0]
        self.sales_acc = Account.objects.get_or_create(code='411', name='Sales', account_type=AccountType.REVENUE, is_leaf=True)[0]
        
        # 3. Setup basic inventory master data
        self.unit = UnitOfMeasure.objects.create(name='Unit Test', code='PCS')
        self.cat = ItemCategory.objects.create(name='Category Test', code='1')
        self.warehouse1 = Warehouse.objects.create(name='Main Warehouse 1', code='WH01')
        self.warehouse2 = Warehouse.objects.create(name='Main Warehouse 2', code='WH02')
        
        self.item1 = Item.objects.create(
            code='ITEM001', name='Item 1', category=self.cat, base_unit=self.unit,
            inventory_account=self.asset_acc, cogs_account=self.expense_acc, sales_account=self.sales_acc
        )
        self.item2 = Item.objects.create(
            code='ITEM002', name='Item 2', category=self.cat, base_unit=self.unit,
            inventory_account=self.asset_acc, cogs_account=self.expense_acc, sales_account=self.sales_acc
        )

    def test_warehouse_transfer_non_draft_modification_blocked(self):
        """Test Case: Prevent modifying posted/cancelled transfers via update view"""
        transfer = WarehouseTransfer.objects.create(
            number='TR-001', date=timezone.now().date(),
            from_warehouse=self.warehouse1, to_warehouse=self.warehouse2,
            status=WarehouseTransfer.Status.POSTED
        )
        
        # Using a client to hit the update view
        client = Client()
        client.force_login(self.user)
        
        # The correct URL name in inventory app is 'transfer-edit'
        url = reverse('inventory:transfer-edit', kwargs={'pk': transfer.pk})
        
        from django.test import RequestFactory
        from apps.inventory.views import WarehouseTransferUpdateView
        request = RequestFactory().get(url)
        request.user = self.user
        
        with self.assertRaises(PermissionDenied):
            view = WarehouseTransferUpdateView.as_view()
            view(request, pk=transfer.pk)

    def test_warehouse_transfer_line_formset_duplicate_items(self):
        """Test Case: Duplicate items in transfer rows must be blocked"""
        transfer = WarehouseTransfer.objects.create(
            number='TR-002', date=timezone.now().date(),
            from_warehouse=self.warehouse1, to_warehouse=self.warehouse2
        )
        
        data = {
            'lines-TOTAL_FORMS': '2',
            'lines-INITIAL_FORMS': '0',
            'lines-MIN_NUM_FORMS': '0',
            'lines-MAX_NUM_FORMS': '1000',
            'lines-0-item': self.item1.id,
            'lines-0-quantity': '10',
            'lines-1-item': self.item1.id, # DUPLICATE!
            'lines-1-quantity': '5',
        }
        formset = WarehouseTransferLineFormSet(data, instance=transfer, prefix='lines')
        self.assertFalse(formset.is_valid())
        # Check duplicate item error in the forms
        errors = [form.errors.get('item') for form in formset.forms if form.errors.get('item')]
        self.assertTrue(any('مكرر' in str(err) for err in errors))

    def test_loading_order_primary_warehouse_validation(self):
        """Test Case: Source warehouse of loading order cannot be a representative's warehouse"""
        # Create rep warehouse
        rep_warehouse = Warehouse.objects.create(name='Rep Car WH', code='WH_REP')
        
        # Create required CashBox for SalesRepresentative
        from apps.treasury.models import CashBox
        rep_cash_box = CashBox.objects.create(
            code='REP_CASH_TEST', name='Rep Cash Test', account=self.asset_acc, responsible_user=self.user
        )
        
        # Create SalesRepresentative with all required parameters
        sales_rep = SalesRepresentative.objects.create(
            name='Rep Test',
            code='REP001',
            user=self.user,
            cash_box=rep_cash_box,
            warehouse=rep_warehouse
        )
        
        form_data = {
            'date': timezone.now().date(),
            'sales_rep': sales_rep.id,
            'from_warehouse': rep_warehouse.id, # INVALID: Rep warehouse selected as source
            'to_warehouse': self.warehouse1.id,
            'notes': 'Test notes'
        }
        form = LoadingOrderForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('from_warehouse', form.errors)
        self.assertTrue(any('مندوب' in str(err) for err in form.errors['from_warehouse']))

    def test_stock_voucher_receipt_cost_validation(self):
        """Test Case: Receipt stock vouchers must have a positive unit_cost"""
        voucher = StockVoucher.objects.create(
            number='V-REC-001', date=timezone.now().date(),
            voucher_type=StockVoucher.VoucherType.RECEIPT,
            warehouse=self.warehouse1, created_by=self.user
        )
        
        data = {
            'lines-TOTAL_FORMS': '1',
            'lines-INITIAL_FORMS': '0',
            'lines-MIN_NUM_FORMS': '0',
            'lines-MAX_NUM_FORMS': '1000',
            'lines-0-item': self.item1.id,
            'lines-0-quantity': '10',
            'lines-0-unit_cost': '', # INVALID: cost is required for receipts
        }
        
        formset = StockVoucherLineFormSet(data, instance=voucher, prefix='lines')
        self.assertFalse(formset.is_valid())
        errors = [form.errors.get('unit_cost') for form in formset.forms if form.errors.get('unit_cost')]
        self.assertTrue(any('يجب إدخال تكلفة وحدة موجبة' in str(err) for err in errors))

    def test_warehouse_toggle_active_status_view(self):
        """Test Case: Warehouse toggle active status via view POST request"""
        warehouse = Warehouse.objects.create(name='Test Toggle Warehouse', code='WH_TGL', is_active=True)
        self.assertTrue(warehouse.is_active)
        
        client = Client()
        client.force_login(self.user)
        
        url = reverse('inventory:warehouse-toggle-active', kwargs={'pk': warehouse.pk})
        response = client.post(url)
        
        # Verify redirect to list
        self.assertRedirects(response, reverse('inventory:warehouse-list'))
        
        # Refresh and verify is_active is now False
        warehouse.refresh_from_db()
        self.assertFalse(warehouse.is_active)
