from django.contrib import admin
from .models import POSStation, POSSession, POSOrder, POSOrderLine, POSPayment

@admin.register(POSStation)
class POSStationAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'warehouse', 'cash_box', 'is_active']
    search_fields = ['code', 'name']
    list_filter = ['is_active', 'warehouse']

@admin.register(POSSession)
class POSSessionAdmin(admin.ModelAdmin):
    list_display = ['user', 'station', 'status', 'start_time', 'end_time', 'opening_cash']
    list_filter = ['status', 'station', 'user']
    search_fields = ['user__username', 'station__name']

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status in [POSSession.Status.CLOSED, POSSession.Status.POSTED]:
            return [f.name for f in self.model._meta.fields]
        return []

class POSOrderLineInline(admin.TabularInline):
    model = POSOrderLine
    extra = 1

    def has_change_permission(self, request, obj=None):
        if obj and obj.status in [POSOrder.Status.POSTED, POSOrder.Status.CANCELLED]:
            return False
        return super().has_change_permission(request, obj)

    def has_add_permission(self, request, obj=None):
        if obj and obj.status in [POSOrder.Status.POSTED, POSOrder.Status.CANCELLED]:
            return False
        return super().has_add_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.status in [POSOrder.Status.POSTED, POSOrder.Status.CANCELLED]:
            return False
        return super().has_delete_permission(request, obj)

class POSPaymentInline(admin.TabularInline):
    model = POSPayment
    extra = 1

    def has_change_permission(self, request, obj=None):
        if obj and obj.status in [POSOrder.Status.POSTED, POSOrder.Status.CANCELLED]:
            return False
        return super().has_change_permission(request, obj)

    def has_add_permission(self, request, obj=None):
        if obj and obj.status in [POSOrder.Status.POSTED, POSOrder.Status.CANCELLED]:
            return False
        return super().has_add_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.status in [POSOrder.Status.POSTED, POSOrder.Status.CANCELLED]:
            return False
        return super().has_delete_permission(request, obj)

@admin.register(POSOrder)
class POSOrderAdmin(admin.ModelAdmin):
    list_display = ['receipt_number', 'session', 'date', 'customer', 'grand_total', 'status']
    list_filter = ['status', 'date']
    search_fields = ['receipt_number', 'customer__name']
    inlines = [POSOrderLineInline, POSPaymentInline]

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status in [POSOrder.Status.POSTED, POSOrder.Status.CANCELLED]:
            return [f.name for f in self.model._meta.fields]
        return []
