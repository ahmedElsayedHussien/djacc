from rest_framework import serializers
from apps.core.models import Account, JournalEntry, JournalLine
from apps.sales.models import Customer, SalesInvoice, PriceList, PriceListItem
from apps.purchases.models import Supplier, PurchaseInvoice

class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = '__all__'

class JournalLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalLine
        fields = '__all__'

class JournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True, read_only=True)
    class Meta:
        model = JournalEntry
        fields = '__all__'

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'

from apps.sales.models import Quotation, QuotationLine
class QuotationLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuotationLine
        fields = ['item', 'extra_discount_percent']

class QuotationSerializer(serializers.ModelSerializer):
    lines = QuotationLineSerializer(many=True, read_only=True)
    class Meta:
        model = Quotation
        fields = ['id', 'name', 'sector', 'start_date', 'end_date', 'lines']

class SalesInvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesInvoice
        fields = '__all__'

class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = '__all__'

class PurchaseInvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseInvoice
        fields = '__all__'

from apps.core.models import TaxType
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
