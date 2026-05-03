from django.urls import path
from .views import (
    HRDashboardView, EmployeeListView, EmployeeCreateView,
    EmployeeUpdateView, EmployeeDetailView
)

app_name = 'hr'

urlpatterns = [
    path('', HRDashboardView.as_view(), name='dashboard'),
    
    # Employees
    path('employees/', EmployeeListView.as_view(), name='employee-list'),
    path('employees/add/', EmployeeCreateView.as_view(), name='employee-add'),
    path('employees/<int:pk>/', EmployeeDetailView.as_view(), name='employee-detail'),
    path('employees/<int:pk>/edit/', EmployeeUpdateView.as_view(), name='employee-edit'),

    # Payroll
    from .views import (
        PayrollPeriodListView, PayrollPeriodCreateView, PayrollPeriodDetailView,
        GeneratePayslipsView, PostPayrollView
    )
    path('payroll/', PayrollPeriodListView.as_view(), name='payroll-list'),
    path('payroll/add/', PayrollPeriodCreateView.as_view(), name='payroll-add'),
    path('payroll/<int:pk>/', PayrollPeriodDetailView.as_view(), name='payroll-detail'),
    path('payroll/<int:pk>/generate/', GeneratePayslipsView.as_view(), name='payroll-generate'),
    path('payroll/<int:pk>/post/', PostPayrollView.as_view(), name='payroll-post'),

    # Leaves
    from .views import LeaveRequestListView, ApproveLeaveView, RejectLeaveView
    path('leaves/', LeaveRequestListView.as_view(), name='leave-list'),
    path('leaves/<int:pk>/approve/', ApproveLeaveView.as_view(), name='leave-approve'),
    path('leaves/<int:pk>/reject/', RejectLeaveView.as_view(), name='leave-reject'),

    # Loans
    from .views import LoanListView, ApproveLoanView, RejectLoanView
    path('loans/', LoanListView.as_view(), name='loan-list'),
    path('loans/<int:pk>/approve/', ApproveLoanView.as_view(), name='loan-approve'),
    path('loans/<int:pk>/reject/', RejectLoanView.as_view(), name='loan-reject'),

    # Employee Self-Service (ESS)
    from .views import ESSDashboardView, ESSPayslipListView, ESSLeaveCreateView, ESSLoanCreateView
    path('ess/', ESSDashboardView.as_view(), name='ess-dashboard'),
    path('ess/payslips/', ESSPayslipListView.as_view(), name='ess-payslips'),
    path('ess/request-leave/', ESSLeaveCreateView.as_view(), name='ess-request-leave'),
    path('ess/request-loan/', ESSLoanCreateView.as_view(), name='ess-request-loan'),
]
