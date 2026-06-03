from django.contrib import admin
from .models import ExpenseCategory, Expense, Custody, CustodySettlement

POSTED_STATUSES = [Expense.Status.POSTED, Expense.Status.REVERSED, Expense.Status.APPROVED]
SETTLED_STATUSES = [Custody.Status.SETTLED, Custody.Status.PARTIALLY_SETTLED]

@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'account')

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'category', 'amount', 'payment_method', 'status')
    list_filter = ('status', 'payment_method')
    search_fields = ('number', 'description')

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status in POSTED_STATUSES:
            return ['number', 'date', 'category', 'subtotal', 'amount', 'payment_method', 'cash_box', 'bank_account', 'custody', 'journal_entry', 'status', 'attachment']
        return []

@admin.register(Custody)
class CustodyAdmin(admin.ModelAdmin):
    list_display = ('number', 'employee', 'amount', 'status')
    list_filter = ('status',)

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status in SETTLED_STATUSES:
            return ['number', 'employee', 'amount', 'account', 'cash_box', 'journal_entry', 'status']
        return []

@admin.register(CustodySettlement)
class CustodySettlementAdmin(admin.ModelAdmin):
    list_display = ('custody', 'date', 'expenses_amount', 'returned_amount')

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.is_posted:
            return ['custody', 'date', 'expenses_amount', 'returned_amount', 'cash_box', 'journal_entry', 'is_posted']
        return []
