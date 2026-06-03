from django.contrib import admin
from .models import (
    ItemCategory, UnitOfMeasure, Item, Warehouse, StockMovement, ItemLedger,
    WarehouseTransfer, WarehouseTransferLine, LoadingOrder, LoadingOrderLine,
    StockVoucher, StockVoucherLine,
)

POSTED_STATUSES = ['posted', 'cancelled', 'issued', 'approved']

class WarehouseTransferLineInline(admin.TabularInline):
    model = WarehouseTransferLine
    extra = 1

    def has_change_permission(self, request, obj=None):
        if obj and obj.status in POSTED_STATUSES:
            return False
        return super().has_change_permission(request, obj)

    def has_add_permission(self, request, obj=None):
        if obj and obj.status in POSTED_STATUSES:
            return False
        return super().has_add_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.status in POSTED_STATUSES:
            return False
        return super().has_delete_permission(request, obj)

class LoadedLineInline(admin.TabularInline):
    model = LoadingOrderLine
    extra = 1

    def has_change_permission(self, request, obj=None):
        if obj and obj.status in POSTED_STATUSES:
            return False
        return super().has_change_permission(request, obj)

    def has_add_permission(self, request, obj=None):
        if obj and obj.status in POSTED_STATUSES:
            return False
        return super().has_add_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.status in POSTED_STATUSES:
            return False
        return super().has_delete_permission(request, obj)

class StockVoucherLineInline(admin.TabularInline):
    model = StockVoucherLine
    extra = 1

    def has_change_permission(self, request, obj=None):
        if obj and obj.status in POSTED_STATUSES:
            return False
        return super().has_change_permission(request, obj)

    def has_add_permission(self, request, obj=None):
        if obj and obj.status in POSTED_STATUSES:
            return False
        return super().has_add_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.status in POSTED_STATUSES:
            return False
        return super().has_delete_permission(request, obj)

@admin.register(WarehouseTransfer)
class WarehouseTransferAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'from_warehouse', 'to_warehouse', 'status')
    list_filter = ('status', 'from_warehouse', 'to_warehouse', 'date')
    search_fields = ('number',)
    inlines = [WarehouseTransferLineInline]

    def get_readonly_fields(self, request, obj=None):
        fields = []
        if obj and obj.status in POSTED_STATUSES:
            fields += ['number', 'date', 'from_warehouse', 'to_warehouse', 'status']
        return fields

@admin.register(ItemCategory)
class ItemCategoryAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'parent')
    search_fields = ('code', 'name')

@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(admin.ModelAdmin):
    list_display = ('code', 'name')
    search_fields = ('code', 'name')

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'category', 'base_unit', 'standard_price', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('code', 'name')
    list_select_related = ('category', 'base_unit')

@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active', 'location')
    search_fields = ('code', 'name')
    list_filter = ('is_active',)

@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('date', 'item', 'warehouse', 'movement_type', 'quantity', 'unit_cost', 'total_cost')
    list_filter = ('movement_type', 'warehouse', 'date')
    readonly_fields = ('date', 'item', 'warehouse', 'movement_type', 'quantity', 'unit_cost', 'total_cost', 'running_quantity', 'running_value', 'reference', 'source')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

@admin.register(ItemLedger)
class ItemLedgerAdmin(admin.ModelAdmin):
    list_display = ('item', 'warehouse', 'quantity_on_hand', 'total_value', 'average_cost')
    readonly_fields = ('item', 'warehouse', 'quantity_on_hand', 'total_value', 'last_updated')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(LoadingOrder)
class LoadingOrderAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'sales_rep', 'from_warehouse', 'to_warehouse', 'status')
    list_filter = ('status', 'date')
    search_fields = ('number',)
    inlines = [LoadedLineInline]

    def get_readonly_fields(self, request, obj=None):
        fields = ['journal_entry']
        if obj and obj.status in POSTED_STATUSES:
            fields += ['number', 'date', 'sales_rep', 'from_warehouse', 'to_warehouse', 'status']
        return fields

@admin.register(StockVoucher)
class StockVoucherAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'voucher_type', 'warehouse', 'status')
    list_filter = ('status', 'voucher_type', 'warehouse')
    search_fields = ('number',)
    inlines = [StockVoucherLineInline]
    readonly_fields = ('journal_entry',)

    def get_readonly_fields(self, request, obj=None):
        fields = ['journal_entry']
        if obj and obj.status in POSTED_STATUSES:
            fields += ['number', 'date', 'voucher_type', 'warehouse', 'status', 'offset_account', 'notes']
        return fields
