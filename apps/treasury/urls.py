from django.urls import path
from . import views

app_name = 'treasury'

urlpatterns = [
    path('', views.TreasuryDashboardView.as_view(), name='dashboard'),
    path('cashboxes/', views.CashBoxListView.as_view(), name='cashbox-list'),
    path('cashboxes/create/', views.CashBoxCreateView.as_view(), name='cashbox-create'),
    path('cashboxes/<int:pk>/', views.CashBoxDetailView.as_view(), name='cashbox-detail'),
    path('cashboxes/<int:pk>/update/', views.CashBoxUpdateView.as_view(), name='cashbox-update'),

    path('banks/', views.BankAccountListView.as_view(), name='bank-list'),
    path('banks/create/', views.BankAccountCreateView.as_view(), name='bank-create'),
    path('banks/<int:pk>/', views.BankAccountDetailView.as_view(), name='bank-detail'),
    path('banks/<int:pk>/update/', views.BankAccountUpdateView.as_view(), name='bank-update'),

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
]
