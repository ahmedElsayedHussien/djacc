from django.views import View
from django.views.generic import ListView, UpdateView, CreateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from .models import EInvoiceLog, CompanySettings, EInvoiceConfig, Certificate
from .forms import CompanySettingsForm, EInvoiceConfigForm, CertificateForm
from .services import EInvoiceService

class BulkSubmitEInvoiceView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_superuser

    def post(self, request):
        from apps.sales.models import SalesInvoice
        invoice_ids = request.POST.getlist('invoice_ids')
        
        if not invoice_ids:
            messages.warning(request, "لم يتم اختيار أي فواتير للإرسال.")
            return redirect('sales:invoice-list')
            
        success_count = 0
        fail_count = 0
        
        for inv_id in invoice_ids:
            invoice = get_object_or_404(SalesInvoice, pk=inv_id)
            # Only submit if posted and not already valid or submitted
            if invoice.status == 'posted' and invoice.einvoice_status not in ['valid', 'submitted']:
                result = EInvoiceService.submit_sales_invoice(invoice, request.user)
                if result.get('success'):
                    success_count += 1
                else:
                    fail_count += 1
                    
        if success_count > 0:
            messages.success(request, f"تم إرسال {success_count} فاتورة بنجاح.")
        if fail_count > 0:
            messages.error(request, f"فشل إرسال {fail_count} فاتورة. يرجى مراجعة سجل الأخطاء.")
            
        return redirect('sales:invoice-list')

class EInvoiceLogDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = EInvoiceLog
    template_name = 'e_invoice/log_detail.html'
    context_object_name = 'log'

    def test_func(self):
        return self.request.user.is_superuser

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Try to parse raw_response if it's a string
        import json
        if isinstance(self.object.raw_response, str):
            try:
                context['response_json'] = json.loads(self.object.raw_response)
            except:
                context['response_json'] = self.object.raw_response
        else:
            context['response_json'] = self.object.raw_response
        return context

class EInvoiceDashboardView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = EInvoiceLog
    template_name = 'e_invoice/dashboard.html'
    context_object_name = 'logs'
    paginate_by = 20

    def test_func(self):
        return self.request.user.is_superuser

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['total_count'] = EInvoiceLog.objects.count()
        ctx['valid_count'] = EInvoiceLog.objects.filter(status='valid').count()
        ctx['invalid_count'] = EInvoiceLog.objects.filter(status='invalid').count()
        ctx['config'] = EInvoiceConfig.objects.first()
        ctx['company'] = CompanySettings.objects.first()
        return ctx

class CompanySettingsUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = CompanySettings
    form_class = CompanySettingsForm
    template_name = 'e_invoice/settings_form.html'
    success_url = reverse_lazy('e_invoice:dashboard')
    
    def test_func(self):
        return self.request.user.is_superuser
    
    def get_object(self, queryset=None):
        obj, created = CompanySettings.objects.get_or_create(id=1)
        return obj

class EInvoiceConfigUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = EInvoiceConfig
    form_class = EInvoiceConfigForm
    template_name = 'e_invoice/settings_form.html'
    success_url = reverse_lazy('e_invoice:dashboard')
    
    def test_func(self):
        return self.request.user.is_superuser
    
    def get_object(self, queryset=None):
        company, _ = CompanySettings.objects.get_or_create(id=1)
        obj, created = EInvoiceConfig.objects.get_or_create(company=company)
        return obj

class CertificateListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Certificate
    template_name = 'e_invoice/certificate_list.html'
    context_object_name = 'certificates'
    
    def test_func(self):
        return self.request.user.is_superuser

class CertificateCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Certificate
    form_class = CertificateForm
    template_name = 'e_invoice/settings_form.html'
    success_url = reverse_lazy('e_invoice:certificate-list')
    
    def test_func(self):
        return self.request.user.is_superuser
    
    def form_valid(self, form):
        company, _ = CompanySettings.objects.get_or_create(id=1)
        form.instance.company = company
        return super().form_valid(form)

class CertificateUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Certificate
    form_class = CertificateForm
    template_name = 'e_invoice/settings_form.html'
    success_url = reverse_lazy('e_invoice:certificate-list')
    
    def test_func(self):
        return self.request.user.is_superuser
