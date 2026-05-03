from django.contrib import admin
from .models import Account, FiscalYear, CostCenter, JournalEntry, JournalLine

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'account_type', 'parent', 'is_leaf', 'is_active')
    list_filter = ('account_type', 'is_leaf', 'is_active')
    search_fields = ('code', 'name')
    ordering = ('code',)

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
    extra = 2

@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'entry_type', 'description', 'is_posted')
    list_filter = ('entry_type', 'is_posted', 'date')
    search_fields = ('number', 'description', 'reference')
    inlines = [JournalLineInline]
    readonly_fields = ('number', 'created_at')
