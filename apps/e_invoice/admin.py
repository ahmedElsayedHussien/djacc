from django.contrib import admin
from .models import CompanySettings, EInvoiceConfig, Certificate, EInvoiceLog

@admin.register(CompanySettings)
class CompanySettingsAdmin(admin.ModelAdmin):
    list_display = ['company_name_ar', 'tax_id', 'branch_code', 'is_active']
    search_fields = ['company_name_ar', 'tax_id']

@admin.register(EInvoiceConfig)
class EInvoiceConfigAdmin(admin.ModelAdmin):
    list_display = ['company', 'environment', 'auto_submit', 'is_active']
    list_filter = ['environment', 'auto_submit']

@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ['name', 'company', 'valid_until', 'is_active']
    list_filter = ['is_active']

@admin.register(EInvoiceLog)
class EInvoiceLogAdmin(admin.ModelAdmin):
    list_display = ['internal_id', 'status', 'submitted_at', 'uuid']
    list_filter = ['status']
    readonly_fields = [f.name for f in EInvoiceLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
