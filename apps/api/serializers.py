from rest_framework import serializers
from apps.core.models import Account, JournalEntry, JournalLine, TaxType
from apps.sales.models import Customer, SalesInvoice, PriceList, PriceListItem, Quotation, QuotationLine
from apps.purchases.models import Supplier, PurchaseInvoice

class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ['id', 'code', 'name', 'account_type', 'is_leaf', 'is_active', 'initial_balance', 'initial_balance_type', 'parent']

class JournalLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalLine
        fields = ['id', 'account', 'cost_center', 'description', 'debit', 'credit']

class JournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True, read_only=True)
    class Meta:
        model = JournalEntry
        fields = ['id', 'number', 'date', 'description', 'entry_type', 'is_posted', 'lines']

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ['id', 'code', 'name', 'phone', 'email', 'tax_number', 'commercial_record', 'is_active', 'balance']

class QuotationLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuotationLine
        fields = ['item', 'unit', 'quantity', 'base_quantity', 'unit_price', 'discount_percent', 'tax_type', 'tax_percent', 'total']

class QuotationSerializer(serializers.ModelSerializer):
    lines = QuotationLineSerializer(many=True, read_only=True)
    class Meta:
        model = Quotation
        fields = ['id', 'number', 'name', 'customer', 'sector', 'sales_rep', 'start_date', 'end_date',
                  'status', 'is_active', 'subtotal', 'discount_amount', 'tax_amount', 'total', 'notes', 'lines']

class SalesInvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesInvoice
        fields = ['id', 'number', 'date', 'customer', 'subtotal', 'tax_amount', 'total', 'status', 'is_return']

class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ['id', 'code', 'name', 'phone', 'email', 'tax_number', 'is_active', 'balance']

class PurchaseInvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseInvoice
        fields = ['id', 'number', 'date', 'supplier', 'subtotal', 'tax_amount', 'total', 'status', 'is_return']

class TaxTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxType
        fields = ['id', 'name', 'rate', 'category']

class PriceListItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceListItem
        fields = ['id', 'item', 'unit_price', 'min_qty']

class PriceListSerializer(serializers.ModelSerializer):
    items = PriceListItemSerializer(many=True, read_only=True)
    class Meta:
        model = PriceList
        fields = ['id', 'name', 'is_default', 'is_active', 'items']
