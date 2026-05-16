from django.urls import path
from . import views, report_views

app_name = 'purchases'

urlpatterns = [
    path('', views.PurchaseDashboardView.as_view(), name='dashboard'),
    # Suppliers
    path('suppliers/', views.SupplierListView.as_view(), name='supplier-list'),
    path('suppliers/create/', views.SupplierCreateView.as_view(), name='supplier-create'),
    path('suppliers/<int:pk>/', views.SupplierDetailView.as_view(), name='supplier-detail'),
    path('suppliers/<int:pk>/edit/', views.SupplierUpdateView.as_view(), name='supplier-edit'),
    
    # Invoices
    path('invoices/', views.PurchaseInvoiceListView.as_view(), name='invoice-list'),
    path('invoices/create/', views.PurchaseInvoiceCreateView.as_view(), name='invoice-create'),
    path('invoices/<int:pk>/', views.PurchaseInvoiceDetailView.as_view(), name='invoice-detail'),
    path('invoices/<int:pk>/post/', views.PurchaseInvoicePostView.as_view(), name='invoice-post'),
    path('invoices/<int:pk>/reverse/', views.PurchaseInvoiceReverseView.as_view(), name='invoice-reverse'),
    # Payments
    path('payments/', views.SupplierPaymentListView.as_view(), name='payment-list'),
    path('payments/create/', views.SupplierPaymentCreateView.as_view(), name='payment-create'),
    path('payments/<int:pk>/', views.SupplierPaymentDetailView.as_view(), name='payment-detail'),

    # Returns
    path('returns/', views.PurchaseReturnListView.as_view(), name='return-list'),
    path('returns/create/', views.PurchaseReturnCreateView.as_view(), name='return-create'),
    path('returns/<int:pk>/', views.PurchaseReturnDetailView.as_view(), name='return-detail'),
    path('returns/<int:pk>/post/', views.PurchaseReturnPostView.as_view(), name='return-post'),

    # Reports
    path('reports/', report_views.PurchaseReportDashboardView.as_view(), name='report-dashboard'),
    path('reports/summary/', report_views.PurchaseSummaryReportView.as_view(), name='report-summary'),
    path('reports/item-cost/', report_views.ItemPurchaseCostReportView.as_view(), name='report-item-cost'),
    path('reports/supplier-balances/', report_views.SupplierBalancesReportView.as_view(), name='report-supplier-balances'),
    path('reports/aging/', report_views.SupplierAgingReportView.as_view(), name='report-aging'),
    path('reports/open-orders/', report_views.OpenPurchaseOrdersReportView.as_view(), name='report-open-orders'),
    path('reports/returns-analysis/', report_views.PurchaseReturnAnalysisReportView.as_view(), name='report-returns-analysis'),
]
