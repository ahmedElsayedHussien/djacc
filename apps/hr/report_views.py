from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from datetime import date
from apps.reports.services import ReportService
from .models import PayrollPeriod

class HRReportDashboardView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = 'hr/reports/dashboard_links.html'
    permission_required = 'hr.view_employee'

class HROrgChartView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = 'hr/reports/org_chart.html'
    permission_required = 'hr.view_employee'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report'] = ReportService.hr_org_chart_summary()
        return context

class HRDocumentExpiryView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = 'hr/reports/document_expiry.html'
    permission_required = 'hr.view_employee'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        days = self.request.GET.get('days', 30)
        context['report'] = ReportService.hr_document_expiry_report(int(days))
        context['selected_days'] = int(days)
        return context

class HRAttendanceSummaryView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = 'hr/reports/attendance_summary.html'
    permission_required = 'hr.view_attendancerecord'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from_date = self.request.GET.get('from', date.today().replace(day=1).isoformat())
        to_date = self.request.GET.get('to', date.today().isoformat())
        
        context['report'] = ReportService.hr_attendance_summary(date.fromisoformat(from_date), date.fromisoformat(to_date))
        context['from_date'] = from_date
        context['to_date'] = to_date
        return context

class HRLeaveBalancesView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = 'hr/reports/leave_balances.html'
    permission_required = 'hr.view_leavebalance'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report'] = ReportService.hr_leave_balances_report()
        return context

class PayrollRegisterView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = 'hr/reports/payroll_register.html'
    permission_required = 'hr.view_payslip'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        period_id = self.request.GET.get('period')
        context['periods'] = PayrollPeriod.objects.all().order_by('-start_date')
        
        if period_id:
            context['report'] = ReportService.payroll_register_report(int(period_id))
            context['selected_period'] = int(period_id)
        return context

class PayrollByCostCenterView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = 'hr/reports/payroll_cost_center.html'
    permission_required = 'hr.view_payslip'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        period_id = self.request.GET.get('period')
        context['periods'] = PayrollPeriod.objects.all().order_by('-start_date')
        
        if period_id:
            context['report'] = ReportService.payroll_by_cost_center_report(int(period_id))
            context['selected_period'] = int(period_id)
        return context

class PayrollTaxInsuranceView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = 'hr/reports/payroll_taxes.html'
    permission_required = 'hr.view_payslip'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        period_id = self.request.GET.get('period')
        context['periods'] = PayrollPeriod.objects.all().order_by('-start_date')
        
        if period_id:
            context['report'] = ReportService.payroll_tax_insurance_report(int(period_id))
            context['selected_period'] = int(period_id)
        return context

class HRLoansBalanceView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = 'hr/reports/loans_balance.html'
    permission_required = 'hr.view_loan'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report'] = ReportService.hr_loans_balance_report()
        return context

class HREmployeeAssetsView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = 'hr/reports/employee_assets.html'
    permission_required = 'hr.view_employeeasset'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report'] = ReportService.hr_employee_assets_report()
        return context

class HREOSSettlementsView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = 'hr/reports/eos_settlements.html'
    permission_required = 'hr.view_endofservice'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report'] = ReportService.hr_eos_settlements_report()
        return context
