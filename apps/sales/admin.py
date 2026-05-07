from django.contrib import admin
from .models import (
    Customer, CustomerSector, SalesInvoice, SalesInvoiceLine, 
    CustomerReceipt, ReceiptAllocation, PriceList, PriceListItem, Quotation, QuotationLine,
    SalesRepresentative, SalesTarget
)

@admin.register(SalesRepresentative)
class SalesRepresentativeAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'warehouse', 'cash_box', 'is_active')
    search_fields = ('code', 'name')

@admin.register(SalesTarget)
class SalesTargetAdmin(admin.ModelAdmin):
    list_display = ('sales_rep', 'target_amount', 'start_date', 'end_date')
    list_filter = ('start_date', 'sales_rep')

@admin.register(CustomerSector)
class CustomerSectorAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')

class PriceListItemInline(admin.TabularInline):
    model = PriceListItem
    extra = 1

@admin.register(PriceList)
class PriceListAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_default', 'is_active')
    inlines = [PriceListItemInline]

class QuotationLineInline(admin.TabularInline):
    model = QuotationLine
    extra = 1

@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ('number', 'name', 'sector', 'start_date', 'end_date', 'status')
    inlines = [QuotationLineInline]



class SalesInvoiceLineInline(admin.TabularInline):
    model = SalesInvoiceLine
    extra = 1

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'account', 'phone')
    search_fields = ('code', 'name')

@admin.register(SalesInvoice)
class SalesInvoiceAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'customer', 'total', 'status')
    list_filter = ('status', 'date')
    inlines = [SalesInvoiceLineInline]
    readonly_fields = ('journal_entry',)

@admin.register(CustomerReceipt)
class CustomerReceiptAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'customer', 'amount', 'payment_method')
    list_filter = ('payment_method', 'date')
