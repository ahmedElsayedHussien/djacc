import logging
from datetime import date, timedelta
from decimal import Decimal
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.core.mixins import PermRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.db import transaction
from django.urls import reverse as django_reverse
from django.views import View
from .models import CashBox, BankAccount, CashTransfer, BankReconciliation, BankTransaction, MobileWallet
from .forms import CashBoxForm, BankAccountForm, CashTransferForm, BankReconciliationForm, BankTransactionForm, IntermediaryCompanyForm, MobileWalletForm
from .services import TreasuryService, BankReconciliationService
from apps.core.models import SystemNotification, JournalLine
from apps.core.services import DocumentService
from apps.core.utils import get_account_balance
from apps.treasury.utils import get_available_cash_boxes
from apps.sales.models import CustomerReceipt, IntermediaryCompany
from apps.purchases.models import SupplierPayment
from django.db.models import Sum, Count, Q

logger = logging.getLogger(__name__)

class TreasuryDashboardView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = CashBox
    template_name = 'treasury/dashboard.html'
    permission_required = 'treasury.view_cashbox'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = date.today()
        
        # 1. Cash Boxes Stats
        cashboxes = get_available_cash_boxes(self.request.user).select_related('account')
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

        # 2.5. Mobile Wallets Stats
        wallets = MobileWallet.objects.filter(is_active=True).select_related('account')
        total_wallet = 0
        wallets_data = []
        for w in wallets:
            bal = get_account_balance(w.account, as_of_date=today)
            total_wallet += bal
            wallets_data.append({'obj': w, 'balance': bal})
            
        ctx['total_wallet'] = total_wallet
        ctx['wallets_data'] = wallets_data

        # 2.8. Intermediary Companies Stats
        intermediaries = IntermediaryCompany.objects.filter(is_active=True).select_related('account')
        total_intermediary = 0
        intermediaries_data = []
        for i in intermediaries:
            bal = get_account_balance(i.account, as_of_date=today)
            total_intermediary += bal
            intermediaries_data.append({'obj': i, 'balance': bal})
            
        ctx['total_intermediary'] = total_intermediary
        ctx['intermediaries_data'] = intermediaries_data

        ctx['total_liquidity'] = total_cash + total_bank + total_wallet + total_intermediary

        # 3. Pending Transfers
        ctx['pending_transfers_count'] = CashTransfer.objects.filter(
            status__in=[CashTransfer.Status.DRAFT, CashTransfer.Status.PENDING]
        ).count()
        
        # 4. Bank Reconciliation Stats
        ctx['pending_reconciliations'] = BankReconciliation.objects.filter(status=BankReconciliation.Status.DRAFT).count()

        # 5. Recent Transfers
        ctx['recent_transfers'] = CashTransfer.objects.order_by('-date', '-id')[:10]

        # 6. Cheque Stats
        ctx['pending_cheques'] = CustomerReceipt.objects.filter(
            payment_method='cheque',
            cheque_status=CustomerReceipt.ChequeStatus.PENDING
        ).select_related('customer').order_by('-date')[:10]
        ctx['bounced_cheques'] = CustomerReceipt.objects.filter(
            payment_method='cheque',
            cheque_status=CustomerReceipt.ChequeStatus.BOUNCED
        ).select_related('customer').order_by('-date')[:10]
        ctx['pending_cheques_count'] = CustomerReceipt.objects.filter(
            payment_method='cheque',
            cheque_status=CustomerReceipt.ChequeStatus.PENDING
        ).count()

        ctx['outgoing_cheques'] = SupplierPayment.objects.filter(
            payment_method='cheque',
            is_cleared=False
        ).select_related('supplier').order_by('-date')[:10]
        ctx['outgoing_cheques_count'] = SupplierPayment.objects.filter(
            payment_method='cheque',
            is_cleared=False
        ).count()

        ctx['overdue_cheques_count'] = CustomerReceipt.objects.filter(
            payment_method='cheque',
            cheque_status=CustomerReceipt.ChequeStatus.PENDING,
            cheque_due_date__lt=date.today()
        ).count()

        return ctx

class CashBoxMovementReportView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = CashBox
    template_name = 'treasury/reports/movements.html'
    permission_required = 'treasury.view_cashbox'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        selected_box = self.request.GET.get('cash_box')
        
        ctx['start_date'] = start_date
        ctx['end_date'] = end_date
        ctx['selected_box'] = selected_box
        
        movements_qs = JournalLine.objects.filter(entry__is_posted=True).select_related('entry', 'account')
        
        box = None
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
        if box:
            if start_date:
                prev_date = date.fromisoformat(start_date) - timedelta(days=1)
                opening_balance = get_account_balance(box.account, as_of_date=prev_date)
            else:
                opening_balance = box.account.initial_balance if box.account.initial_balance_type == 'debit' else -box.account.initial_balance
        
        running_balance = opening_balance
        for mv in movements:
            running_balance += (mv.debit - mv.credit)
            mv.running_balance = running_balance
            
        ctx['opening_balance'] = opening_balance
        # Show chronologically (oldest first) as requested
        ctx['movements'] = movements
        ctx['all_boxes'] = get_available_cash_boxes(self.request.user)
        return ctx

class CashBoxListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = CashBox
    template_name = 'treasury/cashboxes/list.html'
    permission_required = 'treasury.view_cashbox'
    paginate_by = 25

    def get_queryset(self):
        return get_available_cash_boxes(self.request.user).select_related('account', 'responsible_user')

class CashBoxCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
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

class CashBoxUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):
    model = CashBox
    form_class = CashBoxForm
    template_name = 'treasury/cashboxes/form.html'
    permission_required = 'treasury.change_cashbox'
    success_url = reverse_lazy('treasury:cashbox-list')

    def form_valid(self, form):
        TreasuryService.update_cash_box(self.get_object(), form.cleaned_data)
        messages.success(self.request, f'تم تحديث بيانات الخزنة "{self.get_object().name}"')
        return redirect(self.success_url)

class BankAccountListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = BankAccount
    template_name = 'treasury/banks/list.html'
    permission_required = 'treasury.view_bankaccount'
    paginate_by = 25

    def get_queryset(self):
        return BankAccount.objects.select_related('account').filter(is_active=True)

class BankAccountCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = BankAccount
    form_class = BankAccountForm
    template_name = 'treasury/banks/form.html'
    permission_required = 'treasury.add_bankaccount'
    success_url = reverse_lazy('treasury:bank-list')

    def form_valid(self, form):
        bank = TreasuryService.create_bank_account(form.cleaned_data)
        messages.success(self.request, f'تم إنشاء الحساب البنكي "{bank.name}"')
        return redirect(self.success_url)

class BankAccountUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):
    model = BankAccount
    form_class = BankAccountForm
    template_name = 'treasury/banks/form.html'
    permission_required = 'treasury.change_bankaccount'
    success_url = reverse_lazy('treasury:bank-list')

    def form_valid(self, form):
        TreasuryService.update_bank_account(self.get_object(), form.cleaned_data)
        messages.success(self.request, f'تم تحديث بيانات الحساب البنكي "{self.get_object().name}"')
        return redirect(self.success_url)

class CashTransferListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = CashTransfer
    template_name = 'treasury/transfers/list.html'
    context_object_name = 'transfers'
    permission_required = 'treasury.view_cashtransfer'
    paginate_by = 25

    def get_queryset(self):
        return CashTransfer.objects.select_related(
            'from_cash_box', 'from_bank', 'to_cash_box', 'to_bank'
        ).order_by('-date', '-id')

class CashTransferCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = CashTransfer
    form_class = CashTransferForm
    template_name = 'treasury/transfers/form.html'
    success_url = reverse_lazy('treasury:transfer-list')
    permission_required = 'treasury.add_cashtransfer'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        with transaction.atomic():
            form.instance.number = DocumentService.generate_number(CashTransfer, 'XFER')
            form.instance.status = CashTransfer.Status.DRAFT
            self.object = form.save()
            
            # تلقائياً نقوم بإصدار القيد الأول (الخروج من المصدر)
            TreasuryService.process_issue(self.object, self.request.user)
            messages.success(self.request, f'تم إنشاء التحويل {self.object.number} وصرفه من المصدر (قيد الانتظار)')
            
        return redirect('treasury:transfer-detail', pk=self.object.pk)

class CashBoxDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = CashBox
    template_name = 'treasury/cashboxes/detail.html'
    context_object_name = 'cashbox'
    permission_required = 'treasury.view_cashbox'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['balance'] = get_account_balance(self.object.account, as_of_date=date.today())
        return ctx

class BankAccountDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = BankAccount
    template_name = 'treasury/banks/detail.html'
    context_object_name = 'bank'
    permission_required = 'treasury.view_bankaccount'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['balance'] = get_account_balance(self.object.account, as_of_date=date.today())
        return ctx

class CashTransferDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = CashTransfer
    template_name = 'treasury/transfers/detail.html'
    context_object_name = 'transfer'
    permission_required = 'treasury.view_cashtransfer'

class CashTransferReceiveView(LoginRequiredMixin, PermRequiredMixin, View):
    """تأكيد استلام التحويل (الخطوة الثانية)"""
    permission_required = 'treasury.change_cashtransfer'
    
    def post(self, request, pk):
        transfer = get_object_or_404(CashTransfer, pk=pk)
        try:
            with transaction.atomic():
                transfer = CashTransfer.objects.select_for_update().get(pk=pk)
                TreasuryService.process_receive(transfer, request.user)
            messages.success(request, f'تم تأكيد استلام التحويل {transfer.number} بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ أثناء التأكيد: {e}')
        return redirect('treasury:transfer-detail', pk=pk)

class BankReconciliationListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = BankReconciliation
    template_name = 'treasury/bankreconciliations/list.html'
    permission_required = 'treasury.view_bankreconciliation'
    context_object_name = 'reconciliations'
    paginate_by = 25

    def get_queryset(self):
        return BankReconciliation.objects.select_related('bank_account', 'created_by').order_by('-statement_date', '-id')

class BankReconciliationCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = BankReconciliation
    form_class = BankReconciliationForm
    template_name = 'treasury/bankreconciliations/form.html'
    permission_required = 'treasury.add_bankreconciliation'
    success_url = reverse_lazy('treasury:bankreconciliation-list')

    def form_valid(self, form):
        with transaction.atomic():
            obj = form.save(commit=False)
            obj.book_balance = get_account_balance(obj.bank_account.account, as_of_date=obj.statement_date)
            obj.difference = obj.statement_balance - obj.book_balance
            obj.created_by = self.request.user
            obj.save()
        messages.success(self.request, f'تم إنشاء تسوية بنكية للبيان {obj.statement_date}')
        return redirect(self.success_url)

class BankReconciliationDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = BankReconciliation
    template_name = 'treasury/bankreconciliations/detail.html'
    permission_required = 'treasury.view_bankreconciliation'
    context_object_name = 'reconciliation'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.status == BankReconciliation.Status.DRAFT:
            # Recalculate book balance dynamically to reflect any newly posted transactions
            current_book_balance = get_account_balance(obj.bank_account.account, as_of_date=obj.statement_date)
            if obj.book_balance != current_book_balance:
                obj.book_balance = current_book_balance
                obj.difference = obj.statement_balance - obj.book_balance
                obj.save(update_fields=['book_balance', 'difference'])
        return obj

class BankReconciliationUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):
    model = BankReconciliation
    form_class = BankReconciliationForm
    template_name = 'treasury/bankreconciliations/form.html'
    permission_required = 'treasury.change_bankreconciliation'
    success_url = reverse_lazy('treasury:bankreconciliation-list')

    def get_queryset(self):
        # ✅ Fix: Prevent editing if already reconciled
        return super().get_queryset().filter(status=BankReconciliation.Status.DRAFT)

    def dispatch(self, request, *args, **kwargs):
        with transaction.atomic():
            obj = get_object_or_404(BankReconciliation.objects.select_for_update(), pk=kwargs.get('pk'))
            if obj.is_reconciled:
                messages.error(request, "لا يمكن تعديل تسوية بنكية منتهية.")
                return redirect('treasury:bankreconciliation-detail', pk=obj.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        with transaction.atomic():
            obj = form.save(commit=False)
            obj.book_balance = get_account_balance(obj.bank_account.account, as_of_date=obj.statement_date)
            obj.difference = obj.statement_balance - obj.book_balance
            obj.save(update_fields=['difference', 'statement_balance', 'book_balance', 'notes'])
        messages.success(self.request, f'تم تحديث تسوية بنكية للبيان {obj.statement_date}')
        return redirect(self.success_url)

class BankReconciliationLinkTransactionsView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'treasury.change_bankreconciliation'
    
    def get(self, request, pk):
        recon = get_object_or_404(BankReconciliation, pk=pk)
        if recon.is_reconciled:
            messages.error(request, "لا يمكن تعديل تسوية مكتملة.")
            return redirect('treasury:bankreconciliation-detail', pk=pk)
            
        transactions = BankTransaction.objects.filter(
            bank_account=recon.bank_account,
            date__lte=recon.statement_date
        ).filter(
            Q(is_reconciled=False) | Q(pk__in=recon.transactions.values_list('pk', flat=True))
        ).order_by('date')
        
        return render(request, 'treasury/bankreconciliations/link_transactions.html', {
            'reconciliation': recon,
            'transactions': transactions,
            'linked_ids': set(recon.transactions.values_list('pk', flat=True))
        })

    def post(self, request, pk):
        try:
            with transaction.atomic():
                recon = get_object_or_404(BankReconciliation.objects.select_for_update(), pk=pk)
                if recon.is_reconciled:
                    raise ValueError("التسوية مكتملة مسبقاً")
                
                selected_ids = request.POST.getlist('transaction_ids')
                # Only link transactions that belong to this bank and date
                valid_transactions = BankTransaction.objects.filter(
                    pk__in=selected_ids,
                    bank_account=recon.bank_account,
                    date__lte=recon.statement_date
                )
                recon.transactions.set(valid_transactions)
            messages.success(request, 'تم حفظ الحركات المرتبطة بالتسوية بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ أثناء الربط: {e}')
        return redirect('treasury:bankreconciliation-detail', pk=pk)

class BankReconciliationMatchView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'treasury.change_bankreconciliation'
    
    def post(self, request, pk):
        try:
            with transaction.atomic():
                recon = get_object_or_404(BankReconciliation.objects.select_for_update(), pk=pk)
                BankReconciliationService.reconcile(recon, request.user)
            messages.success(request, f'تم إتمام المطابقة البنكية بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ أثناء المطابقة: {e}')
        return redirect('treasury:bankreconciliation-detail', pk=pk)

class CashTransferReverseView(LoginRequiredMixin, PermRequiredMixin, View):

    permission_required = 'treasury.change_cashtransfer'
    
    def post(self, request, pk):
        try:
            with transaction.atomic():
                transfer = get_object_or_404(CashTransfer.objects.select_for_update(), pk=pk)
                TreasuryService.reverse_transfer(transfer, request.user)
            messages.success(request, f'تم عكس التحويل {transfer.number} بنجاح')
            SystemNotification.notify_accountants(
                title="عكس تحويل نقدي",
                message=f"قام {request.user.username} بعكس التحويل النقدي رقم {transfer.number}.",
                url=django_reverse('treasury:transfer-detail', args=[transfer.id])
            )
        except Exception as e:
            messages.error(request, f'خطأ أثناء العكس: {e}')
        return redirect('treasury:transfer-detail', pk=pk)

class IntermediaryCompanyListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = IntermediaryCompany
    template_name = 'treasury/intermediary/list.html'
    context_object_name = 'companies'
    permission_required = 'sales.view_intermediarycompany'
    paginate_by = 25

    def get_queryset(self):
        return IntermediaryCompany.objects.select_related('account').all()

class IntermediaryCompanyCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = IntermediaryCompany
    template_name = 'treasury/intermediary/form.html'
    form_class = IntermediaryCompanyForm
    success_url = reverse_lazy('treasury:intermediary-list')
    permission_required = 'sales.add_intermediarycompany'

class IntermediaryCompanyUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):
    model = IntermediaryCompany
    template_name = 'treasury/intermediary/form.html'
    form_class = IntermediaryCompanyForm
    success_url = reverse_lazy('treasury:intermediary-list')
    permission_required = 'sales.change_intermediarycompany'

# --- Bank Transaction Views ---

class BankTransactionListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = BankTransaction
    template_name = 'treasury/banktransactions/list.html'
    permission_required = 'treasury.view_banktransaction'
    context_object_name = 'transactions'
    paginate_by = 25

    def get_queryset(self):
        return BankTransaction.objects.select_related('bank_account', 'created_by').order_by('-date', '-id')

class BankTransactionCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = BankTransaction
    form_class = BankTransactionForm
    template_name = 'treasury/banktransactions/form.html'
    permission_required = 'treasury.add_banktransaction'
    success_url = reverse_lazy('treasury:banktransaction-list')

    def form_valid(self, form):
        with transaction.atomic():
            form.instance.number = DocumentService.generate_number(BankTransaction, 'BTRN')
            form.instance.created_by = self.request.user
            self.object = form.save()
            messages.success(self.request, f'تم تسجيل الحركة البنكية {self.object.number}')
        return redirect(self.success_url)

class BankTransactionDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = BankTransaction
    template_name = 'treasury/banktransactions/detail.html'
    permission_required = 'treasury.view_banktransaction'
    context_object_name = 'transaction'

class BankTransactionPostView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'treasury.change_banktransaction'
    
    def post(self, request, pk):
        try:
            with transaction.atomic():
                trans = get_object_or_404(BankTransaction.objects.select_for_update(), pk=pk)
                TreasuryService.process_bank_transaction(trans, request.user)
            messages.success(request, f'تم ترحيل الحركة البنكية {trans.number} بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ أثناء الترحيل: {e}')
        return redirect('treasury:banktransaction-detail', pk=pk)

# --- Mobile Wallet Views ---

class MobileWalletListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = MobileWallet
    template_name = 'treasury/wallets/list.html'
    permission_required = 'treasury.view_mobilewallet'
    paginate_by = 25

    def get_queryset(self):
        return MobileWallet.objects.select_related('account').filter(is_active=True)

class MobileWalletCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = MobileWallet
    form_class = MobileWalletForm
    template_name = 'treasury/wallets/form.html'
    permission_required = 'treasury.add_mobilewallet'
    success_url = reverse_lazy('treasury:wallet-list')

    def form_valid(self, form):
        wallet = TreasuryService.create_mobile_wallet(form.cleaned_data)
        messages.success(self.request, f'تم إنشاء المحفظة الإلكترونية "{wallet.name}" بنجاح')
        return redirect(self.success_url)

class MobileWalletUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):
    model = MobileWallet
    form_class = MobileWalletForm
    template_name = 'treasury/wallets/form.html'
    permission_required = 'treasury.change_mobilewallet'
    success_url = reverse_lazy('treasury:wallet-list')

    def form_valid(self, form):
        TreasuryService.update_mobile_wallet(self.get_object(), form.cleaned_data)
        messages.success(self.request, f'تم تحديث بيانات المحفظة الإلكترونية "{self.get_object().name}"')
        return redirect(self.success_url)

class MobileWalletDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = MobileWallet
    template_name = 'treasury/wallets/detail.html'
    context_object_name = 'wallet'
    permission_required = 'treasury.view_mobilewallet'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['balance'] = get_account_balance(self.object.account, as_of_date=date.today())
        return ctx
