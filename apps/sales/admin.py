from django.contrib import admin
from .models import (
    Customer, CustomerSector, SalesInvoice, SalesInvoiceLine, 
    CustomerReceipt, ReceiptAllocation, PriceList, PriceListItem, Quotation, QuotationLine,
    SalesRepresentative, SalesTarget, IntermediaryCompany,
    SalesReturn, SalesReturnLine, RepDailySettlement, RepSettlementInvoice,
)

@admin.register(SalesRepresentative)
class SalesRepresentativeAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'warehouse', 'cash_box', 'is_active')
    search_fields = ('code', 'name')
    list_filter = ('is_active',)

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

class SalesReturnLineInline(admin.TabularInline):
    model = SalesReturnLine
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

class RepSettlementInvoiceInline(admin.TabularInline):
    model = RepSettlementInvoice
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

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'account', 'phone', 'customer_type', 'is_taxable')
    search_fields = ('code', 'name', 'phone', 'email')
    list_filter = ('customer_type', 'is_taxable')

@admin.register(SalesInvoice)
class SalesInvoiceAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'customer', 'total', 'status')
    list_filter = ('status', 'date')
    search_fields = ('number', 'customer__name')
    list_select_related = ('customer',)
    inlines = [SalesInvoiceLineInline]

    def get_readonly_fields(self, request, obj=None):
        fields = ['journal_entry']
        if obj and obj.status in ['posted', 'cancelled']:
            fields += ['number', 'date', 'customer', 'payment_type', 'status', 'total', 'subtotal', 'discount_amount', 'tax_amount', 'paid_amount']
        return fields

class ReceiptAllocationInline(admin.TabularInline):
    model = ReceiptAllocation
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

@admin.register(CustomerReceipt)
class CustomerReceiptAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'customer', 'amount', 'payment_method', 'cheque_status')
    list_filter = ('payment_method', 'cheque_status', 'date')
    search_fields = ('number', 'customer__name', 'cheque_number')
    inlines = [ReceiptAllocationInline]

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.journal_entry:
            return ['number', 'date', 'customer', 'amount', 'payment_method', 'cash_box', 'bank_account', 'journal_entry', 'cheque_status']
        return []

@admin.register(IntermediaryCompany)
class IntermediaryCompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'account', 'commission_percent', 'is_active')
    search_fields = ('name',)
    list_filter = ('is_active',)

@admin.register(SalesReturn)
class SalesReturnAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'customer', 'total', 'status')
    list_filter = ('status', 'date')
    search_fields = ('number',)
    list_select_related = ('customer',)
    inlines = [SalesReturnLineInline]

    def get_readonly_fields(self, request, obj=None):
        fields = ['journal_entry']
        if obj and obj.status in ['posted', 'cancelled']:
            fields += ['number', 'date', 'customer', 'status']
        return fields

@admin.register(RepDailySettlement)
class RepDailySettlementAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'sales_rep', 'total_sales', 'cash_delivered', 'status')
    list_filter = ('status', 'date')
    search_fields = ('number',)
    list_select_related = ('sales_rep',)
    inlines = [RepSettlementInvoiceInline]
    readonly_fields = ('journal_entry',)

