from django.contrib import admin
from .models import Supplier, PurchaseOrder, PurchaseInvoice, PurchaseInvoiceLine, SupplierPayment, PurchaseReturn, PurchaseReturnLine, PaymentAllocation

class PurchaseInvoiceLineInline(admin.TabularInline):
    model = PurchaseInvoiceLine
    extra = 1

    def has_change_permission(self, request, obj=None):
        if obj and obj.status in ['posted', 'cancelled']:
            return False
        return super().has_change_permission(request, obj)

    def has_add_permission(self, request, obj=None):
        if obj and obj.status in ['posted', 'cancelled']:
            return False
        return super().has_add_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.status in ['posted', 'cancelled']:
            return False
        return super().has_delete_permission(request, obj)

class PaymentAllocationInline(admin.TabularInline):
    model = PaymentAllocation
    extra = 1
    readonly_fields = ('invoice', 'amount')

    def has_add_permission(self, request, obj=None):
        if obj and obj.journal_entry:
            return False
        return super().has_add_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        if obj and obj.journal_entry:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.journal_entry:
            return False
        return super().has_delete_permission(request, obj)

class PurchaseReturnLineInline(admin.TabularInline):
    model = PurchaseReturnLine
    extra = 1

    def has_change_permission(self, request, obj=None):
        if obj and obj.status in ['posted', 'cancelled']:
            return False
        return super().has_change_permission(request, obj)

    def has_add_permission(self, request, obj=None):
        if obj and obj.status in ['posted', 'cancelled']:
            return False
        return super().has_add_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.status in ['posted', 'cancelled']:
            return False
        return super().has_delete_permission(request, obj)

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'account')
    search_fields = ('code', 'name')

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'supplier', 'status')
    list_filter = ('status',)

@admin.register(PurchaseInvoice)
class PurchaseInvoiceAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'supplier', 'total', 'status')
    list_filter = ('status', 'date')
    search_fields = ('number', 'supplier__name')
    inlines = [PurchaseInvoiceLineInline]

    def get_readonly_fields(self, request, obj=None):
        fields = ['journal_entry']
        if obj and obj.status in ['posted', 'cancelled']:
            fields += ['number', 'date', 'supplier', 'payment_type', 'payment_method', 'cash_box', 'bank_account', 'cost_center', 'due_date', 'supplier_invoice_number', 'total', 'subtotal', 'discount_amount', 'tax_amount', 'paid_amount', 'status']
        return fields

@admin.register(SupplierPayment)
class SupplierPaymentAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'supplier', 'amount', 'payment_method', 'is_cleared')
    list_filter = ('payment_method', 'is_cleared', 'date')
    search_fields = ('number', 'supplier__name', 'cheque_number')
    inlines = [PaymentAllocationInline]

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.journal_entry:
            return ['number', 'date', 'supplier', 'amount', 'payment_method', 'cash_box', 'bank_account', 'journal_entry', 'is_cleared']
        return []

@admin.register(PurchaseReturn)
class PurchaseReturnAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'supplier', 'total', 'status')
    list_filter = ('status', 'date')
    search_fields = ('number',)
    inlines = [PurchaseReturnLineInline]

    def get_readonly_fields(self, request, obj=None):
        fields = ['journal_entry']
        if obj and obj.status in ['posted', 'cancelled']:
            fields += ['number', 'date', 'supplier', 'invoice', 'cost_center', 'total', 'subtotal', 'discount_amount', 'tax_amount', 'status']
        return fields
