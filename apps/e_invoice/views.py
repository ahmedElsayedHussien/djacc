import json

from django.views import View
from apps.sales.models import SalesInvoice
from django.views.generic import ListView, UpdateView, CreateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.db import transaction
from .models import EInvoiceLog, CompanySettings, EInvoiceConfig, Certificate
from .forms import CompanySettingsForm, EInvoiceConfigForm, CertificateForm
from .services import EInvoiceService


class SuperuserRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser


class BulkSubmitEInvoiceView(LoginRequiredMixin, SuperuserRequiredMixin, View):
    def post(self, request):
        invoice_ids = request.POST.getlist('invoice_ids')
        
        if not invoice_ids:
            messages.warning(request, "لم يتم اختيار أي فواتير للإرسال.")
            return redirect('sales:invoice-list')
            
        success_count = 0
        fail_count = 0
        
        for inv_id in invoice_ids:
            try:
                inv_pk = int(inv_id)
            except (ValueError, TypeError):
                fail_count += 1
                continue
            with transaction.atomic():
                invoice = get_object_or_404(
                    SalesInvoice.objects.select_for_update(), pk=inv_pk
                )
                if invoice.status == 'posted' and invoice.einvoice_status not in ['valid', 'submitted']:
                    result = EInvoiceService.submit_sales_invoice(invoice, request.user)
                else:
                    result = {'success': False, 'message': 'الفاتورة غير قابلة للإرسال'}
            if result.get('success'):
                success_count += 1
            else:
                fail_count += 1
                    
        if success_count > 0:
            messages.success(request, f"تم إرسال {success_count} فاتورة بنجاح.")
        if fail_count > 0:
            messages.error(request, f"فشل إرسال {fail_count} فاتورة. يرجى مراجعة سجل الأخطاء.")
            
        return redirect('sales:invoice-list')

class EInvoiceLogDetailView(LoginRequiredMixin, SuperuserRequiredMixin, DetailView):
    model = EInvoiceLog
    template_name = 'e_invoice/log_detail.html'
    context_object_name = 'log'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if isinstance(self.object.raw_response, str):
            try:
                context['response_json'] = json.loads(self.object.raw_response)
            except (ValueError, TypeError, json.JSONDecodeError):
                context['response_json'] = self.object.raw_response
        else:
            context['response_json'] = self.object.raw_response
        return context

class EInvoiceDashboardView(LoginRequiredMixin, SuperuserRequiredMixin, ListView):
    model = EInvoiceLog
    template_name = 'e_invoice/dashboard.html'
    context_object_name = 'logs'
    paginate_by = 20

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['total_count'] = EInvoiceLog.objects.count()
        ctx['valid_count'] = EInvoiceLog.objects.filter(status='valid').count()
        ctx['invalid_count'] = EInvoiceLog.objects.filter(status='invalid').count()
        ctx['config'] = EInvoiceConfig.objects.first()
        ctx['company'] = CompanySettings.objects.first()
        return ctx

class CompanySettingsUpdateView(LoginRequiredMixin, SuperuserRequiredMixin, UpdateView):
    model = CompanySettings
    form_class = CompanySettingsForm
    template_name = 'e_invoice/settings_form.html'
    success_url = reverse_lazy('e_invoice:dashboard')
    
    def get_object(self, queryset=None):
        obj, created = CompanySettings.objects.get_or_create(
            pk=CompanySettings.objects.first().pk if CompanySettings.objects.exists() else 1,
            defaults={
                'company_name_ar': 'شركتي',
                'company_name_en': 'My Company',
                'tax_id': '000000000',
                'commercial_register': '000',
                'VAT_number': '000000000',
                'address': '—',
                'governorate': '—',
                'region_city': '—',
                'phone': '—',
                'email': 'company@example.com',
            }
        )
        return obj

class EInvoiceConfigUpdateView(LoginRequiredMixin, SuperuserRequiredMixin, UpdateView):
    model = EInvoiceConfig
    form_class = EInvoiceConfigForm
    template_name = 'e_invoice/settings_form.html'
    success_url = reverse_lazy('e_invoice:dashboard')
    
    def get_object(self, queryset=None):
        company, _ = CompanySettings.objects.get_or_create(
            pk=CompanySettings.objects.first().pk if CompanySettings.objects.exists() else 1,
            defaults={
                'company_name_ar': 'شركتي',
                'company_name_en': 'My Company',
                'tax_id': '000000000',
                'commercial_register': '000',
                'VAT_number': '000000000',
                'address': '—',
                'governorate': '—',
                'region_city': '—',
                'phone': '—',
                'email': 'company@example.com',
            }
        )
        obj, created = EInvoiceConfig.objects.get_or_create(company=company)
        return obj

class CertificateListView(LoginRequiredMixin, SuperuserRequiredMixin, ListView):
    model = Certificate
    template_name = 'e_invoice/certificate_list.html'
    context_object_name = 'certificates'
    paginate_by = 25

class CertificateCreateView(LoginRequiredMixin, SuperuserRequiredMixin, CreateView):
    model = Certificate
    form_class = CertificateForm
    template_name = 'e_invoice/settings_form.html'
    success_url = reverse_lazy('e_invoice:certificate-list')
    
    def form_valid(self, form):
        company, _ = CompanySettings.objects.get_or_create(
            pk=CompanySettings.objects.first().pk if CompanySettings.objects.exists() else 1,
            defaults={
                'company_name_ar': 'شركتي',
                'company_name_en': 'My Company',
                'tax_id': '000000000',
                'commercial_register': '000',
                'VAT_number': '000000000',
                'address': '—',
                'governorate': '—',
                'region_city': '—',
                'phone': '—',
                'email': 'company@example.com',
            }
        )
        form.instance.company = company
        return super().form_valid(form)

class CertificateUpdateView(LoginRequiredMixin, SuperuserRequiredMixin, UpdateView):
    model = Certificate
    form_class = CertificateForm
    template_name = 'e_invoice/settings_form.html'
    success_url = reverse_lazy('e_invoice:certificate-list')
