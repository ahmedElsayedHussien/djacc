from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('trial-balance/', views.TrialBalanceView.as_view(), name='trial_balance'),
    path('income-statement/', views.IncomeStatementView.as_view(), name='income_statement'),
    path('balance-sheet/', views.BalanceSheetView.as_view(), name='balance_sheet'),
    path('customer-statement/', views.CustomerStatementView.as_view(), name='customer_statement'),
    path('stock-status/', views.StockStatusView.as_view(), name='stock_status'),
    path('rep-commission/', views.RepCommissionView.as_view(), name='rep_commission'),
    path('cost-center-statement/', views.CostCenterStatementView.as_view(), name='cost_center_statement'),
    path('account-statement/', views.AccountStatementView.as_view(), name='account_statement'),
]
