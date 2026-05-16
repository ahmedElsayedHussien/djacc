from django.views.generic import ListView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import redirect
from django.views import View
from ..models import Account, CostCenter
from ..forms import AccountForm, CostCenterForm
from ..services import AccountService

class AccountInitializeView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'core.add_account'
    
    def post(self, request, *args, **kwargs):
        count = AccountService.initialize_default_chart()
        # Also run sub-accounts and cost centers
        sub_count = AccountService.setup_common_sub_accounts()
        cc_count = AccountService.setup_default_cost_centers()
        messages.success(request, f'تم إنشاء/تحديث {count + sub_count} حساب و {cc_count} مركز تكلفة بنجاح.')
        return redirect('core:account-list')

class AccountListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
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
        from ..models import AccountType, JournalLine
        from django.db.models import Sum, Q
        from decimal import Decimal
        ctx = super().get_context_data(**kwargs)
        ctx['account_types'] = AccountType.choices
        
        # Fetch all accounts and their data to build an in-memory tree for fast roll-up
        all_accounts_qs = Account.objects.all().values(
            'id', 'parent_id', 'account_type', 'initial_balance', 'initial_balance_type', 'is_leaf'
        )
        
        # 1. Get raw movements for ALL accounts
        all_movements = JournalLine.objects.filter(
            entry__is_posted=True
        ).values('account_id').annotate(
            total_debit=Sum('debit'),
            total_credit=Sum('credit')
        )
        mov_map = {m['account_id']: {'d': m['total_debit'] or Decimal(0), 'c': m['total_credit'] or Decimal(0)} for m in all_movements}
        
        # 2. Get accounts that have an opening entry
        from ..models import JournalEntry
        opening_acc_ids = set(JournalLine.objects.filter(
            entry__entry_type=JournalEntry.EntryType.OPENING,
            entry__is_posted=True
        ).values_list('account_id', flat=True))
        
        # 3. Compute base balances for all leaf nodes
        leaf_bals = {}
        acc_dict = {}
        parent_map = {}
        
        for a in all_accounts_qs:
            acc_dict[a['id']] = a
            pid = a['parent_id']
            if pid:
                parent_map.setdefault(pid, []).append(a['id'])
                
            if a['is_leaf']:
                debit = mov_map.get(a['id'], {}).get('d', Decimal(0))
                credit = mov_map.get(a['id'], {}).get('c', Decimal(0))
                
                if a['id'] not in opening_acc_ids:
                    if a['initial_balance_type'] == 'debit':
                        debit += a['initial_balance']
                    else:
                        credit += a['initial_balance']
                
                if a['account_type'] in ['asset', 'expense']:
                    bal = debit - credit
                else:
                    bal = credit - debit
                leaf_bals[a['id']] = bal

        # 4. Recursive function to get rolled-up balance
        # We cache results to avoid recalculating branches
        calc_cache = {}
        def get_rolled_up_balance(acc_id):
            if acc_id in calc_cache:
                return calc_cache[acc_id]
                
            a = acc_dict.get(acc_id)
            if not a:
                return Decimal(0)
                
            if a['is_leaf']:
                res = leaf_bals.get(acc_id, Decimal(0))
            else:
                res = Decimal(0)
                for cid in parent_map.get(acc_id, []):
                    res += get_rolled_up_balance(cid)
                    
            calc_cache[acc_id] = res
            return res
            
        # 5. Assign to the paginated accounts in the view
        accounts = ctx['accounts']
        for acc in accounts:
            acc.current_balance = get_rolled_up_balance(acc.id)
        
        # Get active fiscal year for the "Generate Opening Entry" button
        from ..models import FiscalYear
        ctx['current_fiscal_year'] = FiscalYear.objects.filter(is_closed=False).order_by('start_date').first()
                
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
    paginate_by = 50

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
