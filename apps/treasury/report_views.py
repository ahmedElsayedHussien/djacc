from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.core.mixins import PermRequiredMixin
from datetime import date
from .models import CashBox, BankAccount, BankReconciliation
from apps.reports.services import ReportService

class TreasuryReportDashboardView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'treasury/reports/dashboard_links.html'
    permission_required = 'treasury.view_cashbox'

class LiveLiquidityReportView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'treasury/reports/liquidity.html'
    permission_required = 'treasury.view_cashbox'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report'] = ReportService.live_liquidity_position()
        return context

class CashInTransitReportView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'treasury/reports/in_transit.html'
    permission_required = 'treasury.view_cashtransfer'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report'] = ReportService.cash_in_transit_report()
        return context

class InternalTransfersReportView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'treasury/reports/transfers_summary.html'
    permission_required = 'treasury.view_cashtransfer'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from_date = self.request.GET.get('from', date.today().replace(day=1).isoformat())
        to_date = self.request.GET.get('to', date.today().isoformat())
        
        try:
            from_date_obj = date.fromisoformat(from_date)
            to_date_obj = date.fromisoformat(to_date)
        except (ValueError, TypeError):
            from_date_obj = date.today().replace(day=1)
            to_date_obj = date.today()
        
        context['report'] = ReportService.internal_transfers_summary(from_date_obj, to_date_obj)
        context['from_date'] = from_date_obj
        context['to_date'] = to_date_obj
        return context

class BankReconciliationReportView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'treasury/reports/reconciliation_detail.html'
    permission_required = 'treasury.view_bankreconciliation'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        recon_id = self.request.GET.get('reconciliation')
        context['reconciliations'] = BankReconciliation.objects.all().order_by('-statement_date')
        
        if recon_id:
            try:
                recon_pk = int(recon_id)
                context['data'] = ReportService.bank_reconciliation_report(recon_pk)
                context['selected_recon'] = recon_pk
            except (ValueError, TypeError):
                pass
        return context

class BankChargesInterestReportView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'treasury/reports/charges_interest.html'
    permission_required = 'treasury.view_banktransaction'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from_date = self.request.GET.get('from', date.today().replace(day=1).isoformat())
        to_date = self.request.GET.get('to', date.today().isoformat())
        
        try:
            from_date_obj = date.fromisoformat(from_date)
            to_date_obj = date.fromisoformat(to_date)
        except (ValueError, TypeError):
            from_date_obj = date.today().replace(day=1)
            to_date_obj = date.today()
        
        context['report'] = ReportService.bank_charges_interest_report(from_date_obj, to_date_obj)
        context['from_date'] = from_date_obj
        context['to_date'] = to_date_obj
        return context
