from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.FinancialReportDashboardView.as_view(), name='financial_dashboard'),
    path('trial-balance/', views.TrialBalanceView.as_view(), name='trial_balance'),
    path('income-statement/', views.IncomeStatementView.as_view(), name='income_statement'),
    path('balance-sheet/', views.BalanceSheetView.as_view(), name='balance_sheet'),
    path('cash-flow-statement/', views.CashFlowStatementView.as_view(), name='cash_flow_statement'),
    path('customer-statement/', views.CustomerStatementView.as_view(), name='customer_statement'),
    path('supplier-statement/', views.SupplierStatementView.as_view(), name='supplier_statement'),
    path('stock-status/', views.StockStatusView.as_view(), name='stock_status'),
    path('rep-commission/', views.RepCommissionView.as_view(), name='rep_commission'),
    path('cost-center-statement/', views.CostCenterStatementView.as_view(), name='cost_center_statement'),
    path('account-statement/', views.AccountStatementView.as_view(), name='account_statement'),
    path('rep-statement/', views.RepStatementView.as_view(), name='rep_statement'),
    path('rep-dashboard/', views.SalesRepDashboardView.as_view(), name='rep_dashboard'),
    # Tax Reports
    path('vat-report/', views.VATReportView.as_view(), name='vat_report'),
    path('vat-settlement/', views.VATSettlementView.as_view(), name='vat_settlement'),
    path('wht-report/', views.WHTReportView.as_view(), name='wht_report'),

    # Inventory Reports
    path('inventory-valuation/', views.InventoryValuationView.as_view(), name='inventory_valuation'),
    path('reorder-alert/', views.ReorderAlertView.as_view(), name='reorder_alert'),
    path('item-ledger/', views.ItemLedgerReportView.as_view(), name='item_ledger'),
    path('wastage-adjustments/', views.WastageAdjustmentsView.as_view(), name='wastage_adjustments'),
    path('van-inventory/', views.VanInventoryView.as_view(), name='van_inventory'),
    path('inventory-turnover/', views.InventoryTurnoverView.as_view(), name='inventory_turnover'),
]

