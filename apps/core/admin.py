from django.contrib import admin
from django.db.models import Q
from .models import Account, FiscalYear, CostCenter, JournalEntry, JournalLine, TaxType, AuditLog, SystemNotification
from .forms import AccountForm
from apps.sales.models import SalesInvoiceLine, SalesReturnLine
from apps.purchases.models import PurchaseInvoiceLine, PurchaseReturnLine
from apps.expenses.models import Expense

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'account_type', 'parent', 'is_leaf', 'is_active')
    list_filter = ('account_type', 'is_leaf', 'is_active')
    search_fields = ('code', 'name')
    ordering = ('code',)
    form = AccountForm

@admin.register(FiscalYear)
class FiscalYearAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_date', 'end_date', 'is_closed')
    list_filter = ('is_closed',)

@admin.register(CostCenter)
class CostCenterAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'parent', 'is_active')
    search_fields = ('code', 'name')

class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0
    can_delete = False

    def has_change_permission(self, request, obj=None):
        if obj and obj.is_posted:
            return False
        return super().has_change_permission(request, obj)

    def has_add_permission(self, request, obj=None):
        if obj and obj.is_posted:
            return False
        return super().has_add_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.is_posted:
            return False
        return super().has_delete_permission(request, obj)

@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'entry_type', 'description', 'is_posted')
    list_filter = ('entry_type', 'is_posted', 'date')
    search_fields = ('number', 'description', 'reference')
    inlines = [JournalLineInline]

    def get_readonly_fields(self, request, obj=None):
        fields = ['number', 'created_at']
        if obj and obj.is_posted:
            fields += ['is_posted', 'posted_by', 'posted_at', 'date', 'entry_type', 'description', 'reference', 'fiscal_year', 'is_reversed', 'reversed_by', 'reversed_at']
        return fields

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'timestamp', 'content_type', 'object_id')
    list_filter = ('action', 'timestamp', 'content_type')
    search_fields = ('notes', 'user__username')
    readonly_fields = ('user', 'action', 'timestamp', 'content_type', 'object_id', 'changes', 'notes')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

@admin.register(SystemNotification)
class SystemNotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'recipient', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at')
    search_fields = ('title', 'message', 'recipient__username')
    readonly_fields = ('recipient', 'title', 'message', 'url', 'created_at')

    def has_add_permission(self, request):
        return False

@admin.register(TaxType)
class TaxTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'rate', 'account', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('name',)

    def get_readonly_fields(self, request, obj=None):
        if obj and self._is_in_use(obj):
            return ['name', 'category', 'rate', 'account', 'is_active', 'appear_in_invoices', 'appear_in_payroll']
        return []

    def has_delete_permission(self, request, obj=None):
        if obj and self._is_in_use(obj):
            return False
        return super().has_delete_permission(request, obj)

    def _is_in_use(self, obj):
        return (
            SalesInvoiceLine.objects.filter(Q(tax_type=obj) | Q(tax_type2=obj)).exists() or
            SalesReturnLine.objects.filter(Q(tax_type=obj) | Q(tax_type2=obj)).exists() or
            PurchaseInvoiceLine.objects.filter(Q(tax_type=obj) | Q(tax_type2=obj)).exists() or
            PurchaseReturnLine.objects.filter(Q(tax_type=obj) | Q(tax_type2=obj)).exists() or
            Expense.objects.filter(Q(tax_type=obj) | Q(tax_type2=obj)).exists()
        )
