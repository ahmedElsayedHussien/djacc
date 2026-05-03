from django.contrib import admin
from .models import (
    Department, JobTitle, Employee, EmployeeDocument,
    Shift, AttendanceRecord, LeaveType, LeaveBalance, LeaveRequest,
    PayrollPeriod, Payslip, Loan, EmployeeAsset, EndOfService
)

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'manager', 'parent')
    search_fields = ('name',)

@admin.register(JobTitle)
class JobTitleAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

class EmployeeDocumentInline(admin.TabularInline):
    model = EmployeeDocument
    extra = 1

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'national_id', 'department', 'job_title', 'status')
    list_filter = ('status', 'contract_type', 'department')
    search_fields = ('first_name', 'last_name', 'national_id')
    inlines = [EmployeeDocumentInline]

@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_time', 'end_time', 'grace_period_minutes')

@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'check_in', 'check_out', 'status', 'overtime_hours')
    list_filter = ('status', 'date')
    search_fields = ('employee__first_name', 'employee__last_name')

@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'days_allowed', 'is_paid')

@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = ('employee', 'leave_type', 'year', 'total_days', 'used_days', 'remaining_days')
    list_filter = ('year', 'leave_type')

@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('employee', 'leave_type', 'start_date', 'end_date', 'total_days', 'status')
    list_filter = ('status', 'leave_type')

class PayslipInline(admin.TabularInline):
    model = Payslip
    extra = 0

@admin.register(PayrollPeriod)
class PayrollPeriodAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_date', 'end_date', 'status')
    list_filter = ('status',)
    inlines = [PayslipInline]

@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ('employee', 'amount', 'installments_count', 'monthly_installment', 'status')
    list_filter = ('status',)

@admin.register(EmployeeAsset)
class EmployeeAssetAdmin(admin.ModelAdmin):
    list_display = ('asset_name', 'employee', 'delivery_date', 'is_returned')
    list_filter = ('is_returned',)

@admin.register(EndOfService)
class EndOfServiceAdmin(admin.ModelAdmin):
    list_display = ('employee', 'termination_date', 'total_settlement', 'is_processed')
    list_filter = ('is_processed',)
