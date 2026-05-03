from django.views.generic import ListView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from ..models import TaxType
from ..forms import TaxTypeForm

class TaxTypeListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = TaxType
    template_name = 'core/taxes/list.html'
    context_object_name = 'taxes'
    permission_required = 'core.view_taxtype'

class TaxTypeCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = TaxType
    form_class = TaxTypeForm
    template_name = 'core/taxes/form.html'
    success_url = reverse_lazy('core:taxtype-list')
    permission_required = 'core.add_taxtype'

    def form_valid(self, form):
        messages.success(self.request, f'تم إضافة الضريبة "{form.instance.name}" بنجاح')
        return super().form_valid(form)

class TaxTypeUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = TaxType
    form_class = TaxTypeForm
    template_name = 'core/taxes/form.html'
    success_url = reverse_lazy('core:taxtype-list')
    permission_required = 'core.change_taxtype'

    def form_valid(self, form):
        messages.success(self.request, f'تم تحديث بيانات الضريبة "{form.instance.name}"')
        return super().form_valid(form)
