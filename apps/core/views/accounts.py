from django.views.generic import ListView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from ..models import Account, CostCenter
from ..forms import AccountForm, CostCenterForm

class AccountListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Account
    template_name = 'core/accounts/list.html'
    context_object_name = 'accounts'
    permission_required = 'core.view_account'

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
        from ..models import AccountType, JournalLine
        from django.db.models import Sum, Q
        from decimal import Decimal
        ctx = super().get_context_data(**kwargs)
        ctx['account_types'] = AccountType.choices
        
        # Calculate current balances for all accounts in the current view
        # We'll use a dictionary for fast lookup in the template
        accounts = ctx['accounts']
        account_ids = [acc.id for acc in accounts]
        
        movements = JournalLine.objects.filter(
            account_id__in=account_ids,
            entry__is_posted=True
        ).values('account_id').annotate(
            total_debit=Sum('debit'),
            total_credit=Sum('credit')
        )
        
        movement_map = {m['account_id']: m for m in movements}
        
        # Identify accounts that already have an opening journal entry
        from ..models import JournalEntry
        accounts_with_opening = set(JournalLine.objects.filter(
            account_id__in=account_ids,
            entry__entry_type=JournalEntry.EntryType.OPENING,
            entry__is_posted=True
        ).values_list('account_id', flat=True))
        
        for acc in accounts:
            m = movement_map.get(acc.id, {'total_debit': Decimal('0'), 'total_credit': Decimal('0')})
            debit = m['total_debit'] or Decimal('0')
            credit = m['total_credit'] or Decimal('0')
            
            # Add initial balance only if no opening entry exists
            if acc.id not in accounts_with_opening:
                if acc.initial_balance_type == 'debit':
                    debit += acc.initial_balance
                else:
                    credit += acc.initial_balance
            
            if acc.account_type in ['asset', 'expense']:
                acc.current_balance = debit - credit
            else:
                acc.current_balance = credit - debit
                
        return ctx

class AccountCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Account
    form_class = AccountForm
    template_name = 'core/accounts/form.html'
    success_url = reverse_lazy('core:account-list')
    permission_required = 'core.add_account'

    def form_valid(self, form):
        messages.success(self.request, f'تم إنشاء الحساب {form.instance.name} بنجاح')
        return super().form_valid(form)

class AccountUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Account
    form_class = AccountForm
    template_name = 'core/accounts/form.html'
    success_url = reverse_lazy('core:account-list')
    permission_required = 'core.change_account'

    def form_valid(self, form):
        messages.success(self.request, 'تم تحديث الحساب بنجاح')
        return super().form_valid(form)

class CostCenterListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = CostCenter
    template_name = 'core/cost_centers/list.html'
    context_object_name = 'cost_centers'
    permission_required = 'core.view_costcenter'

    def get_queryset(self):
        return CostCenter.objects.select_related('parent').order_by('code')

class CostCenterCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = CostCenter
    form_class = CostCenterForm
    template_name = 'core/cost_centers/form.html'
    success_url = reverse_lazy('core:costcenter-list')
    permission_required = 'core.add_costcenter'

    def form_valid(self, form):
        messages.success(self.request, f'تم إنشاء مركز التكلفة {form.instance.name} بنجاح')
        return super().form_valid(form)

class CostCenterUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = CostCenter
    form_class = CostCenterForm
    template_name = 'core/cost_centers/form.html'
    success_url = reverse_lazy('core:costcenter-list')
    permission_required = 'core.change_costcenter'

    def form_valid(self, form):
        messages.success(self.request, f'تم تعديل مركز التكلفة {form.instance.name} بنجاح')
        return super().form_valid(form)
