from django.views.generic import ListView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.core.mixins import PermRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import redirect
from django.views import View
from ..models import Account, AccountType, CostCenter, FiscalYear
from ..forms import AccountForm, CostCenterForm
from ..services import AccountService, AuditService
from ..utils import get_account_balance, clear_balance_cache

class AccountInitializeView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'core.add_account'
    
    def post(self, request, *args, **kwargs):
        count = AccountService.initialize_default_chart()
        # Also run sub-accounts and cost centers
        sub_count = AccountService.setup_common_sub_accounts()
        cc_count = AccountService.setup_default_cost_centers()
        messages.success(request, f'تم إنشاء/تحديث {count + sub_count} حساب و {cc_count} مركز تكلفة بنجاح.')
        return redirect('core:account-list')

class AccountListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = Account
    template_name = 'core/accounts/list.html'
    context_object_name = 'accounts'
    permission_required = 'core.view_account'
    paginate_by = 50

    def get_queryset(self):
        qs = Account.objects.select_related('parent').order_by('code')
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(name__icontains=q) | qs.filter(code__icontains=q)
        acc_type = self.request.GET.get('type')
        if acc_type:
            qs = qs.filter(account_type=acc_type)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['account_types'] = AccountType.choices

        clear_balance_cache()

        for acc in ctx['accounts']:
            acc.current_balance = get_account_balance(acc)
        
        ctx['current_fiscal_year'] = FiscalYear.objects.filter(is_closed=False).order_by('start_date').first()
                
        return ctx

class AccountCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = Account
    form_class = AccountForm
    template_name = 'core/accounts/form.html'
    success_url = reverse_lazy('core:account-list')
    permission_required = 'core.add_account'

    def form_valid(self, form):
        response = super().form_valid(form)
        AuditService.log(self.request.user, 'Create', form.instance,
                         f'إنشاء حساب "{form.instance.code} - {form.instance.name}"')
        messages.success(self.request, f'تم إنشاء الحساب {form.instance.name} بنجاح')
        return response

class AccountUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):
    model = Account
    form_class = AccountForm
    template_name = 'core/accounts/form.html'
    success_url = reverse_lazy('core:account-list')
    permission_required = 'core.change_account'

    def form_valid(self, form):
        response = super().form_valid(form)
        AuditService.log(self.request.user, 'Update', form.instance,
                         f'تحديث حساب "{form.instance.code} - {form.instance.name}"')
        messages.success(self.request, 'تم تحديث الحساب بنجاح')
        return response

class CostCenterListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = CostCenter
    template_name = 'core/cost_centers/list.html'
    context_object_name = 'cost_centers'
    permission_required = 'core.view_costcenter'
    paginate_by = 50

    def get_queryset(self):
        return CostCenter.objects.select_related('parent').order_by('code')

class CostCenterCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = CostCenter
    form_class = CostCenterForm
    template_name = 'core/cost_centers/form.html'
    success_url = reverse_lazy('core:costcenter-list')
    permission_required = 'core.add_costcenter'

    def form_valid(self, form):
        response = super().form_valid(form)
        AuditService.log(self.request.user, 'Create', form.instance,
                         f'إنشاء مركز تكلفة "{form.instance.code} - {form.instance.name}"')
        messages.success(self.request, f'تم إنشاء مركز التكلفة {form.instance.name} بنجاح')
        return response

class CostCenterUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):
    model = CostCenter
    form_class = CostCenterForm
    template_name = 'core/cost_centers/form.html'
    success_url = reverse_lazy('core:costcenter-list')
    permission_required = 'core.change_costcenter'

    def form_valid(self, form):
        response = super().form_valid(form)
        AuditService.log(self.request.user, 'Update', form.instance,
                         f'تحديث مركز تكلفة "{form.instance.code} - {form.instance.name}"')
        messages.success(self.request, f'تم تعديل مركز التكلفة {form.instance.name} بنجاح')
        return response
