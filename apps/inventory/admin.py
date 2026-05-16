from django.contrib import admin
from .models import ItemCategory, UnitOfMeasure, Item, Warehouse, StockMovement, ItemLedger, WarehouseTransfer, WarehouseTransferLine

class WarehouseTransferLineInline(admin.TabularInline):
    model = WarehouseTransferLine
    extra = 1

@admin.register(WarehouseTransfer)
class WarehouseTransferAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'from_warehouse', 'to_warehouse', 'status')
    list_filter = ('status', 'from_warehouse', 'to_warehouse', 'date')
    inlines = [WarehouseTransferLineInline]


@admin.register(ItemCategory)
class ItemCategoryAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'parent')

@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(admin.ModelAdmin):
    list_display = ('code', 'name')

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'category', 'base_unit', 'standard_price', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('code', 'name')

@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active')

@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('date', 'item', 'warehouse', 'movement_type', 'quantity', 'unit_cost', 'total_cost')
    list_filter = ('movement_type', 'warehouse', 'date')
    readonly_fields = ('running_quantity', 'running_value')

@admin.register(ItemLedger)
class ItemLedgerAdmin(admin.ModelAdmin):
    list_display = ('item', 'warehouse', 'quantity_on_hand', 'total_value', 'average_cost')
    readonly_fields = ('quantity_on_hand', 'total_value', 'last_updated')
