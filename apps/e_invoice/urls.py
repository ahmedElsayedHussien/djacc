from django.urls import path
from . import views

app_name = 'e_invoice'

urlpatterns = [
    path('', views.EInvoiceDashboardView.as_view(), name='dashboard'),
    path('settings/', views.CompanySettingsUpdateView.as_view(), name='company-settings'),
    path('config/', views.EInvoiceConfigUpdateView.as_view(), name='config'),
    path('certificates/', views.CertificateListView.as_view(), name='certificate-list'),
    path('certificates/add/', views.CertificateCreateView.as_view(), name='certificate-create'),
    path('certificates/<int:pk>/update/', views.CertificateUpdateView.as_view(), name='certificate-update'),
    path('bulk-submit/', views.BulkSubmitEInvoiceView.as_view(), name='bulk-submit'),
    path('log/<int:pk>/', views.EInvoiceLogDetailView.as_view(), name='log-detail'),
]
