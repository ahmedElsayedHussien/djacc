from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from apps.core.models import Account, JournalEntry, TaxType
from apps.sales.models import Customer, SalesInvoice, PriceList, PriceListItem, Quotation
from apps.purchases.models import Supplier, PurchaseInvoice
from .serializers import (
    AccountSerializer, JournalEntrySerializer, 
    CustomerSerializer, SalesInvoiceSerializer,
    SupplierSerializer, PurchaseInvoiceSerializer, TaxTypeSerializer,
    QuotationSerializer, PriceListSerializer
)

class AccountViewSet(viewsets.ReadOnlyModelViewSet):
    """ReadOnly to protect financial structure integrity"""
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    permission_classes = [permissions.DjangoModelPermissions]

class JournalEntryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = JournalEntry.objects.all()
    serializer_class = JournalEntrySerializer
    permission_classes = [permissions.DjangoModelPermissions]

class CustomerViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [permissions.DjangoModelPermissions]

class SalesInvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SalesInvoice.objects.all()
    serializer_class = SalesInvoiceSerializer
    permission_classes = [permissions.DjangoModelPermissions]

class SupplierViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [permissions.DjangoModelPermissions]

class PurchaseInvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PurchaseInvoice.objects.all()
    serializer_class = PurchaseInvoiceSerializer
    permission_classes = [permissions.DjangoModelPermissions]

class TaxTypeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TaxType.objects.filter(is_active=True)
    serializer_class = TaxTypeSerializer
    permission_classes = [permissions.DjangoModelPermissions]

class PriceListViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PriceList.objects.filter(is_active=True)
    serializer_class = PriceListSerializer
    permission_classes = [permissions.DjangoModelPermissions]

    @action(detail=True, methods=['get'])
    def item_price(self, request, pk=None):
        item_id = request.query_params.get('item_id')
        if not item_id:
            return viewsets.response.Response({'error': 'item_id is required'}, status=400)
        
        try:
            item_price = PriceListItem.objects.get(price_list_id=pk, item_id=item_id)
            return viewsets.response.Response({'price': item_price.unit_price})
        except PriceListItem.DoesNotExist:
            return viewsets.response.Response({'price': None})
class QuotationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Quotation.objects.filter(is_active=True, status='active')
    serializer_class = QuotationSerializer
    permission_classes = [permissions.DjangoModelPermissions]

    @action(detail=False, methods=['get'])
    def active_for_sector(self, request):
        sector_id = request.query_params.get('sector_id')
        if not sector_id:
            return viewsets.response.Response({'error': 'sector_id is required'}, status=400)
        
        from django.utils import timezone
        today = timezone.now().date()
        
        offers = Quotation.objects.filter(
            sector_id=sector_id,
            is_active=True,
            status='active',
            start_date__lte=today,
            end_date__gte=today
        )
        serializer = self.get_serializer(offers, many=True)
        return viewsets.response.Response(serializer.data)
