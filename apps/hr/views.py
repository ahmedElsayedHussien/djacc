from datetime import date
from decimal import Decimal
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.db import transaction
from django.contrib import messages
from .models import Employee, LeaveRequest, PayrollPeriod, EmployeeDocument, Loan, LeaveBalance, JobTitle, Department
from .forms import EmployeeForm, PayrollPeriodForm, LeaveRequestForm, LoanForm, UserForm, JobTitleForm, DepartmentForm
from django.contrib.auth.models import User

class DepartmentCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Department
    form_class = DepartmentForm
    template_name = 'hr/departments/form.html'
    permission_required = 'hr.add_department'
    success_url = reverse_lazy('hr:employee-add')

    def form_valid(self, form):
        messages.success(self.request, "تم إنشاء القسم بنجاح")
        return super().form_valid(form)

class JobTitleCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = JobTitle
    form_class = JobTitleForm
    template_name = 'hr/job_titles/form.html'
    permission_required = 'hr.add_jobtitle'
    success_url = reverse_lazy('hr:employee-add')

    def form_valid(self, form):
        messages.success(self.request, "تم إنشاء المسمى الوظيفي بنجاح")
        return super().form_valid(form)

class UserCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = User
    form_class = UserForm
    template_name = 'hr/users/form.html'
    permission_required = 'auth.add_user'
    success_url = reverse_lazy('hr:employee-add')

    def form_valid(self, form):
        messages.success(self.request, "تم إنشاء المستخدم بنجاح")
        return super().form_valid(form)

def get_user_info(request):
    user_id = request.GET.get('user_id')
    if user_id:
        try:
            user = User.objects.get(id=user_id)
            return JsonResponse({
                'first_name': user.first_name,
                'last_name': user.last_name,
                'email': user.email
            })
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found'}, status=404)
    return JsonResponse({'error': 'No user_id provided'}, status=400)

class HRDashboardView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'hr.view_employee'
    template_name = 'hr/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_employees'] = Employee.objects.filter(status='active').count()
        context['pending_leaves'] = LeaveRequest.objects.filter(status='pending').count()
        
        # New Stats
        context['pending_loans'] = Loan.objects.filter(status='pending').count()
        context['expiring_docs_count'] = EmployeeDocument.objects.filter(
            expiry_date__lte=date.today()
        ).count()

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
        # التعامل مع القسم الجديد إذا تم إدخاله يدوياً
        new_dept_name = self.request.POST.get('new_department')
        if new_dept_name:
            new_dept, created = Department.objects.get_or_create(name=new_dept_name)
            form.instance.department = new_dept

        # التعامل مع المسمى الوظيفي الجديد إذا تم إدخاله يدوياً
        new_title_name = self.request.POST.get('new_job_title')
        if new_title_name:
            new_title, created = JobTitle.objects.get_or_create(name=new_title_name)
            form.instance.job_title = new_title
            
        messages.success(self.request, f'تم إضافة الموظف {form.instance.first_name} {form.instance.last_name} بنجاح.')
        return super().form_valid(form)

class EmployeeUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Employee
    form_class = EmployeeForm
    template_name = 'hr/employees/form.html'
    success_url = reverse_lazy('hr:employee-list')
    permission_required = 'hr.change_employee'

    def form_valid(self, form):
        # التعامل مع القسم الجديد إذا تم إدخاله يدوياً
        new_dept_name = self.request.POST.get('new_department')
        if new_dept_name:
            new_dept, created = Department.objects.get_or_create(name=new_dept_name)
            form.instance.department = new_dept

        # التعامل مع المسمى الوظيفي الجديد إذا تم إدخاله يدوياً
        new_title_name = self.request.POST.get('new_job_title')
        if new_title_name:
            new_title, created = JobTitle.objects.get_or_create(name=new_title_name)
            form.instance.job_title = new_title

        messages.success(self.request, f'تم تحديث بيانات الموظف {form.instance.first_name} بنجاح.')
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
        context['payslips'] = self.object.payslips.select_related('period').order_by('-period__start_date')
        context['loans'] = self.object.loans.all().order_by('-request_date')
        return context

# ==========================================
# Payroll Management Views
# ==========================================

from django.shortcuts import get_object_or_404, redirect
from django.views import View
from .forms import PayrollPeriodForm, LeaveBalanceForm
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
        
        from apps.treasury.models import BankAccount, CashBox
        context['bank_accounts'] = BankAccount.objects.all()
        context['cash_boxes'] = CashBox.objects.all()
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

class ApprovePayrollView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """✅ Bug #6 Fix: خطوة الاعتماد المفقودة (DRAFT → APPROVED) قبل الترحيل المحاسبي."""
    permission_required = 'hr.change_payrollperiod'

    def post(self, request, pk):
        period = get_object_or_404(PayrollPeriod, pk=pk)
        if period.status != PayrollPeriod.Status.DRAFT:
            messages.error(request, f'لا يمكن اعتماد فترة بحالة: {period.get_status_display()}')
            return redirect('hr:payroll-detail', pk=pk)
        period.status = PayrollPeriod.Status.APPROVED
        period.save(update_fields=['status'])
        messages.success(request, f'تم اعتماد فترة الرواتب "{period.name}" — يمكنك الآن الترحيل المحاسبي.')
        return redirect('hr:payroll-detail', pk=pk)


class PostInsuranceView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'hr.change_payrollperiod'
    
    def post(self, request, pk):
        period = get_object_or_404(PayrollPeriod, pk=pk)
        rate = Decimal(request.POST.get('employer_rate', '18.75')) # Default Egyptian employer rate
        try:
            PayrollService.post_insurance_entry(period, rate / Decimal(100), request.user)
            messages.success(request, 'تم إنشاء قيد التأمينات الاجتماعية بنجاح.')
        except Exception as e:
            messages.error(request, f'فشل إنشاء قيد التأمينات: {e}')
        return redirect('hr:payroll-detail', pk=pk)

class PostPaymentView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'hr.change_payrollperiod'
    
    def post(self, request, pk):
        period = get_object_or_404(PayrollPeriod, pk=pk)
        from apps.treasury.models import BankAccount, CashBox
        
        # Determine source of payment (Bank or Cash)
        source_id = request.POST.get('source_id')
        source_type = request.POST.get('source_type')
        
        try:
            if source_type == 'bank':
                acc = get_object_or_404(BankAccount, pk=source_id).account
            else:
                acc = get_object_or_404(CashBox, pk=source_id).account
                
            PayrollService.post_payment_entry(period, acc, request.user)
            messages.success(request, 'تم إثبات صرف الرواتب بنجاح.')
        except Exception as e:
            messages.error(request, f'فشل إثبات الصرف: {e}')
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

        # ✅ Atomicity Fix: التحقق من الرصيد وخصمه داخل transaction واحدة مع select_for_update
        # لمنع Race Condition في حالة موافقة على طلبين في نفس الوقت
        with transaction.atomic():
            balance = LeaveBalance.objects.select_for_update().filter(
                employee=leave.employee,
                leave_type=leave.leave_type,
                year=leave.start_date.year
            ).first()

            if not balance:
                messages.error(request, 'لا يوجد رصيد إجازات مسجل لهذا الموظف في السنة الحالية.')
                return redirect('hr:leave-list')

            if balance.remaining_days < leave.total_days:
                messages.warning(request, f'رصيد الموظف غير كافٍ. المتبقي: {balance.remaining_days} أيام، المطلوب: {leave.total_days}.')
                return redirect('hr:leave-list')

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

# ==========================================
# Payslip Management (Manual Adjustments)
# ==========================================
from .models import Payslip, PayslipItem
from .forms import PayslipForm, PayslipItemFormSet

class PayslipUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Payslip
    form_class = PayslipForm
    template_name = 'hr/payroll/payslip_form.html'
    permission_required = 'hr.change_payslip'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['items_formset'] = PayslipItemFormSet(self.request.POST, instance=self.object)
        else:
            context['items_formset'] = PayslipItemFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        items_formset = context['items_formset']
        
        if items_formset.is_valid():
            payslip = form.save(commit=False)
            items = items_formset.save(commit=False)
            
            for obj in items_formset.deleted_objects:
                obj.delete()
                
            for item in items:
                item.payslip = payslip
                item.save()

            # حساب المجاميع من البنود المتغيرة
            total_additions = sum(item.amount for item in payslip.items.filter(item_type=PayslipItem.ItemType.ADDITION))
            total_deductions_other = sum(item.amount for item in payslip.items.filter(item_type=PayslipItem.ItemType.DEDUCTION))

            payslip.other_additions = total_additions
            payslip.other_deductions = total_deductions_other

            # Recalculate Net Salary
            payslip.net_salary = (
                payslip.basic_salary 
                + payslip.total_allowances 
                + payslip.other_additions
                - payslip.total_deductions 
                - payslip.other_deductions
                - payslip.social_insurance 
                - payslip.income_tax
            )
            payslip.save()
            messages.success(self.request, 'تم تحديث تفاصيل القسيمة والبنود الإضافية بنجاح.')
            return redirect(reverse_lazy('hr:payroll-detail', kwargs={'pk': payslip.period.pk}))
        else:
            return self.render_to_response(self.get_context_data(form=form))


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

# ==========================================
# Attendance Management
# ==========================================
from .models import AttendanceRecord

class DailyAttendanceView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'hr.add_attendancerecord'
    template_name = 'hr/attendance/daily.html'

    def get(self, request):
        date_str = request.GET.get('date', date.today().isoformat())
        target_date = date.fromisoformat(date_str)
        
        employees = Employee.objects.filter(status='active').select_related('department', 'job_title')
        
        # Get existing records for this date
        records = AttendanceRecord.objects.filter(date=target_date)
        records_dict = {r.employee_id: r for r in records}
        
        context = {
            'employees': employees,
            'target_date': target_date,
            'records_dict': records_dict,
            'status_choices': AttendanceRecord.Status.choices,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        date_str = request.POST.get('date')
        target_date = date.fromisoformat(date_str)
        
        employees = Employee.objects.filter(status='active')
        
        with transaction.atomic():
            for emp in employees:
                status = request.POST.get(f'status_{emp.id}')
                check_in = request.POST.get(f'check_in_{emp.id}')
                check_out = request.POST.get(f'check_out_{emp.id}')
                
                # Update or create
                AttendanceRecord.objects.update_or_create(
                    employee=emp,
                    date=target_date,
                    defaults={
                        'status': status,
                        'check_in': check_in if check_in else None,
                        'check_out': check_out if check_out else None,
                    }
                )
        
        messages.success(request, f'تم حفظ سجل الحضور ليوم {target_date} بنجاح.')
        return redirect(reverse_lazy('hr:attendance-daily') + f'?date={date_str}')

class LeaveBalanceCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = LeaveBalance
    form_class = LeaveBalanceForm
    template_name = 'hr/leaves/balance_form.html'
    permission_required = 'hr.add_leavebalance'

    def form_valid(self, form):
        employee = get_object_or_404(Employee, pk=self.kwargs.get('emp_pk'))
        form.instance.employee = employee
        messages.success(self.request, f'تم إضافة رصيد إجازات للموظف {employee.first_name}')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('hr:employee-detail', kwargs={'pk': self.kwargs.get('emp_pk')})

class LeaveBalanceUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = LeaveBalance
    form_class = LeaveBalanceForm
    template_name = 'hr/leaves/balance_form.html'
    permission_required = 'hr.change_leavebalance'

    def form_valid(self, form):
        messages.success(self.request, 'تم تحديث رصيد الإجازات بنجاح.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('hr:employee-detail', kwargs={'pk': self.object.employee.pk})

from .models import EndOfService
# Form will be added to forms.py next
class EOSListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = EndOfService
    template_name = 'hr/eos/list.html'
    context_object_name = 'records'
    permission_required = 'hr.view_endofservice'

class EOSCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = EndOfService
    fields = ['employee', 'termination_date', 'reason', 'assets_returned', 'loans_settled', 'severance_pay', 'leave_encashment', 'total_settlement']
    template_name = 'hr/eos/form.html'
    permission_required = 'hr.add_endofservice'
    success_url = reverse_lazy('hr:eos-list')

    def form_valid(self, form):
        messages.success(self.request, f'تم إنشاء نموذج نهاية خدمة للموظف {form.instance.employee}')
        return super().form_valid(form)

class PostEOSView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'hr.change_endofservice'
    
    def post(self, request, pk):
        record = get_object_or_404(EndOfService, pk=pk)
        try:
            from .services import EOSService
            EOSService.process_settlement(record, request.user)
            messages.success(request, 'تم ترحيل تسوية نهاية الخدمة بنجاح.')
        except Exception as e:
            messages.error(request, f'فشل الترحيل: {e}')
        return redirect('hr:eos-list')

