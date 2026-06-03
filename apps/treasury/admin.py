from django.contrib import admin
from .models import CashBox, BankAccount, BankTransaction, BankReconciliation, CashTransfer, MobileWallet

@admin.register(CashBox)
class CashBoxAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'account', 'responsible_user')
    search_fields = ('code', 'name')
    list_filter = ('is_active',)

@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'bank_name', 'account_number')
    search_fields = ('code', 'name', 'bank_name', 'account_number')
    list_filter = ('is_active',)

@admin.register(MobileWallet)
class MobileWalletAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'provider', 'mobile_number', 'account', 'is_active')
    search_fields = ('code', 'name', 'mobile_number')
    list_filter = ('is_active', 'provider')

@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'bank_account', 'transaction_type', 'amount', 'is_reconciled')
    list_filter = ('transaction_type', 'is_reconciled')
    search_fields = ('number', 'reference', 'description')
    date_hierarchy = 'date'

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.is_reconciled:
            return [f.name for f in self.model._meta.fields]
        return []

@admin.register(BankReconciliation)
class BankReconciliationAdmin(admin.ModelAdmin):
    list_display = ('bank_account', 'statement_date', 'statement_balance', 'book_balance', 'difference', 'is_reconciled', 'status')
    list_filter = ('status',)
    search_fields = ('bank_account__name',)

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.is_reconciled:
            return [f.name for f in self.model._meta.fields]
        return []

@admin.register(CashTransfer)
class CashTransferAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'amount', 'description', 'status')
    list_filter = ('status',)
    search_fields = ('number', 'description')
    date_hierarchy = 'date'

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status in [CashTransfer.Status.COMPLETED, CashTransfer.Status.CANCELLED]:
            return [f.name for f in self.model._meta.fields]
        return []
