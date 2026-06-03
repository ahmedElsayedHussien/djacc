from django.views.generic import ListView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import redirect
from apps.core.mixins import PermRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from ..models import TaxType
from ..forms import TaxTypeForm
from ..services import AuditService
from apps.sales.models import SalesInvoiceLine, SalesReturnLine
from apps.purchases.models import PurchaseInvoiceLine, PurchaseReturnLine
from apps.expenses.models import Expense

class TaxTypeListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = TaxType
    template_name = 'core/taxes/list.html'
    context_object_name = 'taxes'
    permission_required = 'core.view_taxtype'

class TaxTypeCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = TaxType
    form_class = TaxTypeForm
    template_name = 'core/taxes/form.html'
    success_url = reverse_lazy('core:taxtype-list')
    permission_required = 'core.add_taxtype'

    def form_valid(self, form):
        response = super().form_valid(form)
        AuditService.log(self.request.user, 'Create', form.instance,
                         f'إنشاء ضريبة "{form.instance.name}" - فئة {form.instance.category}')
        messages.success(self.request, f'تم إضافة الضريبة "{form.instance.name}" بنجاح')
        return response

class TaxTypeUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):
    model = TaxType
    form_class = TaxTypeForm
    template_name = 'core/taxes/form.html'
    success_url = reverse_lazy('core:taxtype-list')
    permission_required = 'core.change_taxtype'

    def dispatch(self, request, *args, **kwargs):
        self.kwargs = kwargs
        self.args = args
        obj = self.get_object()
        in_use = (
            SalesInvoiceLine.objects.filter(Q(tax_type=obj) | Q(tax_type2=obj)).exists() or
            SalesReturnLine.objects.filter(Q(tax_type=obj) | Q(tax_type2=obj)).exists() or
            PurchaseInvoiceLine.objects.filter(Q(tax_type=obj) | Q(tax_type2=obj)).exists() or
            PurchaseReturnLine.objects.filter(Q(tax_type=obj) | Q(tax_type2=obj)).exists() or
            Expense.objects.filter(Q(tax_type=obj) | Q(tax_type2=obj)).exists()
        )
        if in_use:
            messages.error(self.request,
                           f'لا يمكن تعديل الضريبة "{obj.name}" لأنها مستخدمة في فواتير سابقة. '
                           f'قم بإنشاء ضريبة جديدة بدلاً من ذلك.')
            return redirect('core:taxtype-list')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        AuditService.log(self.request.user, 'Update', form.instance,
                         f'تحديث ضريبة "{form.instance.name}"')
        messages.success(self.request, f'تم تحديث بيانات الضريبة "{form.instance.name}"')
        return response
