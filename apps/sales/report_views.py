from django.views.generic import TemplateView, ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.core.mixins import PermRequiredMixin
from django.db.models import Sum, Count, F, Q, ExpressionWrapper, DecimalField, Case, When
from django.db.models.functions import TruncMonth, TruncDay, Coalesce
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import timedelta, date
from decimal import Decimal

from .models import SalesInvoice, SalesInvoiceLine, SalesReturn, SalesRepresentative, Customer, SalesTarget, ReceiptAllocation
from apps.inventory.models import Item
from apps.reports.services import ReportService


class SalesDashboardView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'sales/reports/dashboard.html'
    permission_required = 'sales.view_salesinvoice'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        month_start = today.replace(day=1)
        year_start = today.replace(month=1, day=1)
        
        # Summary Stats
        context['total_sales_month'] = SalesInvoice.objects.filter(
            status=SalesInvoice.Status.POSTED,
            date__gte=month_start
        ).aggregate(total=Coalesce(Sum('total'), Decimal('0')))['total']
        
        context['total_invoices_month'] = SalesInvoice.objects.filter(
            status=SalesInvoice.Status.POSTED,
            date__gte=month_start
        ).count()

        context['total_sales'] = SalesInvoice.objects.filter(
            status=SalesInvoice.Status.POSTED
        ).aggregate(total=Coalesce(Sum('total'), Decimal('0')))['total']
        
        context['total_customers'] = Customer.objects.count()
        
        # --- Top Customers ---
        # Month
        context['top_customers_month'] = Customer.objects.annotate(
            total_sales=Coalesce(Sum('salesinvoice__total', filter=Q(salesinvoice__status=SalesInvoice.Status.POSTED, salesinvoice__date__gte=month_start)), Decimal('0'))
        ).order_by('-total_sales')[:5]
        # Year
        context['top_customers_year'] = Customer.objects.annotate(
            total_sales=Coalesce(Sum('salesinvoice__total', filter=Q(salesinvoice__status=SalesInvoice.Status.POSTED, salesinvoice__date__gte=year_start)), Decimal('0'))
        ).order_by('-total_sales')[:5]
        
        # --- Top Reps ---
        # Month
        context['top_reps_month'] = SalesRepresentative.objects.annotate(
            total_sales=Coalesce(Sum('salesinvoice__total', filter=Q(salesinvoice__status=SalesInvoice.Status.POSTED, salesinvoice__date__gte=month_start)), Decimal('0'))
        ).order_by('-total_sales')[:5]
        # Year
        context['top_reps_year'] = SalesRepresentative.objects.annotate(
            total_sales=Coalesce(Sum('salesinvoice__total', filter=Q(salesinvoice__status=SalesInvoice.Status.POSTED, salesinvoice__date__gte=year_start)), Decimal('0'))
        ).order_by('-total_sales')[:5]
        
        # Monthly Sales Chart Data
        last_6_months = today - timedelta(days=180)
        chart_data = SalesInvoice.objects.filter(
            status=SalesInvoice.Status.POSTED,
            date__gte=last_6_months
        ).annotate(month=TruncMonth('date')).values('month').annotate(
            total=Sum('total')
        ).order_by('month')
        
        context['chart_labels'] = [d['month'].strftime('%Y-%m') for d in chart_data]
        context['chart_values'] = [float(d['total']) for d in chart_data]
        
        return context

class SalesByItemReportView(LoginRequiredMixin, PermRequiredMixin, ListView):
    template_name = 'sales/reports/by_item.html'
    context_object_name = 'report_data'
    permission_required = 'sales.view_salesinvoice'
    paginate_by = 50

    def get_queryset(self):
        date_from_str = self.request.GET.get('date_from')
        date_to_str = self.request.GET.get('date_to')
        
        qs = SalesInvoiceLine.objects.filter(invoice__status=SalesInvoice.Status.POSTED)
        
        if date_from_str:
            qs = qs.filter(invoice__date__gte=date.fromisoformat(date_from_str))
        if date_to_str:
            qs = qs.filter(invoice__date__lte=date.fromisoformat(date_to_str))
            
        return qs.values('item__code', 'item__name', 'item__base_unit__name').annotate(
            total_qty=Sum('base_quantity'),
            total_amount=Sum('total'),
            avg_price=Case(
                When(total_qty__gt=0, then=ExpressionWrapper(Sum('total') / Sum('base_quantity'), output_field=DecimalField())),
                default=Decimal('0'),
                output_field=DecimalField()
            )
        ).order_by('-total_amount')

class SalesByRepReportView(LoginRequiredMixin, PermRequiredMixin, ListView):
    template_name = 'sales/reports/by_rep.html'
    context_object_name = 'report_data'
    permission_required = 'sales.view_salesinvoice'
    paginate_by = 50

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        context['default_date_from'] = self.request.GET.get('date_from', today.replace(day=1).isoformat())
        context['default_date_to'] = self.request.GET.get('date_to', today.isoformat())
        return context

    def get_queryset(self):
        today = timezone.now().date()
        date_from_str = self.request.GET.get('date_from', today.replace(day=1).isoformat())
        date_to_str = self.request.GET.get('date_to', today.isoformat())
        
        date_from = date.fromisoformat(date_from_str)
        date_to   = date.fromisoformat(date_to_str)
        
        reps = SalesRepresentative.objects.filter(is_active=True)
        
        report_data = []
        for rep in reps:
            actual = SalesInvoice.objects.filter(
                sales_rep=rep,
                status=SalesInvoice.Status.POSTED,
                date__range=[date_from, date_to]
            ).aggregate(total=Coalesce(Sum('total'), Decimal('0')))['total']
            
            # Target (find target overlapping with period)
            target = SalesTarget.objects.filter(
                sales_rep=rep,
                start_date__lte=date_to,
                end_date__gte=date_from
            ).aggregate(total=Coalesce(Sum('target_amount'), Decimal('0')))['total']
            
            report_data.append({
                'rep': rep,
                'actual': actual,
                'target': target,
                'achievement': (actual / target * 100) if target > 0 else 0
            })
            
        return sorted(report_data, key=lambda x: x['actual'], reverse=True)

class SalesByCustomerReportView(LoginRequiredMixin, PermRequiredMixin, ListView):
    template_name = 'sales/reports/by_customer.html'
    context_object_name = 'report_data'
    permission_required = 'sales.view_salesinvoice'
    paginate_by = 50

    def get_queryset(self):
        date_from_str = self.request.GET.get('date_from')
        date_to_str = self.request.GET.get('date_to')
        
        qs = SalesInvoice.objects.filter(status=SalesInvoice.Status.POSTED)
        
        if date_from_str:
            qs = qs.filter(date__gte=date.fromisoformat(date_from_str))
        if date_to_str:
            qs = qs.filter(date__lte=date.fromisoformat(date_to_str))
            
        return qs.values('customer__code', 'customer__name').annotate(
            invoice_count=Count('id'),
            total_amount=Sum('total')
        ).order_by('-total_amount')

class SalesReturnReportView(LoginRequiredMixin, PermRequiredMixin, ListView):
    template_name = 'sales/reports/returns.html'
    context_object_name = 'report_data'
    permission_required = 'sales.view_salesreturn'
    paginate_by = 50

    def get_queryset(self):
        date_from_str = self.request.GET.get('date_from')
        date_to_str = self.request.GET.get('date_to')
        
        qs = SalesReturn.objects.filter(status=SalesReturn.Status.POSTED)
        
        if date_from_str:
            qs = qs.filter(date__gte=date.fromisoformat(date_from_str))
        if date_to_str:
            qs = qs.filter(date__lte=date.fromisoformat(date_to_str))
            
        return qs.select_related('customer', 'sales_rep').order_by('-date')

class SalesTargetComparisonView(LoginRequiredMixin, PermRequiredMixin, ListView):
    template_name = 'sales/reports/target_comparison.html'
    context_object_name = 'targets'
    permission_required = 'sales.view_salesinvoice'
    paginate_by = 20

    def get_queryset(self):
        return SalesTarget.objects.select_related('sales_rep').all()

class DetailedSalesReportView(LoginRequiredMixin, PermRequiredMixin, ListView):
    template_name = 'sales/reports/detailed_sales.html'
    context_object_name = 'report_data'
    permission_required = 'sales.view_salesinvoice'
    paginate_by = 100

    def get_queryset(self):
        date_from_str = self.request.GET.get('date_from')
        date_to_str = self.request.GET.get('date_to')
        customer_id = self.request.GET.get('customer')
        rep_id = self.request.GET.get('rep')
        
        qs = SalesInvoiceLine.objects.filter(invoice__status=SalesInvoice.Status.POSTED).select_related(
            'invoice', 'invoice__customer', 'invoice__sales_rep', 'item'
        ).order_by('-invoice__date', '-invoice__number')
        
        if date_from_str:
            qs = qs.filter(invoice__date__gte=date.fromisoformat(date_from_str))
        if date_to_str:
            qs = qs.filter(invoice__date__lte=date.fromisoformat(date_to_str))
        if customer_id:
            qs = qs.filter(invoice__customer_id=customer_id)
        if rep_id:
            qs = qs.filter(invoice__sales_rep_id=rep_id)
            
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['customers'] = Customer.objects.all()
        context['reps'] = SalesRepresentative.objects.filter(is_active=True)
        return context

class SalesAgingReportView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'sales/reports/aging.html'
    permission_required = 'sales.view_salesinvoice'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        customer_id = self.request.GET.get('customer')
        
        # Base Query: Posted invoices with remaining balance
        invoices = SalesInvoice.objects.filter(
            status=SalesInvoice.Status.POSTED
        ).annotate(
            allocated_amount=Coalesce(Sum('receiptallocation__amount'), Decimal('0'))
        ).annotate(
            remaining_balance=ExpressionWrapper(
                F('total') - F('allocated_amount'),
                output_field=DecimalField()
            )
        ).filter(remaining_balance__gt=0).select_related('customer', 'sales_rep')

        if customer_id:
            invoices = invoices.filter(customer_id=customer_id)

        # Categorize by age
        aging_data = []
        for inv in invoices:
            due_date = inv.due_date if inv.due_date else inv.date
            age = (today - due_date).days
            bucket = '90+'
            if age <= 30: bucket = '0-30'
            elif age <= 60: bucket = '31-60'
            elif age <= 90: bucket = '61-90'
            
            aging_data.append({
                'invoice': inv,
                'customer': inv.customer,
                'age': age,
                'bucket': bucket,
                'total': inv.total,
                'remaining': inv.remaining_balance
            })

        context['report_data'] = aging_data
        context['customers'] = Customer.objects.all()
        context['selected_customer'] = int(customer_id) if customer_id else None
        context['today'] = today
        
        # Summary by bucket
        summary = {
            'age_0_30': Decimal('0'),
            'age_31_60': Decimal('0'),
            'age_61_90': Decimal('0'),
            'age_90_plus': Decimal('0'),
            'total': Decimal('0')
        }
        for item in aging_data:
            bucket_key = item['bucket'].replace('-', '_').replace('+', '_plus')
            if not bucket_key.startswith('age_'):
                bucket_key = f"age_{bucket_key}"
            summary[bucket_key] += item['remaining']
            summary['total'] += item['remaining']
            
        context['summary'] = summary
        return context
class SalesReportDashboardView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'sales/reports/dashboard_links.html'
    permission_required = 'sales.view_salesinvoice'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context

class NetSalesProfitabilityReportView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'sales/reports/net_sales_profitability.html'
    permission_required = 'sales.view_salesinvoice'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from_date = self.request.GET.get('from', date.today().replace(day=1).isoformat())
        to_date = self.request.GET.get('to', date.today().isoformat())
        
        from_date_obj = date.fromisoformat(from_date)
        to_date_obj = date.fromisoformat(to_date)
        
        
        context['report'] = ReportService.net_sales_profitability_report(from_date_obj, to_date_obj)
        context['from_date'] = from_date_obj
        context['to_date'] = to_date_obj
        return context

class ProductProfitabilityReportView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'sales/reports/product_profitability.html'
    permission_required = 'sales.view_salesinvoice'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from_date = self.request.GET.get('from', date.today().replace(day=1).isoformat())
        to_date = self.request.GET.get('to', date.today().isoformat())
        
        from_date_obj = date.fromisoformat(from_date)
        to_date_obj = date.fromisoformat(to_date)
        
        
        report_data = ReportService.product_profitability_report(from_date_obj, to_date_obj)
        
        paginator = Paginator(report_data, 50)
        page_number = self.request.GET.get('page')
        context['report'] = paginator.get_page(page_number)
        
        context['from_date'] = from_date_obj
        context['to_date'] = to_date_obj
        return context

class SalesBySectorReportView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'sales/reports/by_sector.html'
    permission_required = 'sales.view_salesinvoice'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from_date = self.request.GET.get('from', date.today().replace(day=1).isoformat())
        to_date = self.request.GET.get('to', date.today().isoformat())
        
        from_date_obj = date.fromisoformat(from_date)
        to_date_obj = date.fromisoformat(to_date)
        
        
        report_data = ReportService.sales_by_sector_report(from_date_obj, to_date_obj)
        
        paginator = Paginator(report_data, 50)
        page_number = self.request.GET.get('page')
        context['report'] = paginator.get_page(page_number)
        
        context['from_date'] = from_date_obj
        context['to_date'] = to_date_obj
        return context

class RepPerformanceEnhancedReportView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'sales/reports/rep_performance_enhanced.html'
    permission_required = 'sales.view_salesinvoice'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from_date = self.request.GET.get('from', date.today().replace(day=1).isoformat())
        to_date = self.request.GET.get('to', date.today().isoformat())
        
        from_date_obj = date.fromisoformat(from_date)
        to_date_obj = date.fromisoformat(to_date)
        
        
        report_data = ReportService.rep_performance_report_enhanced(from_date_obj, to_date_obj)
        
        paginator = Paginator(report_data, 50)
        page_number = self.request.GET.get('page')
        context['report'] = paginator.get_page(page_number)
        
        context['from_date'] = from_date_obj
        context['to_date'] = to_date_obj
        return context

class CustomerAgingSummaryReportView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'sales/reports/aging_summary.html'
    permission_required = 'sales.view_salesinvoice'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customer_id = self.request.GET.get('customer')
        
        
        report_data = ReportService.customer_aging_summary_report(customer_id)
        
        paginator = Paginator(report_data, 50)
        page_number = self.request.GET.get('page')
        context['report'] = paginator.get_page(page_number)
        
        context['customers'] = Customer.objects.all()
        if customer_id:
            context['selected_customer'] = int(customer_id)
            
        return context

class QuotationAnalysisReportView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'sales/reports/quotation_analysis.html'
    permission_required = 'sales.view_quotation'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from_date = self.request.GET.get('from', date.today().replace(day=1).isoformat())
        to_date = self.request.GET.get('to', date.today().isoformat())
        
        from_date_obj = date.fromisoformat(from_date)
        to_date_obj = date.fromisoformat(to_date)
        
        
        context['report'] = ReportService.quotation_analysis_report(from_date_obj, to_date_obj)
        context['from_date'] = from_date_obj
        context['to_date'] = to_date_obj
        return context

