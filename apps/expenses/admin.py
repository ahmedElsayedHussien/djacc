from django.contrib import admin
from .models import ExpenseCategory, Expense, Custody, CustodySettlement

@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'account')

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'category', 'amount', 'payment_method', 'status')
    list_filter = ('status', 'payment_method')
    search_fields = ('number', 'description')

@admin.register(Custody)
class CustodyAdmin(admin.ModelAdmin):
    list_display = ('number', 'employee', 'amount', 'status')
    list_filter = ('status',)

@admin.register(CustodySettlement)
class CustodySettlementAdmin(admin.ModelAdmin):
    list_display = ('custody', 'date', 'expenses_amount', 'returned_amount')
