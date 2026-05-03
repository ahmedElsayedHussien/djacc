from django.contrib import admin
from .models import Supplier, PurchaseOrder, PurchaseInvoice, PurchaseInvoiceLine, SupplierPayment

class PurchaseInvoiceLineInline(admin.TabularInline):
    model = PurchaseInvoiceLine
    extra = 1

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
    list_display = ('number', 'date', 'supplier', 'total')
    inlines = [PurchaseInvoiceLineInline]
    readonly_fields = ('journal_entry',)

@admin.register(SupplierPayment)
class SupplierPaymentAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'supplier', 'amount', 'payment_method')
