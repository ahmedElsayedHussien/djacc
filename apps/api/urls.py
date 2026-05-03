from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'accounts', views.AccountViewSet)
router.register(r'journal-entries', views.JournalEntryViewSet)
router.register(r'customers', views.CustomerViewSet)
router.register(r'sales-invoices', views.SalesInvoiceViewSet)
router.register(r'suppliers', views.SupplierViewSet)
router.register(r'purchase-invoices', views.PurchaseInvoiceViewSet)
router.register(r'taxes', views.TaxTypeViewSet)
router.register(r'price-lists', views.PriceListViewSet)
router.register(r'quotations', views.QuotationViewSet)

app_name = 'api'

urlpatterns = [
    path('', include(router.urls)),
]
