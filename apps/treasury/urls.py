from django.urls import path
from . import views, report_views

app_name = 'treasury'

urlpatterns = [
    path('', views.TreasuryDashboardView.as_view(), name='dashboard'),
    path('cashboxes/', views.CashBoxListView.as_view(), name='cashbox-list'),
    path('cashboxes/create/', views.CashBoxCreateView.as_view(), name='cashbox-create'),
    path('cashboxes/<int:pk>/', views.CashBoxDetailView.as_view(), name='cashbox-detail'),
    path('cashboxes/<int:pk>/update/', views.CashBoxUpdateView.as_view(), name='cashbox-update'),
    path('reports/movements/', views.CashBoxMovementReportView.as_view(), name='movement-report'),

    path('banks/', views.BankAccountListView.as_view(), name='bank-list'),
    path('banks/create/', views.BankAccountCreateView.as_view(), name='bank-create'),
    path('banks/<int:pk>/', views.BankAccountDetailView.as_view(), name='bank-detail'),
    path('banks/<int:pk>/update/', views.BankAccountUpdateView.as_view(), name='bank-update'),

    # Wallets
    path('wallets/', views.MobileWalletListView.as_view(), name='wallet-list'),
    path('wallets/create/', views.MobileWalletCreateView.as_view(), name='wallet-create'),
    path('wallets/<int:pk>/', views.MobileWalletDetailView.as_view(), name='wallet-detail'),
    path('wallets/<int:pk>/update/', views.MobileWalletUpdateView.as_view(), name='wallet-update'),

    # Intermediary Companies
    path('intermediary/', views.IntermediaryCompanyListView.as_view(), name='intermediary-list'),
    path('intermediary/create/', views.IntermediaryCompanyCreateView.as_view(), name='intermediary-create'),
    path('intermediary/<int:pk>/update/', views.IntermediaryCompanyUpdateView.as_view(), name='intermediary-update'),

    # Transfers
    path('transfers/', views.CashTransferListView.as_view(), name='transfer-list'),
    path('transfers/create/', views.CashTransferCreateView.as_view(), name='transfer-create'),
    path('transfers/<int:pk>/', views.CashTransferDetailView.as_view(), name='transfer-detail'),
    path('transfers/<int:pk>/receive/', views.CashTransferReceiveView.as_view(), name='transfer-receive'),
    path('transfers/<int:pk>/reverse/', views.CashTransferReverseView.as_view(), name='transfer-reverse'),

    # Bank Reconciliation
    path('bank-reconciliations/', views.BankReconciliationListView.as_view(), name='bankreconciliation-list'),
    path('bank-reconciliations/create/', views.BankReconciliationCreateView.as_view(), name='bankreconciliation-create'),
    path('bank-reconciliations/<int:pk>/', views.BankReconciliationDetailView.as_view(), name='bankreconciliation-detail'),
    path('bank-reconciliations/<int:pk>/update/', views.BankReconciliationUpdateView.as_view(), name='bankreconciliation-update'),
    path('bank-reconciliations/<int:pk>/match/', views.BankReconciliationMatchView.as_view(), name='bankreconciliation-match'),

    # Bank Transactions
    path('bank-transactions/', views.BankTransactionListView.as_view(), name='banktransaction-list'),
    path('bank-transactions/create/', views.BankTransactionCreateView.as_view(), name='banktransaction-create'),
    path('bank-transactions/<int:pk>/', views.BankTransactionDetailView.as_view(), name='banktransaction-detail'),
    path('bank-transactions/<int:pk>/post/', views.BankTransactionPostView.as_view(), name='banktransaction-post'),

    # Advanced Reports
    path('reports/dashboard/', report_views.TreasuryReportDashboardView.as_view(), name='report-dashboard'),
    path('reports/liquidity/', report_views.LiveLiquidityReportView.as_view(), name='report-liquidity'),
    path('reports/in-transit/', report_views.CashInTransitReportView.as_view(), name='report-in-transit'),
    path('reports/transfers-summary/', report_views.InternalTransfersReportView.as_view(), name='report-transfers-summary'),
    path('reports/reconciliation-detail/', report_views.BankReconciliationReportView.as_view(), name='report-reconciliation-detail'),
    path('reports/charges-interest/', report_views.BankChargesInterestReportView.as_view(), name='report-charges-interest'),
]
