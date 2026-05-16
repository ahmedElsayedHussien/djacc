from django.views.generic import ListView, CreateView, UpdateView, DetailView
from decimal import Decimal
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.db import transaction
from django.views import View
from .models import CashBox, BankAccount, CashTransfer, BankReconciliation, BankTransaction
from .forms import CashBoxForm, BankAccountForm, CashTransferForm, BankReconciliationForm, BankTransactionForm
from .services import TreasuryService
from django.db.models import Sum, Count, Q
from django.utils import timezone
from apps.core.utils import get_account_balance
from datetime import date

class TreasuryDashboardView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = CashBox
    template_name = 'treasury/dashboard.html'
    permission_required = 'treasury.view_cashbox'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = date.today()
        
        # 1. Cash Boxes Stats
        cashboxes = CashBox.objects.filter(is_active=True).select_related('account')
        total_cash = 0
        boxes_data = []
        for cb in cashboxes:
            bal = get_account_balance(cb.account, as_of_date=today)
            total_cash += bal
            boxes_data.append({'obj': cb, 'balance': bal})
        
        ctx['total_cash'] = total_cash
        ctx['boxes_data'] = boxes_data

        # 2. Bank Accounts Stats
        banks = BankAccount.objects.filter(is_active=True).select_related('account')
        total_bank = 0
        banks_data = []
        for b in banks:
            bal = get_account_balance(b.account, as_of_date=today)
            total_bank += bal
            banks_data.append({'obj': b, 'balance': bal})
            
        ctx['total_bank'] = total_bank
        ctx['banks_data'] = banks_data
        ctx['total_liquidity'] = total_cash + total_bank

        # 3. Pending Transfers
        ctx['pending_transfers_count'] = CashTransfer.objects.filter(
            status__in=[CashTransfer.Status.DRAFT, CashTransfer.Status.PENDING]
        ).count()
        
        # 4. Bank Reconciliation Stats
        ctx['pending_reconciliations'] = BankReconciliation.objects.filter(status=BankReconciliation.Status.DRAFT).count()

        # 5. Recent Transfers
        ctx['recent_transfers'] = CashTransfer.objects.order_by('-date', '-id')[:10]

        return ctx

class CashBoxMovementReportView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = CashBox
    template_name = 'treasury/reports/movements.html'
    permission_required = 'treasury.view_cashbox'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.core.models import JournalLine
        
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        selected_box = self.request.GET.get('cash_box')
        
        ctx['start_date'] = start_date
        ctx['end_date'] = end_date
        ctx['selected_box'] = selected_box
        
        movements_qs = JournalLine.objects.filter(entry__is_posted=True).select_related('entry', 'account')
        
        if selected_box:
            box = get_object_or_404(CashBox, pk=selected_box)
            movements_qs = movements_qs.filter(account=box.account)
        else:
            # All cash box accounts
            box_accounts = CashBox.objects.values_list('account_id', flat=True)
            movements_qs = movements_qs.filter(account_id__in=box_accounts)
            
        if start_date:
            movements_qs = movements_qs.filter(entry__date__gte=start_date)
        if end_date:
            movements_qs = movements_qs.filter(entry__date__lte=end_date)
            
        # Order chronologically to calculate running balance
        movements = list(movements_qs.order_by('entry__date', 'id'))
        
        opening_balance = Decimal('0')
        if selected_box:
            box = get_object_or_404(CashBox, pk=selected_box)
            from apps.core.utils import get_account_balance
            from datetime import date as date_type, timedelta
            if start_date:
                # Balance before start_date
                prev_date = date_type.fromisoformat(start_date) - timedelta(days=1)
                opening_balance = get_account_balance(box.account, as_of_date=prev_date)
            else:
                # No start date means we include all history, but initial balance still applies
                # Actually, get_account_balance with no date gives current, but we need start of time.
                # If no start_date, opening balance is just the initial balance of the account
                opening_balance = box.account.initial_balance if box.account.initial_balance_type == 'debit' else -box.account.initial_balance
        
        running_balance = opening_balance
        for mv in movements:
            running_balance += (mv.debit - mv.credit)
            mv.running_balance = running_balance
            
        ctx['opening_balance'] = opening_balance
        # Show chronologically (oldest first) as requested
        ctx['movements'] = movements
        ctx['all_boxes'] = CashBox.objects.filter(is_active=True)
        return ctx

class CashBoxListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = CashBox
    template_name = 'treasury/cashboxes/list.html'
    permission_required = 'treasury.view_cashbox'

    def get_queryset(self):
        return CashBox.objects.select_related('account', 'responsible_user').filter(is_active=True)

class CashBoxCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = CashBox
    form_class = CashBoxForm
    template_name = 'treasury/cashboxes/form.html'
    permission_required = 'treasury.add_cashbox'
    success_url = reverse_lazy('treasury:cashbox-list')

    def form_valid(self, form):
        cash_box = TreasuryService.create_cash_box(form.cleaned_data)
        messages.success(self.request,
            f'تم إنشاء الخزنة "{cash_box.name}" — كود الحساب: {cash_box.account.code}')
        return redirect(self.success_url)

class CashBoxUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = CashBox
    form_class = CashBoxForm
    template_name = 'treasury/cashboxes/form.html'
    permission_required = 'treasury.change_cashbox'
    success_url = reverse_lazy('treasury:cashbox-list')

    def form_valid(self, form):
        TreasuryService.update_cash_box(self.get_object(), form.cleaned_data)
        messages.success(self.request, f'تم تحديث بيانات الخزنة "{self.get_object().name}"')
        return redirect(self.success_url)

class BankAccountListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = BankAccount
    template_name = 'treasury/banks/list.html'
    permission_required = 'treasury.view_bankaccount'

    def get_queryset(self):
        return BankAccount.objects.select_related('account').filter(is_active=True)

class BankAccountCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = BankAccount
    form_class = BankAccountForm
    template_name = 'treasury/banks/form.html'
    permission_required = 'treasury.add_bankaccount'
    success_url = reverse_lazy('treasury:bank-list')

    def form_valid(self, form):
        bank = TreasuryService.create_bank_account(form.cleaned_data)
        messages.success(self.request, f'تم إنشاء الحساب البنكي "{bank.name}"')
        return redirect(self.success_url)

class BankAccountUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = BankAccount
    form_class = BankAccountForm
    template_name = 'treasury/banks/form.html'
    permission_required = 'treasury.change_bankaccount'
    success_url = reverse_lazy('treasury:bank-list')

    def form_valid(self, form):
        TreasuryService.update_bank_account(self.get_object(), form.cleaned_data)
        messages.success(self.request, f'تم تحديث بيانات الحساب البنكي "{self.get_object().name}"')
        return redirect(self.success_url)

class CashTransferListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = CashTransfer
    template_name = 'treasury/transfers/list.html'
    context_object_name = 'transfers'
    permission_required = 'treasury.view_cashtransfer'

class CashTransferCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = CashTransfer
    form_class = CashTransferForm
    template_name = 'treasury/transfers/form.html'
    success_url = reverse_lazy('treasury:transfer-list')
    permission_required = 'treasury.add_cashtransfer'

    def form_valid(self, form):
        with transaction.atomic():
            from apps.core.services import DocumentService
            form.instance.number = DocumentService.generate_number(CashTransfer, 'XFER')
            form.instance.status = CashTransfer.Status.DRAFT
            self.object = form.save()
            
            # تلقائياً نقوم بإصدار القيد الأول (الخروج من المصدر)
            TreasuryService.process_issue(self.object, self.request.user)
            messages.success(self.request, f'تم إنشاء التحويل {self.object.number} وصرفه من المصدر (قيد الانتظار)')
            
        return redirect('treasury:transfer-detail', pk=self.object.pk)

class CashBoxDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = CashBox
    template_name = 'treasury/cashboxes/detail.html'
    context_object_name = 'cashbox'
    permission_required = 'treasury.view_cashbox'

    def get_context_data(self, **kwargs):
        from apps.core.utils import get_account_balance
        ctx = super().get_context_data(**kwargs)
        ctx['balance'] = get_account_balance(self.object.account, as_of_date=date.today())
        return ctx

class BankAccountDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = BankAccount
    template_name = 'treasury/banks/detail.html'
    context_object_name = 'bank'
    permission_required = 'treasury.view_bankaccount'

    def get_context_data(self, **kwargs):
        from apps.core.utils import get_account_balance
        ctx = super().get_context_data(**kwargs)
        ctx['balance'] = get_account_balance(self.object.account, as_of_date=date.today())
        return ctx

class CashTransferDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = CashTransfer
    template_name = 'treasury/transfers/detail.html'
    context_object_name = 'transfer'
    permission_required = 'treasury.view_cashtransfer'

class CashTransferReceiveView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """تأكيد استلام التحويل (الخطوة الثانية)"""
    permission_required = 'treasury.change_cashtransfer'
    
    def post(self, request, pk):
        transfer = get_object_or_404(CashTransfer, pk=pk)
        try:
            TreasuryService.process_receive(transfer, request.user)
            messages.success(request, f'تم تأكيد استلام التحويل {transfer.number} بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ أثناء التأكيد: {e}')
        return redirect('treasury:transfer-detail', pk=pk)

class BankReconciliationListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = BankReconciliation
    template_name = 'treasury/bankreconciliations/list.html'
    permission_required = 'treasury.view_bankreconciliation'
    context_object_name = 'reconciliations'

    def get_queryset(self):
        return BankReconciliation.objects.select_related('bank_account', 'created_by').all()

class BankReconciliationCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = BankReconciliation
    form_class = BankReconciliationForm
    template_name = 'treasury/bankreconciliations/form.html'
    permission_required = 'treasury.add_bankreconciliation'
    success_url = reverse_lazy('treasury:bankreconciliation-list')

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.difference = obj.statement_balance - obj.book_balance
        obj.created_by = self.request.user
        obj.save()
        messages.success(self.request, f'تم إنشاء تسوية بنكية للبيان {obj.statement_date}')
        return redirect(self.success_url)

class BankReconciliationDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = BankReconciliation
    template_name = 'treasury/bankreconciliations/detail.html'
    permission_required = 'treasury.view_bankreconciliation'
    context_object_name = 'reconciliation'

class BankReconciliationUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = BankReconciliation
    form_class = BankReconciliationForm
    template_name = 'treasury/bankreconciliations/form.html'
    permission_required = 'treasury.change_bankreconciliation'
    success_url = reverse_lazy('treasury:bankreconciliation-list')

    def get_queryset(self):
        # ✅ Fix: Prevent editing if already reconciled
        return super().get_queryset().filter(status=BankReconciliation.Status.DRAFT)

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.is_reconciled:
            messages.error(request, "لا يمكن تعديل تسوية بنكية منتهية.")
            return redirect('treasury:bankreconciliation-detail', pk=obj.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.difference = obj.statement_balance - obj.book_balance
        obj.save()
        messages.success(self.request, f'تم تحديث تسوية بنكية للبيان {obj.statement_date}')
        return redirect(self.success_url)

class BankReconciliationMatchView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'treasury.change_bankreconciliation'
    
    def post(self, request, pk):
        recon = get_object_or_404(BankReconciliation, pk=pk)
        try:
            from .services import BankReconciliationService
            BankReconciliationService.reconcile(recon, request.user)
            messages.success(request, f'تم إتمام المطابقة البنكية بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ أثناء المطابقة: {e}')
        return redirect('treasury:bankreconciliation-detail', pk=pk)

class CashTransferReverseView(LoginRequiredMixin, PermissionRequiredMixin, View):

    permission_required = 'treasury.change_cashtransfer'
    
    def post(self, request, pk):
        transfer = get_object_or_404(CashTransfer, pk=pk)
        try:
            TreasuryService.reverse_transfer(transfer, request.user)
            messages.success(request, f'تم عكس التحويل {transfer.number} بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ أثناء العكس: {e}')
        return redirect('treasury:transfer-detail', pk=pk)

# --- Bank Transaction Views ---

class BankTransactionListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = BankTransaction
    template_name = 'treasury/banktransactions/list.html'
    permission_required = 'treasury.view_banktransaction'
    context_object_name = 'transactions'

    def get_queryset(self):
        return BankTransaction.objects.select_related('bank_account', 'created_by').order_by('-date', '-id')

class BankTransactionCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = BankTransaction
    form_class = BankTransactionForm
    template_name = 'treasury/banktransactions/form.html'
    permission_required = 'treasury.add_banktransaction'
    success_url = reverse_lazy('treasury:banktransaction-list')

    def form_valid(self, form):
        with transaction.atomic():
            from apps.core.services import DocumentService
            form.instance.number = DocumentService.generate_number(BankTransaction, 'BTRN')
            form.instance.created_by = self.request.user
            self.object = form.save()
            messages.success(self.request, f'تم تسجيل الحركة البنكية {self.object.number}')
        return redirect(self.success_url)

class BankTransactionDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = BankTransaction
    template_name = 'treasury/banktransactions/detail.html'
    permission_required = 'treasury.view_banktransaction'
    context_object_name = 'transaction'

class BankTransactionPostView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'treasury.change_banktransaction'
    
    def post(self, request, pk):
        trans = get_object_or_404(BankTransaction, pk=pk)
        try:
            TreasuryService.process_bank_transaction(trans, request.user)
            messages.success(request, f'تم ترحيل الحركة البنكية {trans.number} بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ أثناء الترحيل: {e}')
        return redirect('treasury:banktransaction-detail', pk=pk)
