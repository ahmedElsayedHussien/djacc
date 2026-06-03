import logging
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.core.mixins import PermRequiredMixin
from datetime import date
from .models import Supplier
from apps.reports.services import ReportService
from django.core.paginator import Paginator

logger = logging.getLogger(__name__)

class PurchaseReportDashboardView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'purchases/reports/dashboard_links.html'
    permission_required = 'purchases.view_purchaseinvoice'

class PurchaseSummaryReportView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'purchases/reports/summary.html'
    permission_required = 'purchases.view_purchaseinvoice'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from_date = self.request.GET.get('from', date.today().replace(day=1).isoformat())
        to_date = self.request.GET.get('to', date.today().isoformat())
        
        from_date_obj = date.fromisoformat(from_date)
        to_date_obj = date.fromisoformat(to_date)
        
        context['report'] = ReportService.purchases_summary_report(from_date_obj, to_date_obj)
        context['from_date'] = from_date_obj
        context['to_date'] = to_date_obj
        return context

class ItemPurchaseCostReportView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'purchases/reports/item_cost.html'
    permission_required = 'purchases.view_purchaseinvoice'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from_date = self.request.GET.get('from', date.today().replace(day=1).isoformat())
        to_date = self.request.GET.get('to', date.today().isoformat())
        
        from_date_obj = date.fromisoformat(from_date)
        to_date_obj = date.fromisoformat(to_date)
        
        report_data = ReportService.item_purchase_cost_report(from_date_obj, to_date_obj)
        paginator = Paginator(report_data, 50)
        page_number = self.request.GET.get('page')
        context['report'] = paginator.get_page(page_number)
        
        context['from_date'] = from_date_obj
        context['to_date'] = to_date_obj
        return context

class SupplierBalancesReportView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'purchases/reports/supplier_balances.html'
    permission_required = 'purchases.view_supplier'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from_date = self.request.GET.get('from', date.today().replace(day=1).isoformat())
        to_date = self.request.GET.get('to', date.today().isoformat())
        
        from_date_obj = date.fromisoformat(from_date)
        to_date_obj = date.fromisoformat(to_date)
        
        report_data = ReportService.supplier_balances_report(from_date_obj, to_date_obj)
        paginator = Paginator(report_data, 50)
        page_number = self.request.GET.get('page')
        context['report'] = paginator.get_page(page_number)
        
        context['from_date'] = from_date_obj
        context['to_date'] = to_date_obj
        return context

class SupplierAgingReportView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'purchases/reports/aging.html'
    permission_required = 'purchases.view_supplier'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        supplier_id = self.request.GET.get('supplier')
        
        report_data = ReportService.supplier_aging_report(supplier_id)
        paginator = Paginator(report_data, 50)
        page_number = self.request.GET.get('page')
        context['report'] = paginator.get_page(page_number)
        
        context['suppliers'] = Supplier.objects.all().select_related('account')
        if supplier_id:
            context['selected_supplier'] = int(supplier_id)
        return context

class OpenPurchaseOrdersReportView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'purchases/reports/open_orders.html'
    permission_required = 'purchases.view_purchaseorder'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report'] = ReportService.open_purchase_orders_report()
        return context

class PurchaseReturnAnalysisReportView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'purchases/reports/returns_analysis.html'
    permission_required = 'purchases.view_purchasereturn'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from_date = self.request.GET.get('from', date.today().replace(day=1).isoformat())
        to_date = self.request.GET.get('to', date.today().isoformat())
        
        from_date_obj = date.fromisoformat(from_date)
        to_date_obj = date.fromisoformat(to_date)
        
        context['report'] = ReportService.purchase_returns_analysis_report(from_date_obj, to_date_obj)
        context['from_date'] = from_date_obj
        context['to_date'] = to_date_obj
        return context
