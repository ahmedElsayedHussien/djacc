from django.urls import path
from .views import (
    HRDashboardView, EmployeeListView, EmployeeCreateView,
    EmployeeUpdateView, EmployeeDetailView, UserCreateView, JobTitleCreateView, DepartmentCreateView, get_user_info,
    PayrollPeriodListView, PayrollPeriodCreateView, PayrollPeriodDetailView,
    GeneratePayslipsView, ApprovePayrollView, PostPayrollView, PostInsuranceView, PostPaymentView, PostGovPaymentView, PayslipUpdateView,
    LeaveRequestListView, ApproveLeaveView, RejectLeaveView,
    LoanListView, ApproveLoanView, RejectLoanView,
    ESSDashboardView, ESSPayslipListView, ESSLeaveCreateView, ESSLoanCreateView,
    DailyAttendanceView, LeaveBalanceCreateView, LeaveBalanceUpdateView,
    EOSListView, EOSCreateView, PostEOSView, employee_reset_password, employee_create_user,
    setup_hr_defaults_view
)
from . import report_views


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
    path('setup-defaults/', setup_hr_defaults_view, name='setup-defaults'),
    path('employees/<int:pk>/', EmployeeDetailView.as_view(), name='employee-detail'),
    path('employees/<int:pk>/edit/', EmployeeUpdateView.as_view(), name='employee-edit'),
    path('employees/<int:pk>/reset-password/', employee_reset_password, name='employee-reset-password'),
    path('employees/<int:pk>/create-user/', employee_create_user, name='employee-create-user'),

    # Payroll
    path('payroll/', PayrollPeriodListView.as_view(), name='payroll-list'),
    path('payroll/add/', PayrollPeriodCreateView.as_view(), name='payroll-add'),
    path('payroll/<int:pk>/', PayrollPeriodDetailView.as_view(), name='payroll-detail'),
    path('payroll/<int:pk>/generate/', GeneratePayslipsView.as_view(), name='payroll-generate'),
    path('payroll/<int:pk>/approve/', ApprovePayrollView.as_view(), name='payroll-approve'),
    path('payroll/<int:pk>/post/', PostPayrollView.as_view(), name='payroll-post'),
    path('payroll/<int:pk>/post-insurance/', PostInsuranceView.as_view(), name='payroll-post-insurance'),
    path('payroll/<int:pk>/post-payment/', PostPaymentView.as_view(), name='payroll-post-payment'),
    path('payroll/<int:pk>/post-gov-payment/', PostGovPaymentView.as_view(), name='payroll-post-gov-payment'),
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

    # Reports
    path('reports/dashboard/', report_views.HRReportDashboardView.as_view(), name='report-dashboard'),
    path('reports/org-chart/', report_views.HROrgChartView.as_view(), name='report-org-chart'),
    path('reports/document-expiry/', report_views.HRDocumentExpiryView.as_view(), name='report-document-expiry'),
    path('reports/attendance-summary/', report_views.HRAttendanceSummaryView.as_view(), name='report-attendance-summary'),
    path('reports/leave-balances/', report_views.HRLeaveBalancesView.as_view(), name='report-leave-balances'),
    path('reports/payroll-register/', report_views.PayrollRegisterView.as_view(), name='report-payroll-register'),
    path('reports/payroll-cost-center/', report_views.PayrollByCostCenterView.as_view(), name='report-payroll-cost-center'),
    path('reports/payroll-taxes/', report_views.PayrollTaxInsuranceView.as_view(), name='report-payroll-taxes'),
    path('reports/loans-balance/', report_views.HRLoansBalanceView.as_view(), name='report-loans-balance'),
    path('reports/employee-assets/', report_views.HREmployeeAssetsView.as_view(), name='report-employee-assets'),
    path('reports/eos-settlements/', report_views.HREOSSettlementsView.as_view(), name='report-eos-settlements'),
]
