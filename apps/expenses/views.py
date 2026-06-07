import logging
from decimal import Decimal
from datetime import timedelta
from django.views.generic import ListView, CreateView, UpdateView, DetailView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.core.mixins import PermRequiredMixin
from django.urls import reverse_lazy, reverse as django_reverse
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.views import View
from apps.core.services import DocumentService, AuditService
from apps.core.tax_utils import calculate_line_taxes
from apps.core.models import SystemNotification
from .models import Expense, ExpenseCategory, Custody, CustodySettlement
from .forms import ExpenseForm, ExpenseCategoryForm, CustodyForm, CustodySettlementForm
from .services import ExpenseService, CustodyService

logger = logging.getLogger(__name__)

class ExpenseDashboardView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'expenses/dashboard.html'
    permission_required = 'expenses.view_expense'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        now = timezone.now()
        month_start = now.replace(day=1)
        
        # 1. Monthly Summary
        monthly_stats = Expense.objects.filter(
            date__gte=month_start, 
            status=Expense.Status.POSTED
        ).aggregate(
            total_amount=Sum('amount'),
            count=Count('id')
        )
        ctx['monthly_total'] = monthly_stats['total_amount'] or 0
        ctx['monthly_count'] = monthly_stats['count'] or 0

        # 2. Category Distribution (Current Month)
        ctx['category_stats'] = ExpenseCategory.objects.annotate(
            total=Sum('expense__amount', filter=Q(expense__date__gte=month_start, expense__status=Expense.Status.POSTED))
        ).filter(total__gt=0).order_by('-total')

        # 3. Pending Approvals
        ctx['pending_expenses'] = Expense.objects.filter(status=Expense.Status.DRAFT).count()
        
        # 4. Custody Summary
        custody_stats = Custody.objects.aggregate(
            open_count=Count('id', filter=Q(status=Custody.Status.OPEN)),
            total_open_amount=Sum('amount', filter=Q(status=Custody.Status.OPEN))
        )
        ctx['open_custodies_count'] = custody_stats['open_count'] or 0
        ctx['total_open_custody_amount'] = custody_stats['total_open_amount'] or 0

        # 5. Recent Expenses
        ctx['recent_expenses'] = Expense.objects.select_related('category', 'cost_center').order_by('-date', '-id')[:10]

        # 6. Trends (Last 6 Months)
        # For simplicity in this view, we'll just pass raw data for the chart if needed
        return ctx

class ExpenseListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = Expense
    template_name = 'expenses/list.html'
    context_object_name = 'expenses'
    permission_required = 'expenses.view_expense'
    paginate_by = 25

    def get_queryset(self):
        return super().get_queryset().select_related('category', 'cost_center', 'created_by', 'approved_by')

class ExpenseCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'expenses/form.html'
    success_url = reverse_lazy('expenses:expense-list')
    permission_required = 'expenses.add_expense'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        with transaction.atomic():
            expense = form.instance
            expense.number = DocumentService.generate_number(Expense, 'EXP')
            expense.created_by = self.request.user
            
            # Calculate Taxes
            subtotal = Decimal(str(expense.subtotal or '0'))
            res = calculate_line_taxes(
                subtotal,
                expense.tax_type,
                expense.tax_percent,
                expense.tax_type2,
                expense.tax_percent2,
                is_purchase_or_expense=True
            )
            
            expense.tax_amount = res['tax_total_added'] + res['tax_total_deducted']
            expense.total = subtotal + res['tax1_signed'] + res['tax2_signed']
            expense.amount = expense.total
            
            response = super().form_valid(form)
            
        messages.success(self.request, f'تم تسجيل المصروف {expense.number} بنجاح')
        return response

class ExpenseApproveView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'expenses.change_expense'
    
    def post(self, request, pk):
        with transaction.atomic():
            expense = get_object_or_404(Expense.objects.select_for_update(), pk=pk)
            if expense.status != Expense.Status.DRAFT:
                messages.warning(request, "يمكن فقط اعتماد المصروفات في حالة المسودة")
                return redirect('expenses:expense-detail', pk=pk)
                
            expense.status = Expense.Status.APPROVED
            expense.approved_by = request.user
            expense.save()
        AuditService.log(request.user, 'Approve', expense, f'اعتماد مصروف رقم {expense.number}')
        messages.success(request, f'تم اعتماد المصروف {expense.number} بنجاح')
        return redirect('expenses:expense-detail', pk=pk)

class ExpensePostView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'expenses.change_expense'
    
    def post(self, request, pk):
        expense = get_object_or_404(Expense.objects.select_for_update(), pk=pk)
        if expense.status == Expense.Status.POSTED:
            messages.warning(request, "هذا المصروف تم ترحيله بالفعل")
            return redirect('expenses:expense-detail', pk=pk)
        
        if expense.status != Expense.Status.APPROVED:
            messages.warning(request, "يجب اعتماد المصروف أولاً قبل الترحيل")
            return redirect('expenses:expense-detail', pk=pk)
            
        try:
            ExpenseService.post_expense(expense, request.user)
            
            from apps.core.utils import get_account_balance, clear_balance_cache
            clear_balance_cache()
            
            acc = None
            if expense.cash_box:
                acc = expense.cash_box.account
            elif expense.bank_account:
                acc = expense.bank_account.account
                
            if acc:
                new_balance = get_account_balance(acc)
                if new_balance < 0:
                    messages.warning(request, f'تم ترحيل المصروف {expense.number}، لكن تنبيه: رصيد {acc.name} أصبح بالسالب ({new_balance}).')
                else:
                    messages.success(request, f'تم ترحيل المصروف {expense.number}')
            else:
                messages.success(request, f'تم ترحيل المصروف {expense.number}')
        except Exception as e:
            logger.exception("خطأ في ترحيل المصروف %s", pk)
            messages.error(request, f'خطأ في الترحيل: {e}')
        return redirect('expenses:expense-detail', pk=pk)

class ExpenseReverseView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'expenses.change_expense'
    
    def post(self, request, pk):
        expense = get_object_or_404(Expense, pk=pk)
        
        try:
            ExpenseService.reverse_expense(expense, request.user)
            messages.success(request, f'تم عكس المصروف {expense.number} وإنشاء قيد عكسي بنجاح.')
            SystemNotification.notify_accountants(
                title="عكس مصروف",
                message=f"قام {request.user.username} بعكس المصروف رقم {expense.number} بقيمة {expense.amount:.2f} ج.م.",
                url=django_reverse('expenses:expense-detail', args=[expense.id])
            )
        except Exception as e:
            logger.exception("خطأ في عكس المصروف %s", pk)
            messages.error(request, f'خطأ في العكس: {e}')
        return redirect('expenses:expense-detail', pk=pk)

class ExpenseCategoryListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = ExpenseCategory
    template_name = 'expenses/categories/list.html'
    context_object_name = 'categories'
    permission_required = 'expenses.view_expensecategory'
    paginate_by = 25

class ExpenseCategoryCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = ExpenseCategory
    form_class = ExpenseCategoryForm
    template_name = 'expenses/categories/form.html'
    success_url = reverse_lazy('expenses:category-list')
    permission_required = 'expenses.add_expensecategory'

class CustodyListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = Custody
    template_name = 'expenses/custody/list.html'
    context_object_name = 'custodies'
    permission_required = 'expenses.view_custody'
    paginate_by = 25

    def get_queryset(self):
        return super().get_queryset().select_related('employee', 'cash_box')

class CustodyCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = Custody
    form_class = CustodyForm
    template_name = 'expenses/custody/form.html'
    success_url = reverse_lazy('expenses:custody-list')
    permission_required = 'expenses.add_custody'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        with transaction.atomic():
            form.instance.number = DocumentService.generate_number(Custody, 'CUS')
            form.instance.created_by = self.request.user
            
            # Fetch or Auto-create custody account
            employee = form.cleaned_data['employee']
            from apps.core.models import Account
            from django.conf import settings
            custody_parent_code = getattr(settings, 'CUSTODY_ACCOUNTS_PARENT', '1142')
            parent_account = Account.objects.filter(code=custody_parent_code).first()
            if not parent_account:
                messages.error(self.request, f'خطأ: لم يتم العثور على الحساب الرئيسي للعهد ({custody_parent_code}). يرجى التحقق من إعدادات النظام.')
                return super().form_invalid(form)
            
            account_name = f'عهدة - {employee.first_name} {employee.last_name}'.strip()
            account = Account.objects.filter(name=account_name, parent=parent_account).first()
            if not account:
                last_acc = Account.objects.filter(parent=parent_account).order_by('code').last()
                if last_acc:
                    try:
                        next_seq = int(last_acc.code[len(parent_account.code):]) + 1
                    except ValueError:
                        next_seq = Account.objects.filter(parent=parent_account).count() + 1
                else:
                    next_seq = 1
                account = Account.objects.create(
                    code=f'{parent_account.code}{next_seq:03d}',
                    name=account_name,
                    account_type=parent_account.account_type,
                    parent=parent_account,
                    is_leaf=True,
                )
            form.instance.account = account
            
            response = super().form_valid(form)
            CustodyService.issue_custody(self.object, self.request.user)
            
            from apps.core.utils import get_account_balance, clear_balance_cache
            clear_balance_cache()
            if self.object.cash_box:
                new_balance = get_account_balance(self.object.cash_box.account)
                if new_balance < 0:
                    messages.warning(self.request, f'تم صرف العهدة رقم {self.object.number} وإنشاء القيد، لكن تنبيه: رصيد {self.object.cash_box.name} أصبح بالسالب ({new_balance}).')
                    return response
                    
            messages.success(self.request, f'تم صرف العهدة رقم {self.object.number} وإنشاء القيد المحاسبي بنجاح.')
            return response

class ExpenseDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = Expense
    template_name = 'expenses/detail.html'
    context_object_name = 'expense'
    permission_required = 'expenses.view_expense'

    def get_queryset(self):
        return super().get_queryset().select_related('category', 'cost_center', 'tax_type', 'tax_type2', 'bank_account', 'cash_box', 'custody', 'created_by', 'approved_by', 'journal_entry')

class CustodyDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = Custody
    template_name = 'expenses/custody/detail.html'
    context_object_name = 'custody'
    permission_required = 'expenses.view_custody'

    def get_queryset(self):
        return super().get_queryset().select_related(
            'employee', 'account', 'cash_box', 'journal_entry'
        ).prefetch_related(
            'settlements', 'settlements__journal_entry',
            'expense_set', 'expense_set__category'
        )

class CustodySettlementCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = CustodySettlement
    form_class = CustodySettlementForm
    template_name = 'expenses/custody/settlement_form.html'
    permission_required = 'expenses.add_custodysettlement'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        custody = get_object_or_404(Custody, pk=self.kwargs['custody_pk'])
        ctx['custody'] = custody
        
        # Calculate pending expenses
        expenses = custody.expense_set.filter(status=Expense.Status.POSTED).select_related('category', 'cost_center')
        total_expenses = expenses.aggregate(t=Sum('amount'))['t'] or 0
        ctx['pending_expenses'] = expenses
        ctx['total_expenses'] = total_expenses
        ctx['remaining_balance'] = custody.amount - custody.settled_amount - total_expenses
        return ctx
        
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.custody_obj = get_object_or_404(Custody, pk=self.kwargs['custody_pk'])
        return form

    def form_valid(self, form):
        with transaction.atomic():
            custody = form.custody_obj
            form.instance.custody = custody
            form.instance.created_by = self.request.user
            
            self.object = form.save()
            CustodyService.settle_custody(self.object, self.request.user)
            
            from apps.core.utils import get_account_balance, clear_balance_cache
            clear_balance_cache()
            if self.object.cash_box:
                new_balance = get_account_balance(self.object.cash_box.account)
                if new_balance < 0:
                    messages.warning(self.request, f'تمت تسوية العهدة بنجاح، لكن تنبيه: رصيد {self.object.cash_box.name} أصبح بالسالب ({new_balance}).')
                    return redirect('expenses:custody-detail', pk=custody.pk)
                    
            messages.success(self.request, 'تمت تسوية العهدة بنجاح')
            return redirect('expenses:custody-detail', pk=custody.pk)
