from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.db import transaction
from django.views import View
from .models import CashBox, BankAccount, CashTransfer, BankReconciliation
from .forms import CashBoxForm, BankAccountForm, CashTransferForm
from .services import TreasuryService
from datetime import date

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
        return BankReconciliation.objects.select_related('bank_account').all()

class BankReconciliationCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = BankReconciliation
    fields = ['bank_account', 'statement_date', 'statement_balance', 'book_balance']
    template_name = 'treasury/bankreconciliations/form.html'
    permission_required = 'treasury.add_bankreconciliation'
    success_url = reverse_lazy('treasury:bankreconciliation-list')

    def form_valid(self, form):
        # Calculate difference automatically
        obj = form.save(commit=False)
        obj.difference = obj.statement_balance - obj.book_balance
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
    fields = ['bank_account', 'statement_date', 'statement_balance', 'book_balance', 'is_reconciled', 'notes']
    template_name = 'treasury/bankreconciliations/form.html'
    permission_required = 'treasury.change_bankreconciliation'
    success_url = reverse_lazy('treasury:bankreconciliation-list')

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
