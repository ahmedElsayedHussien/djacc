from django.contrib import admin
from .models import CashBox, BankAccount, BankTransaction, BankReconciliation, CashTransfer

@admin.register(CashBox)
class CashBoxAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'account', 'responsible_user')

@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'bank_name', 'account_number')

@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'bank_account', 'transaction_type', 'amount', 'is_reconciled')
    list_filter = ('transaction_type', 'is_reconciled')

@admin.register(BankReconciliation)
class BankReconciliationAdmin(admin.ModelAdmin):
    list_display = ('bank_account', 'statement_date', 'difference', 'is_reconciled')

@admin.register(CashTransfer)
class CashTransferAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'amount', 'description')
