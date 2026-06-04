from django.urls import path
from . import views, report_views

app_name = 'sales'

urlpatterns = [
    # Dashboard
    path('', report_views.SalesDashboardView.as_view(), name='dashboard'),

    # Customers
    path('customers/', views.CustomerListView.as_view(), name='customer-list'),
    path('customers/create/', views.CustomerCreateView.as_view(), name='customer-create'),
    path('customers/<int:pk>/', views.CustomerDetailView.as_view(), name='customer-detail'),
    path('customers/<int:pk>/edit/', views.CustomerUpdateView.as_view(), name='customer-edit'),
    path('customers/<int:pk>/statement/', views.CustomerStatementView.as_view(), name='customer-statement'),
    
    # Invoices
    path('invoices/', views.SalesInvoiceListView.as_view(), name='invoice-list'),
    path('invoices/create/', views.SalesInvoiceCreateView.as_view(), name='invoice-create'),
    path('invoices/<int:pk>/', views.SalesInvoiceDetailView.as_view(), name='invoice-detail'),
    path('invoices/<int:pk>/print/', views.SalesInvoicePrintView.as_view(), name='invoice-print'),
    path('invoices/<int:pk>/edit/', views.SalesInvoiceUpdateView.as_view(), name='invoice-edit'),
    path('invoices/<int:pk>/reverse/', views.SalesInvoiceReverseView.as_view(), name='invoice-reverse'),
    path('invoices/<int:pk>/post/', views.SalesInvoicePostView.as_view(), name='invoice-post'),
    # Receipts
    path('receipts/', views.CustomerReceiptListView.as_view(), name='receipt-list'),
    path('receipts/create/', views.CustomerReceiptCreateView.as_view(), name='receipt-create'),
    path('receipts/<int:pk>/', views.CustomerReceiptDetailView.as_view(), name='receipt-detail'),
    path('receipts/<int:pk>/print/', views.CustomerReceiptPrintView.as_view(), name='receipt-print'),
    path('receipts/<int:pk>/collect/', views.ChequeCollectionView.as_view(), name='collect-cheque'),
    path('receipts/<int:pk>/bounce/', views.ChequeBounceView.as_view(), name='bounce-cheque'),
    
    # Representatives
    path('reps/', views.SalesRepresentativeListView.as_view(), name='rep-list'),
    path('reps/create/', views.SalesRepresentativeCreateView.as_view(), name='rep-create'),
    path('reps/<int:pk>/', views.SalesRepresentativeDetailView.as_view(), name='rep-detail'),
    path('reps/<int:pk>/edit/', views.SalesRepresentativeUpdateView.as_view(), name='rep-edit'),
    path('reps/<int:rep_pk>/collect/', views.RepReceivableCollectView.as_view(), name='rep-collect'),

    # Rep Settlements
    path('settlements/', views.RepDailySettlementListView.as_view(), name='settlement-list'),
    path('settlements/create/', views.RepDailySettlementCreateView.as_view(), name='settlement-create'),
    path('settlements/unsettled-invoices/', views.RepUnsettledInvoicesView.as_view(), name='unsettled-invoices'),
    path('settlements/<int:pk>/', views.RepDailySettlementDetailView.as_view(), name='settlement-detail'),
    path('settlements/<int:pk>/post/', views.RepDailySettlementPostView.as_view(), name='settlement-post'),

    # Returns
    path('returns/', views.SalesReturnListView.as_view(), name='return-list'),
    path('returns/create/', views.SalesReturnCreateView.as_view(), name='return-create'),
    path('returns/<int:pk>/', views.SalesReturnDetailView.as_view(), name='return-detail'),
    path('returns/<int:pk>/post/', views.SalesReturnPostView.as_view(), name='return-post'),
    path('returns/<int:pk>/delete/', views.SalesReturnDeleteView.as_view(), name='return-delete'),

    # Quotations
    path('quotations/', views.QuotationListView.as_view(), name='quotation-list'),
    path('quotations/create/', views.QuotationCreateView.as_view(), name='quotation-create'),
    path('quotations/<int:pk>/', views.QuotationDetailView.as_view(), name='quotation-detail'),
    path('quotations/<int:pk>/edit/', views.QuotationUpdateView.as_view(), name='quotation-update'),
    path('quotations/<int:pk>/cancel/', views.QuotationCancelView.as_view(), name='quotation-cancel'),
    path('quotations/<int:pk>/convert/', views.QuotationConvertToInvoiceView.as_view(), name='quotation-convert'),
    
    # API
    path('api/rep/<int:pk>/', views.RepDetailsAPIView.as_view(), name='rep-api'),
    path('api/customer/<int:customer_id>/invoices/', views.CustomerInvoicesAPIView.as_view(), name='customer-invoices-api'),
    path('api/invoice/<int:invoice_id>/lines/', views.SalesInvoiceLinesAPIView.as_view(), name='invoice-lines-api'),
    
    # Sectors
    path('sectors/', views.CustomerSectorListView.as_view(), name='sector-list'),
    path('sectors/create/', views.CustomerSectorCreateView.as_view(), name='sector-create'),
    path('sectors/<int:pk>/edit/', views.CustomerSectorUpdateView.as_view(), name='sector-edit'),
    
    # Price Lists
    path('price-lists/', views.PriceListListView.as_view(), name='pricelist-list'),
    path('price-lists/create/', views.PriceListCreateView.as_view(), name='pricelist-create'),
    path('price-lists/<int:pk>/edit/', views.PriceListUpdateView.as_view(), name='pricelist-update'),
    path('price-lists/<int:pk>/delete/', views.PriceListDeleteView.as_view(), name='pricelist-delete'),
    
    # Representative Views
    path('my-stock/', views.RepStockStatusView.as_view(), name='rep-stock'),

    # Reports
    path('reports/', report_views.SalesReportDashboardView.as_view(), name='report-dashboard'),

    path('reports/sales-by-item/', report_views.SalesByItemReportView.as_view(), name='report-by-item'),
    path('reports/sales-by-rep/', report_views.SalesByRepReportView.as_view(), name='report-by-rep'),
    path('reports/sales-by-customer/', report_views.SalesByCustomerReportView.as_view(), name='report-by-customer'),
    path('reports/returns/', report_views.SalesReturnReportView.as_view(), name='report-returns'),
    path('reports/detailed/', report_views.DetailedSalesReportView.as_view(), name='report-detailed'),
    path('reports/target-comparison/', report_views.SalesTargetComparisonView.as_view(), name='report-target-comparison'),
    path('reports/aging/', report_views.SalesAgingReportView.as_view(), name='report-aging'),
    path('reports/net-profitability/', report_views.NetSalesProfitabilityReportView.as_view(), name='report-net-profitability'),
    path('reports/product-profitability/', report_views.ProductProfitabilityReportView.as_view(), name='report-product-profitability'),
    path('reports/by-sector/', report_views.SalesBySectorReportView.as_view(), name='report-by-sector'),
    path('reports/rep-performance-enhanced/', report_views.RepPerformanceEnhancedReportView.as_view(), name='report-rep-performance-enhanced'),
    path('reports/aging-summary/', report_views.CustomerAgingSummaryReportView.as_view(), name='report-aging-summary'),
    path('reports/quotation-analysis/', report_views.QuotationAnalysisReportView.as_view(), name='report-quotation-analysis'),
    path('reports/customer-balances/', report_views.CustomerBalancesReportView.as_view(), name='report-customer-balances'),
]

