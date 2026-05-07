from django.urls import path
from .views import (
    HRDashboardView, EmployeeListView, EmployeeCreateView,
    EmployeeUpdateView, EmployeeDetailView, UserCreateView, JobTitleCreateView, DepartmentCreateView, get_user_info,
    PayrollPeriodListView, PayrollPeriodCreateView, PayrollPeriodDetailView,
    GeneratePayslipsView, PostPayrollView, PostInsuranceView, PostPaymentView, PayslipUpdateView,
    LeaveRequestListView, ApproveLeaveView, RejectLeaveView,
    LoanListView, ApproveLoanView, RejectLoanView,
    ESSDashboardView, ESSPayslipListView, ESSLeaveCreateView, ESSLoanCreateView,
    DailyAttendanceView, LeaveBalanceCreateView, LeaveBalanceUpdateView,
    EOSListView, EOSCreateView, PostEOSView
)

app_name = 'hr'

urlpatterns = [
    path('', HRDashboardView.as_view(), name='dashboard'),
    
    # Attendance
    path('attendance/', DailyAttendanceView.as_view(), name='attendance-daily'),
    
    # Employees
    path('employees/', EmployeeListView.as_view(), name='employee-list'),
    path('employees/add/', EmployeeCreateView.as_view(), name='employee-add'),
    path('employees/users/add/', UserCreateView.as_view(), name='user-add'),
    path('employees/departments/add/', DepartmentCreateView.as_view(), name='department-add'),
    path('employees/job-titles/add/', JobTitleCreateView.as_view(), name='jobtitle-add'),
    path('api/user-info/', get_user_info, name='api-user-info'),
    path('employees/<int:pk>/', EmployeeDetailView.as_view(), name='employee-detail'),
    path('employees/<int:pk>/edit/', EmployeeUpdateView.as_view(), name='employee-edit'),

    # Payroll
    path('payroll/', PayrollPeriodListView.as_view(), name='payroll-list'),
    path('payroll/add/', PayrollPeriodCreateView.as_view(), name='payroll-add'),
    path('payroll/<int:pk>/', PayrollPeriodDetailView.as_view(), name='payroll-detail'),
    path('payroll/<int:pk>/generate/', GeneratePayslipsView.as_view(), name='payroll-generate'),
    path('payroll/<int:pk>/post/', PostPayrollView.as_view(), name='payroll-post'),
    path('payroll/<int:pk>/post-insurance/', PostInsuranceView.as_view(), name='payroll-post-insurance'),
    path('payroll/<int:pk>/post-payment/', PostPaymentView.as_view(), name='payroll-post-payment'),
    path('payslips/<int:pk>/edit/', PayslipUpdateView.as_view(), name='payslip-edit'),

    # Leaves
    path('leaves/', LeaveRequestListView.as_view(), name='leave-list'),
    path('leaves/<int:pk>/approve/', ApproveLeaveView.as_view(), name='leave-approve'),
    path('leaves/<int:pk>/reject/', RejectLeaveView.as_view(), name='leave-reject'),

    # Loans
    path('loans/', LoanListView.as_view(), name='loan-list'),
    path('loans/<int:pk>/approve/', ApproveLoanView.as_view(), name='loan-approve'),
    path('loans/<int:pk>/reject/', RejectLoanView.as_view(), name='loan-reject'),

    # Employee Self-Service (ESS)
    path('ess/', ESSDashboardView.as_view(), name='ess-dashboard'),
    path('ess/payslips/', ESSPayslipListView.as_view(), name='ess-payslips'),
    path('ess/request-leave/', ESSLeaveCreateView.as_view(), name='ess-request-leave'),
    path('ess/request-loan/', ESSLoanCreateView.as_view(), name='ess-request-loan'),
    
    # Leave Balances
    path('employees/<int:emp_pk>/balances/add/', LeaveBalanceCreateView.as_view(), name='balance-add'),
    path('balances/<int:pk>/edit/', LeaveBalanceUpdateView.as_view(), name='balance-edit'),

    # End of Service
    path('eos/', EOSListView.as_view(), name='eos-list'),
    path('eos/add/', EOSCreateView.as_view(), name='eos-add'),
    path('eos/<int:pk>/post/', PostEOSView.as_view(), name='eos-post'),
]
