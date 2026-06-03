from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Login Redirect
    path('login-redirect/', views.login_redirect, name='login-redirect'),

    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Chart of Accounts
    path('accounts/', views.AccountListView.as_view(), name='account-list'),
    path('accounts/create/', views.AccountCreateView.as_view(), name='account-create'),
    path('accounts/initialize/', views.AccountInitializeView.as_view(), name='account-initialize'),
    path('accounts/<int:pk>/edit/', views.AccountUpdateView.as_view(), name='account-edit'),

    # Fiscal Year
    path('fiscal-years/', views.FiscalYearListView.as_view(), name='fiscalyear-list'),
    path('fiscal-years/create/', views.FiscalYearCreateView.as_view(), name='fiscalyear-create'),
    path('fiscal-years/<int:pk>/close/', views.FiscalYearCloseView.as_view(), name='fiscalyear-close'),
    path('fiscal-years/<int:pk>/post-opening/', views.FiscalYearPostOpeningView.as_view(), name='fiscalyear-post-opening'),

    # Cost Centers
    path('cost-centers/', views.CostCenterListView.as_view(), name='costcenter-list'),
    path('cost-centers/create/', views.CostCenterCreateView.as_view(), name='costcenter-create'),
    path('cost-centers/<int:pk>/edit/', views.CostCenterUpdateView.as_view(), name='costcenter-edit'),

    # Journal Entries
    path('journal/', views.JournalEntryListView.as_view(), name='journal-list'),
    path('journal/create/', views.JournalEntryCreateView.as_view(), name='journal-create'),
    path('journal/<int:pk>/', views.JournalEntryDetailView.as_view(), name='journal-detail'),
    path('journal/<int:pk>/post/', views.JournalEntryPostView.as_view(), name='journal-post'),
    path('journal/<int:pk>/reverse/', views.JournalEntryReverseView.as_view(), name='journal-reverse'),
    
    # Tax Types
    path('taxes/', views.TaxTypeListView.as_view(), name='taxtype-list'),
    path('taxes/create/', views.TaxTypeCreateView.as_view(), name='taxtype-create'),
    path('taxes/<int:pk>/edit/', views.TaxTypeUpdateView.as_view(), name='taxtype-edit'),

    # Notifications
    path('notifications/', views.NotificationListView.as_view(), name='notification-list'),
    path('notifications/<int:pk>/read/', views.notification_read, name='notification-read'),
    path('notifications/mark-all-read/', views.mark_all_notifications_read, name='notification-mark-all-read'),
]
