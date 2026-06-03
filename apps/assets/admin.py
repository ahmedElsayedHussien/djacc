from django.contrib import admin
from .models import AssetCategory, Asset, DepreciationLog

@admin.register(AssetCategory)
class AssetCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'asset_account', 'accumulated_depreciation_account', 'depreciation_expense_account', 'default_depreciation_rate')
    search_fields = ('name',)

class DepreciationLogInline(admin.TabularInline):
    model = DepreciationLog
    extra = 0
    readonly_fields = ('journal_entry',)

@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'category', 'purchase_date', 'purchase_value', 'book_value', 'status')
    list_filter = ('status', 'category', 'purchase_date')
    search_fields = ('code', 'name')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [DepreciationLogInline]

@admin.register(DepreciationLog)
class DepreciationLogAdmin(admin.ModelAdmin):
    list_display = ('asset', 'date', 'amount')
    list_filter = ('date',)
    search_fields = ('asset__name',)
    readonly_fields = ('journal_entry',)
