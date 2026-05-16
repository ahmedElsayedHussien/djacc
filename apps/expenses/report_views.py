from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from datetime import date
from apps.reports.services import ReportService
from .models import CustodySettlement

class ExpenseReportDashboardView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = 'expenses/reports/dashboard_links.html'
    permission_required = 'expenses.view_expense'

class ExpensesByCategoryView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = 'expenses/reports/by_category.html'
    permission_required = 'expenses.view_expense'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from_date = self.request.GET.get('from', date.today().replace(day=1).isoformat())
        to_date = self.request.GET.get('to', date.today().isoformat())
        
        context['report'] = ReportService.expenses_by_category(date.fromisoformat(from_date), date.fromisoformat(to_date))
        context['from_date'] = from_date
        context['to_date'] = to_date
        return context

class ExpensesByCostCenterView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = 'expenses/reports/by_cost_center.html'
    permission_required = 'expenses.view_expense'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from_date = self.request.GET.get('from', date.today().replace(day=1).isoformat())
        to_date = self.request.GET.get('to', date.today().isoformat())
        
        context['report'] = ReportService.expenses_by_cost_center(date.fromisoformat(from_date), date.fromisoformat(to_date))
        context['from_date'] = from_date
        context['to_date'] = to_date
        return context

class ExpenseTaxReportView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = 'expenses/reports/tax_report.html'
    permission_required = 'expenses.view_expense'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from_date = self.request.GET.get('from', date.today().replace(day=1).isoformat())
        to_date = self.request.GET.get('to', date.today().isoformat())
        
        context['report'] = ReportService.expense_tax_report(date.fromisoformat(from_date), date.fromisoformat(to_date))
        context['from_date'] = from_date
        context['to_date'] = to_date
        return context

class OutstandingCustodiesView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = 'expenses/reports/outstanding_custodies.html'
    permission_required = 'expenses.view_custody'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report'] = ReportService.outstanding_custodies_summary()
        return context

class CustodySettlementStatementView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = 'expenses/reports/settlement_statement.html'
    permission_required = 'expenses.view_custodysettlement'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        settlement_id = self.request.GET.get('settlement')
        context['settlements'] = CustodySettlement.objects.filter(is_posted=True).order_by('-date')
        
        if settlement_id:
            context['data'] = ReportService.custody_settlement_detail(int(settlement_id))
            context['selected_settlement'] = int(settlement_id)
        return context

class AgedCustodiesView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = 'expenses/reports/aged_custodies.html'
    permission_required = 'expenses.view_custody'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report'] = ReportService.aged_custodies_report()
        return context

class ExpensesByPaymentMethodView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = 'expenses/reports/by_payment_method.html'
    permission_required = 'expenses.view_expense'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from_date = self.request.GET.get('from', date.today().replace(day=1).isoformat())
        to_date = self.request.GET.get('to', date.today().isoformat())
        
        context['report'] = ReportService.expenses_by_payment_method(date.fromisoformat(from_date), date.fromisoformat(to_date))
        context['from_date'] = from_date
        context['to_date'] = to_date
        return context
