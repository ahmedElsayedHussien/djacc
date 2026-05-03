from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from datetime import date, datetime
from .services import ReportService
from apps.core.models import FiscalYear

def parse_date(date_val, default=None):
    if not date_val:
        return default or date.today()
    if isinstance(date_val, str):
        try:
            return datetime.strptime(date_val, '%Y-%m-%d').date()
        except ValueError:
            return default or date.today()
    return date_val

class TrialBalanceView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/trial_balance.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from_date = parse_date(self.request.GET.get('from'), date(date.today().year, 1, 1))
        to_date = parse_date(self.request.GET.get('to'), date.today())
        
        from apps.core.models import CostCenter
        context['cost_centers'] = CostCenter.objects.filter(is_active=True)
        cc_id = self.request.GET.get('cost_center')
        if cc_id:
            context['selected_cc'] = int(cc_id)
        
        context['rows'] = ReportService.trial_balance(from_date, to_date)
        context['from_date'] = from_date
        context['to_date'] = to_date
        return context

class IncomeStatementView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/income_statement.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from_date = parse_date(self.request.GET.get('from'), date.today().replace(day=1))
        to_date = parse_date(self.request.GET.get('to'), date.today())

        from apps.core.models import CostCenter
        context['cost_centers'] = CostCenter.objects.filter(is_active=True)
        cc_id = self.request.GET.get('cost_center')
        cc_id_int = int(cc_id) if cc_id else None
        if cc_id_int:
            context['selected_cc'] = cc_id_int

        context['report'] = ReportService.income_statement(from_date, to_date, cost_center_id=cc_id_int)
        context['from_date'] = from_date
        context['to_date'] = to_date
        return context

class BalanceSheetView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/balance_sheet.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        as_of_date = parse_date(self.request.GET.get('date'), date.today())

        from apps.core.models import CostCenter
        context['cost_centers'] = CostCenter.objects.filter(is_active=True)
        cc_id = self.request.GET.get('cost_center')
        cc_id_int = int(cc_id) if cc_id else None
        if cc_id_int:
            context['selected_cc'] = cc_id_int

        context['report'] = ReportService.balance_sheet(as_of_date, cost_center_id=cc_id_int)
        context['as_of_date'] = as_of_date
        return context

class CustomerStatementView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/customer_statement.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.sales.models import Customer
        customer_id = self.request.GET.get('customer')
        from_date = parse_date(self.request.GET.get('from'), date.today().replace(day=1))
        to_date = parse_date(self.request.GET.get('to'), date.today())
        
        context['customers'] = Customer.objects.all()
        context['from_date'] = from_date
        context['to_date'] = to_date
        
        if customer_id:
            context['report'] = ReportService.customer_statement(int(customer_id), from_date, to_date)
            context['selected_customer'] = int(customer_id)
            
        return context

class StockStatusView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/stock_status.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.inventory.models import Warehouse
        warehouse_id = self.request.GET.get('warehouse')
        
        context['warehouses'] = Warehouse.objects.all()
        context['report'] = ReportService.stock_status(warehouse_id)
        if warehouse_id:
            context['selected_warehouse'] = int(warehouse_id)
            
        return context

class RepCommissionView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/rep_commission.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from_date = parse_date(self.request.GET.get('from'), date.today().replace(day=1))
        to_date = parse_date(self.request.GET.get('to'), date.today())
        context['report'] = ReportService.rep_commission_report(from_date, to_date)
        context['from_date'] = from_date
        context['to_date'] = to_date
        return context

class CostCenterStatementView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/cost_center_statement.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.core.models import CostCenter
        cost_center_id = self.request.GET.get('cost_center')
        from_date = parse_date(self.request.GET.get('from'), date.today().replace(day=1))
        to_date = parse_date(self.request.GET.get('to'), date.today())
        
        context['cost_centers'] = CostCenter.objects.all()
        context['from_date'] = from_date
        context['to_date'] = to_date
        
        if cost_center_id:
            context['report'] = ReportService.cost_center_statement(int(cost_center_id), from_date, to_date)
            context['selected_cost_center'] = int(cost_center_id)
            
        return context

class AccountStatementView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/account_statement.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.core.models import Account
        account_id = self.request.GET.get('account')
        from_date = parse_date(self.request.GET.get('from'), date.today().replace(day=1))
        to_date = parse_date(self.request.GET.get('to'), date.today())
        
        context['accounts'] = Account.objects.filter(is_leaf=True).order_by('code')
        context['from_date'] = from_date
        context['to_date'] = to_date
        
        if account_id:
            context['report'] = ReportService.account_statement(int(account_id), from_date, to_date)
            context['selected_account'] = int(account_id)
            
        return context
