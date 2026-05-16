from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.InventoryDashboardView.as_view(), name='dashboard'),
    path('items/', views.ItemListView.as_view(), name='item-list'),
    path('items/create/', views.ItemCreateView.as_view(), name='item-create'),
    path('items/<int:pk>/', views.ItemDetailView.as_view(), name='item-detail'),
    path('items/<int:pk>/edit/', views.ItemUpdateView.as_view(), name='item-edit'),

    path('warehouses/', views.WarehouseListView.as_view(), name='warehouse-list'),
    path('warehouses/create/', views.WarehouseCreateView.as_view(), name='warehouse-create'),

    path('categories/', views.ItemCategoryListView.as_view(), name='category-list'),
    path('categories/create/', views.ItemCategoryCreateView.as_view(), name='category-create'),

    path('units/', views.UnitListView.as_view(), name='unit-list'),
    path('units/create/', views.UnitCreateView.as_view(), name='unit-create'),

    # Transfers
    path('transfers/', views.WarehouseTransferListView.as_view(), name='transfer-list'),
    path('transfers/create/', views.WarehouseTransferCreateView.as_view(), name='transfer-create'),
    path('transfers/<int:pk>/', views.WarehouseTransferDetailView.as_view(), name='transfer-detail'),
    path('transfers/<int:pk>/edit/', views.WarehouseTransferUpdateView.as_view(), name='transfer-edit'),
    path('transfers/<int:pk>/post/', views.WarehouseTransferPostView.as_view(), name='transfer-post'),
    path('transfers/<int:pk>/reverse/', views.WarehouseTransferReverseView.as_view(), name='transfer-reverse'),


    # Loadings
    path('loadings/', views.LoadingOrderListView.as_view(), name='loading-list'),
    path('loadings/create/', views.LoadingOrderCreateView.as_view(), name='loading-create'),
    path('loadings/<int:pk>/', views.LoadingOrderDetailView.as_view(), name='loading-detail'),
    path('loadings/<int:pk>/request/', views.LoadingOrderRequestView.as_view(), name='loading-request'),
    path('loadings/<int:pk>/approve/', views.LoadingOrderApproveView.as_view(), name='loading-approve'),
    path('loadings/<int:pk>/issue/', views.LoadingOrderIssueView.as_view(), name='loading-issue'),
    path('loadings/<int:pk>/cancel/', views.LoadingOrderCancelView.as_view(), name='loading-cancel'),


    # Vouchers
    path('vouchers/', views.StockVoucherListView.as_view(), name='voucher-list'),
    path('vouchers/create/', views.StockVoucherCreateView.as_view(), name='voucher-create'),
    path('vouchers/<int:pk>/', views.StockVoucherDetailView.as_view(), name='voucher-detail'),
    path('vouchers/<int:pk>/post/', views.StockVoucherPostView.as_view(), name='voucher-post'),
    path('vouchers/<int:pk>/reverse/', views.StockVoucherReverseView.as_view(), name='voucher-reverse'),
    # API
    path('api/item/<int:pk>/', views.ItemDetailsAPIView.as_view(), name='api-item-details'),
    
    # Reports
    path('reports/dashboard/', views.InventoryReportDashboardView.as_view(), name='report-dashboard'),
]

