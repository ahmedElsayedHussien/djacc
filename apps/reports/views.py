from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.utils import timezone
from django.core.paginator import Paginator
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

class FinancialReportDashboardView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'core.view_account'
    template_name = 'reports/financial_dashboard.html'

class TrialBalanceView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'core.view_account'
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
        
        rows = ReportService.trial_balance(from_date, to_date)
        context['rows'] = rows
        
        # Calculate totals
        totals = {
            'op_debit': sum(row['op_debit'] for row in rows),
            'op_credit': sum(row['op_credit'] for row in rows),
            'mov_debit': sum(row['mov_debit'] for row in rows),
            'mov_credit': sum(row['mov_credit'] for row in rows),
            'cl_debit': sum(row['cl_debit'] for row in rows),
            'cl_credit': sum(row['cl_credit'] for row in rows),
        }
        context['totals'] = totals
        
        context['from_date'] = from_date
        context['to_date'] = to_date
        return context

class IncomeStatementView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'core.view_account'
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

class BalanceSheetView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'core.view_account'
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

class CustomerStatementView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'sales.view_customer'
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
class SupplierStatementView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'purchases.view_supplier'
    template_name = 'reports/supplier_statement.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.purchases.models import Supplier
        supplier_id = self.request.GET.get('supplier')
        from_date = parse_date(self.request.GET.get('from'), date.today().replace(day=1))
        to_date = parse_date(self.request.GET.get('to'), date.today())
        
        context['suppliers'] = Supplier.objects.all()
        context['from_date'] = from_date
        context['to_date'] = to_date
        
        if supplier_id:
            context['report'] = ReportService.supplier_statement(int(supplier_id), from_date, to_date)
            context['selected_supplier'] = int(supplier_id)
            
        return context

class RepStatementView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'sales.view_salesrepresentative'
    template_name = 'reports/rep_statement.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.sales.models import SalesRepresentative
        rep_id = self.request.GET.get('rep')
        from_date = parse_date(self.request.GET.get('from'), date.today().replace(day=1))
        to_date = parse_date(self.request.GET.get('to'), date.today())
        
        context['reps'] = SalesRepresentative.objects.all()
        context['from_date'] = from_date
        context['to_date'] = to_date
        
        if rep_id:
            context['report'] = ReportService.rep_statement(int(rep_id), from_date, to_date)
            context['selected_rep'] = int(rep_id)
            
        return context

class StockStatusView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'inventory.view_item'
    template_name = 'reports/stock_status.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.inventory.models import Warehouse
        warehouse_id = self.request.GET.get('warehouse')
        
        context['warehouses'] = Warehouse.objects.all()
        report_data = ReportService.stock_status(warehouse_id)
        
        paginator = Paginator(report_data['items'], 50)
        page_number = self.request.GET.get('page')
        report_data['items'] = paginator.get_page(page_number)
        
        context['report'] = report_data
        if warehouse_id:
            context['selected_warehouse'] = int(warehouse_id)


            
        return context

class RepCommissionView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'sales.view_salesrepresentative'
    template_name = 'reports/rep_commission.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from_date = parse_date(self.request.GET.get('from'), date.today().replace(day=1))
        to_date = parse_date(self.request.GET.get('to'), date.today())
        context['report'] = ReportService.rep_commission_report(from_date, to_date)
        context['from_date'] = from_date
        context['to_date'] = to_date
        return context

class CostCenterStatementView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'core.view_costcenter'
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

class AccountStatementView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'core.view_account'
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


class VATReportView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """
    تقرير ضريبة القيمة المضافة (VAT Report)
    يُظهر: ضريبة المبيعات (Output) + ضريبة المشتريات (Input) + صافي الضريبة
    """
    permission_required = 'core.view_account'
    template_name = 'reports/vat_report.html'

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

        context['report'] = ReportService.vat_report(from_date, to_date, cost_center_id=cc_id_int)
        context['from_date'] = from_date
        context['to_date'] = to_date
        return context


class WHTReportView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """
    تقرير ضريبة الخصم والتحصيل (Withholding Tax Report)
    يُظهر: WHT على المبيعات + WHT على المشتريات + صافي القيمة
    """
    permission_required = 'core.view_account'
    template_name = 'reports/wht_report.html'

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

        context['report'] = ReportService.wht_report(from_date, to_date, cost_center_id=cc_id_int)
        context['from_date'] = from_date
        context['to_date'] = to_date
        return context

# --- Inventory Reports ---

class InventoryValuationView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'inventory.view_item'
    template_name = 'reports/inventory_valuation.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.inventory.models import Warehouse
        warehouse_id = self.request.GET.get('warehouse')
        context['warehouses'] = Warehouse.objects.all()
        report_data = ReportService.inventory_valuation(warehouse_id)
        
        paginator = Paginator(report_data['items'], 50)
        page_number = self.request.GET.get('page')
        report_data['items'] = paginator.get_page(page_number)
        
        context['report'] = report_data
        if warehouse_id:
            context['selected_warehouse'] = int(warehouse_id)

        return context

class ReorderAlertView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'inventory.view_item'
    template_name = 'reports/reorder_alert.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        report_qs = ReportService.reorder_alert_report()
        
        paginator = Paginator(report_qs, 50)
        page_number = self.request.GET.get('page')
        context['report'] = paginator.get_page(page_number)
        
        return context


class ItemLedgerReportView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'inventory.view_item'
    template_name = 'reports/item_ledger.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.inventory.models import Item, Warehouse
        item_id = self.request.GET.get('item')
        warehouse_id = self.request.GET.get('warehouse')
        from_date = parse_date(self.request.GET.get('from'), date.today().replace(day=1))
        to_date = parse_date(self.request.GET.get('to'), date.today())

        context['items'] = Item.objects.filter(is_active=True).order_by('name')
        context['warehouses'] = Warehouse.objects.all()
        context['from_date'] = from_date
        context['to_date'] = to_date

        if item_id:
            report_data = ReportService.item_ledger_report(
                int(item_id), 
                int(warehouse_id) if warehouse_id else None,
                from_date,
                to_date
            )
            
            paginator = Paginator(report_data['movements'], 50)
            page_number = self.request.GET.get('page')
            report_data['movements'] = paginator.get_page(page_number)
            
            context['report'] = report_data
            context['selected_item'] = int(item_id)
            if warehouse_id:
                context['selected_warehouse'] = int(warehouse_id)

        
        return context

class WastageAdjustmentsView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'inventory.view_stockvoucher'
    template_name = 'reports/wastage_adjustments.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from_date = parse_date(self.request.GET.get('from'), date.today().replace(day=1))
        to_date = parse_date(self.request.GET.get('to'), date.today())
        report_qs = ReportService.wastage_adjustments_report(from_date, to_date)
        
        paginator = Paginator(report_qs, 50)
        page_number = self.request.GET.get('page')
        context['report'] = paginator.get_page(page_number)
        
        context['from_date'] = from_date
        context['to_date'] = to_date
        return context


class VanInventoryView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'sales.view_salesrepresentative'
    template_name = 'reports/van_inventory.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.sales.models import SalesRepresentative
        rep_id = self.request.GET.get('rep')
        context['reps'] = SalesRepresentative.objects.filter(is_active=True)
        
        if rep_id:
            try:
                report_data = ReportService.van_inventory_report(int(rep_id))
                
                paginator = Paginator(report_data['items'], 50)
                page_number = self.request.GET.get('page')
                report_data['items'] = paginator.get_page(page_number)
                
                context['report'] = report_data
                context['selected_rep'] = int(rep_id)
            except Exception as e:
                context['error'] = str(e)

        return context

class InventoryTurnoverView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'inventory.view_item'
    template_name = 'reports/inventory_turnover.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from_date = parse_date(self.request.GET.get('from'), date(date.today().year, 1, 1))
        to_date = parse_date(self.request.GET.get('to'), date.today())
        report_list = ReportService.inventory_turnover_report(from_date, to_date)
        
        paginator = Paginator(report_list, 50)
        page_number = self.request.GET.get('page')
        context['report'] = paginator.get_page(page_number)
        
        context['from_date'] = from_date
        context['to_date'] = to_date
        return context


