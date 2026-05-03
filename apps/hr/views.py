from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from .models import Employee, LeaveRequest, PayrollPeriod, EmployeeDocument
from .forms import EmployeeForm

class HRDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'hr/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_employees'] = Employee.objects.filter(status='active').count()
        context['pending_leaves'] = LeaveRequest.objects.filter(status='pending').count()
        
        # Latest payroll period
        latest_period = PayrollPeriod.objects.order_by('-start_date').first()
        context['latest_period'] = latest_period
        
        return context

# ==========================================
# Employee Management Views
# ==========================================

class EmployeeListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Employee
    template_name = 'hr/employees/list.html'
    context_object_name = 'employees'
    permission_required = 'hr.view_employee'
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset().select_related('department', 'job_title')
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(first_name__icontains=q) | qs.filter(last_name__icontains=q) | qs.filter(national_id__icontains=q)
        return qs

class EmployeeCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Employee
    form_class = EmployeeForm
    template_name = 'hr/employees/form.html'
    success_url = reverse_lazy('hr:employee-list')
    permission_required = 'hr.add_employee'

    def form_valid(self, form):
        messages.success(self.request, f'تم إضافة الموظف {form.instance.first_name} {form.instance.last_name} بنجاح.')
        return super().form_valid(form)

class EmployeeUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Employee
    form_class = EmployeeForm
    template_name = 'hr/employees/form.html'
    permission_required = 'hr.change_employee'

    def get_success_url(self):
        return reverse_lazy('hr:employee-detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, 'تم تحديث بيانات الموظف بنجاح.')
        return super().form_valid(form)

class EmployeeDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Employee
    template_name = 'hr/employees/detail.html'
    context_object_name = 'employee'
    permission_required = 'hr.view_employee'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Fetch related documents, leaves, etc.
        context['documents'] = self.object.documents.all()
        context['leave_balances'] = self.object.leave_balances.all()
        return context

# ==========================================
# Payroll Management Views
# ==========================================

from django.shortcuts import get_object_or_404, redirect
from django.views import View
from .forms import PayrollPeriodForm
from .services import PayrollService

class PayrollPeriodListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = PayrollPeriod
    template_name = 'hr/payroll/list.html'
    context_object_name = 'periods'
    permission_required = 'hr.view_payrollperiod'
    ordering = ['-start_date']

class PayrollPeriodCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = PayrollPeriod
    form_class = PayrollPeriodForm
    template_name = 'hr/payroll/form.html'
    success_url = reverse_lazy('hr:payroll-list')
    permission_required = 'hr.add_payrollperiod'

    def form_valid(self, form):
        messages.success(self.request, f'تم إنشاء فترة الرواتب: {form.instance.name}')
        return super().form_valid(form)

class PayrollPeriodDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = PayrollPeriod
    template_name = 'hr/payroll/detail.html'
    context_object_name = 'period'
    permission_required = 'hr.view_payrollperiod'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['payslips'] = self.object.payslips.select_related('employee', 'employee__job_title')
        return context

class GeneratePayslipsView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'hr.change_payrollperiod'
    
    def post(self, request, pk):
        period = get_object_or_404(PayrollPeriod, pk=pk)
        try:
            count = PayrollService.generate_payslips_for_period(period)
            if count > 0:
                messages.success(request, f'تم توليد {count} قسيمة راتب بنجاح.')
            else:
                messages.warning(request, 'لم يتم توليد قسائم جديدة. قد يكون تم توليدها مسبقاً أو لا يوجد موظفين نشطين.')
        except Exception as e:
            messages.error(request, f'حدث خطأ: {e}')
        return redirect('hr:payroll-detail', pk=pk)

class PostPayrollView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'hr.change_payrollperiod'
    
    def post(self, request, pk):
        period = get_object_or_404(PayrollPeriod, pk=pk)
        try:
            PayrollService.post_payroll(period, request.user)
            messages.success(request, 'تم اعتماد مسير الرواتب وترحيله محاسبياً بنجاح.')
        except Exception as e:
            messages.error(request, f'فشل الترحيل المحاسبي: {e}')
        return redirect('hr:payroll-detail', pk=pk)

# ==========================================
# Requests Management (Leaves & Loans)
# ==========================================
from django.utils import timezone
from django.db import transaction
from .models import LeaveBalance, Loan

class LeaveRequestListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = LeaveRequest
    template_name = 'hr/requests/leaves.html'
    context_object_name = 'requests'
    permission_required = 'hr.view_leaverequest'
    ordering = ['-applied_on']

    def get_queryset(self):
        qs = super().get_queryset().select_related('employee', 'leave_type')
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs

class ApproveLeaveView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'hr.change_leaverequest'
    
    def post(self, request, pk):
        leave = get_object_or_404(LeaveRequest, pk=pk)
        if leave.status != LeaveRequest.Status.PENDING:
            messages.error(request, 'لا يمكن تغيير حالة طلب ليس قيد الانتظار.')
            return redirect('hr:leave-list')
            
        # Check balance and deduct
        current_year = timezone.now().year
        balance = LeaveBalance.objects.filter(employee=leave.employee, leave_type=leave.leave_type, year=current_year).first()
        
        if not balance:
            messages.error(request, 'لا يوجد رصيد إجازات مسجل لهذا الموظف في السنة الحالية.')
            return redirect('hr:leave-list')
            
        if balance.remaining_days < leave.total_days:
            messages.warning(request, f'رصيد الموظف غير كافٍ. المتبقي: {balance.remaining_days} أيام، المطلوب: {leave.total_days}.')
            return redirect('hr:leave-list')
            
        # Proceed with approval
        with transaction.atomic():
            leave.status = LeaveRequest.Status.APPROVED
            leave.approved_by = request.user
            leave.save()
            
            balance.used_days += leave.total_days
            balance.save()
            
        messages.success(request, f'تم الموافقة على الإجازة للموظف {leave.employee} وخصم {leave.total_days} يوم من رصيده.')
        return redirect('hr:leave-list')

class RejectLeaveView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'hr.change_leaverequest'
    
    def post(self, request, pk):
        leave = get_object_or_404(LeaveRequest, pk=pk)
        if leave.status == LeaveRequest.Status.PENDING:
            leave.status = LeaveRequest.Status.REJECTED
            leave.approved_by = request.user
            leave.save()
            messages.success(request, 'تم رفض الطلب.')
        return redirect('hr:leave-list')

class LoanListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Loan
    template_name = 'hr/requests/loans.html'
    context_object_name = 'loans'
    permission_required = 'hr.view_loan'
    ordering = ['-request_date']

class ApproveLoanView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'hr.change_loan'
    
    def post(self, request, pk):
        loan = get_object_or_404(Loan, pk=pk)
        if loan.status == Loan.Status.PENDING:
            loan.status = Loan.Status.APPROVED
            loan.save()
            messages.success(request, 'تم الموافقة على السلفة واعتماد جدول الخصم.')
        return redirect('hr:loan-list')

class RejectLoanView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'hr.change_loan'
    
    def post(self, request, pk):
        loan = get_object_or_404(Loan, pk=pk)
        if loan.status == Loan.Status.PENDING:
            loan.status = Loan.Status.REJECTED
            loan.save()
            messages.success(request, 'تم رفض السلفة.')
        return redirect('hr:loan-list')

# ==========================================
# Employee Self-Service (ESS) Views
# ==========================================

class ESSMixin(LoginRequiredMixin):
    """Mixin to ensure user is an employee"""
    def dispatch(self, request, *args, **kwargs):
        if not hasattr(request.user, 'employee_profile') or not request.user.employee_profile:
            messages.error(request, 'حسابك غير مرتبط بملف موظف. يرجى مراجعة إدارة الموارد البشرية.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)

class ESSDashboardView(ESSMixin, TemplateView):
    template_name = 'hr/ess/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        emp = self.request.user.employee_profile
        context['employee'] = emp
        context['balances'] = emp.leave_balances.filter(year=timezone.now().year)
        context['recent_payslips'] = emp.payslips.order_by('-period__start_date')[:3]
        context['recent_leaves'] = emp.leave_requests.order_by('-applied_on')[:3]
        return context

class ESSPayslipListView(ESSMixin, ListView):
    template_name = 'hr/ess/payslips.html'
    context_object_name = 'payslips'
    
    def get_queryset(self):
        return self.request.user.employee_profile.payslips.select_related('period').order_by('-period__start_date')

from .forms import LeaveRequestForm, LoanForm

class ESSLeaveCreateView(ESSMixin, CreateView):
    model = LeaveRequest
    form_class = LeaveRequestForm
    template_name = 'hr/ess/leave_form.html'
    success_url = reverse_lazy('hr:ess-dashboard')

    def form_valid(self, form):
        form.instance.employee = self.request.user.employee_profile
        form.instance.status = LeaveRequest.Status.PENDING
        messages.success(self.request, 'تم إرسال طلب الإجازة بنجاح وهو الآن قيد المراجعة.')
        return super().form_valid(form)

class ESSLoanCreateView(ESSMixin, CreateView):
    model = Loan
    form_class = LoanForm
    template_name = 'hr/ess/loan_form.html'
    success_url = reverse_lazy('hr:ess-dashboard')

    def form_valid(self, form):
        form.instance.employee = self.request.user.employee_profile
        form.instance.status = Loan.Status.PENDING
        messages.success(self.request, 'تم إرسال طلب السلفة بنجاح وهو الآن قيد المراجعة.')
        return super().form_valid(form)
