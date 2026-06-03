from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from ..models import FiscalYear
from ..forms import FiscalYearForm
from ..services import JournalService

class FiscalYearListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = FiscalYear
    template_name = 'core/fiscal_years/list.html'
    context_object_name = 'fiscal_years'
    permission_required = 'core.view_fiscalyear'
    ordering = ['-start_date']

class FiscalYearCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = FiscalYear
    form_class = FiscalYearForm
    template_name = 'core/fiscal_years/form.html'
    success_url = reverse_lazy('core:fiscalyear-list')
    permission_required = 'core.add_fiscalyear'

    def form_valid(self, form):
        messages.success(self.request, f'تم إنشاء السنة المالية {form.instance.name} بنجاح')
        return super().form_valid(form)

class FiscalYearCloseView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'core.change_fiscalyear'
    
    def post(self, request, pk):
        fiscal_year = get_object_or_404(FiscalYear, pk=pk)
        try:
            JournalService.close_fiscal_year(fiscal_year, request.user)
            messages.success(request, f'تم إقفال السنة المالية {fiscal_year.name} بنجاح وإنشاء قيد الإقفال.')
        except Exception as e:
            messages.error(request, f'فشل الإقفال: {e}')
        return redirect('core:fiscalyear-list')

class FiscalYearPostOpeningView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_superuser
    
    def post(self, request, pk):
        fiscal_year = get_object_or_404(FiscalYear, pk=pk)
        try:
            entry = JournalService.post_opening_balances(fiscal_year, request.user)
            if entry:
                messages.success(request, f'تم إنشاء القيد الافتتاحي بنجاح برقم {entry.number}')
            else:
                messages.warning(request, 'لم يتم العثور على أرصدة افتتاحية للحسابات (Leaf Accounts)')
        except Exception as e:
            messages.error(request, f'فشل إنشاء القيد الافتتاحي: {e}')
        return redirect('core:fiscalyear-list')
