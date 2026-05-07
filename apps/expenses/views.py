from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import redirect
from django.views import View
from .models import Expense, ExpenseCategory, Custody
from .forms import ExpenseForm, ExpenseCategoryForm, CustodyForm
from .services import ExpenseService # Assuming it exists based on dir listing

class ExpenseListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Expense
    template_name = 'expenses/list.html'
    context_object_name = 'expenses'
    permission_required = 'expenses.view_expense'
    paginate_by = 25

class ExpenseCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'expenses/form.html'
    success_url = reverse_lazy('expenses:expense-list')
    permission_required = 'expenses.add_expense'

    def form_valid(self, form):
        from apps.core.services import DocumentService
        from django.db import transaction
        
        with transaction.atomic():
            expense = form.instance
            expense.number = DocumentService.generate_number(Expense, 'EXP')
            expense.created_by = self.request.user
            
            # Calculate Taxes
            subtotal = expense.subtotal
            tax1_val = 0
            if expense.tax_type:
                rate = expense.tax_percent if expense.tax_percent else expense.tax_type.rate
                tax1_val = subtotal * (rate / 100)
                if expense.tax_type.category in ['wht', 'salary', 'insurance']:
                    tax1_val = -tax1_val # Deduction
            
            tax2_val = 0
            if expense.tax_type2:
                rate2 = expense.tax_percent2 if expense.tax_percent2 else expense.tax_type2.rate
                tax2_val = subtotal * (rate2 / 100)
                if expense.tax_type2.category in ['wht', 'salary', 'insurance']:
                    tax2_val = -tax2_val # Deduction
            
            expense.tax_amount = abs(tax1_val) + abs(tax2_val) # Total absolute taxes
            expense.total = subtotal + tax1_val + tax2_val # Net Payable
            expense.amount = expense.total # Final Net Paid
            
            response = super().form_valid(form)
            
        messages.success(self.request, f'تم تسجيل المصروف {expense.number} بنجاح')
        return response

class ExpenseApproveView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'expenses.change_expense'
    
    def post(self, request, pk):
        from django.shortcuts import get_object_or_404
        expense = get_object_or_404(Expense, pk=pk)
        if expense.status != Expense.Status.DRAFT:
            messages.warning(request, "يمكن فقط اعتماد المصروفات في حالة المسودة")
            return redirect('expenses:expense-detail', pk=pk)
            
        expense.status = Expense.Status.APPROVED
        expense.approved_by = request.user
        expense.save()
        messages.success(request, f'تم اعتماد المصروف {expense.number} بنجاح')
        return redirect('expenses:expense-detail', pk=pk)

class ExpensePostView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'expenses.change_expense'
    
    def post(self, request, pk):
        from .services import ExpenseService
        from django.shortcuts import get_object_or_404
        expense = get_object_or_404(Expense, pk=pk)
        if expense.status == Expense.Status.POSTED:
            messages.warning(request, "هذا المصروف تم ترحيله بالفعل")
            return redirect('expenses:expense-detail', pk=pk)
        
        if expense.status != Expense.Status.APPROVED:
            messages.warning(request, "يجب اعتماد المصروف أولاً قبل الترحيل")
            return redirect('expenses:expense-detail', pk=pk)
            
        try:
            ExpenseService.post_expense(expense, request.user)
            messages.success(request, f'تم ترحيل المصروف {expense.number}')
        except Exception as e:
            messages.error(request, f'خطأ في الترحيل: {e}')
        return redirect('expenses:expense-detail', pk=pk)

class ExpenseReverseView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'expenses.change_expense'
    
    def post(self, request, pk):
        from .services import ExpenseService
        from django.shortcuts import get_object_or_404
        expense = get_object_or_404(Expense, pk=pk)
        
        try:
            ExpenseService.reverse_expense(expense, request.user)
            messages.success(request, f'تم عكس المصروف {expense.number} وإنشاء قيد عكسي بنجاح.')
        except Exception as e:
            messages.error(request, f'خطأ في العكس: {e}')
        return redirect('expenses:expense-detail', pk=pk)

class ExpenseCategoryListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = ExpenseCategory
    template_name = 'expenses/categories/list.html'
    permission_required = 'expenses.view_expensecategory'

class ExpenseCategoryCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = ExpenseCategory
    form_class = ExpenseCategoryForm
    template_name = 'expenses/categories/form.html'
    success_url = reverse_lazy('expenses:category-list')
    permission_required = 'expenses.add_expensecategory'

class CustodyListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Custody
    template_name = 'expenses/custody/list.html'
    permission_required = 'expenses.view_custody'

class CustodyCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Custody
    form_class = CustodyForm
    template_name = 'expenses/custody/form.html'
    success_url = reverse_lazy('expenses:custody-list')
    permission_required = 'expenses.add_custody'

    def form_valid(self, form):
        from apps.core.services import DocumentService
        from .services import CustodyService
        from django.db import transaction
        
        with transaction.atomic():
            form.instance.number = DocumentService.generate_number(Custody, 'CUS')
            # Fix: created_by removed as it doesn't exist in Custody model
            response = super().form_valid(form)
            CustodyService.issue_custody(self.object, self.request.user)
            messages.success(self.request, f'تم صرف العهدة رقم {self.object.number} وإنشاء القيد المحاسبي بنجاح.')
            return response

class ExpenseDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Expense
    template_name = 'expenses/detail.html'
    context_object_name = 'expense'
    permission_required = 'expenses.view_expense'

class CustodyDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Custody
    template_name = 'expenses/custody/detail.html'
    context_object_name = 'custody'
    permission_required = 'expenses.view_custody'

from .models import CustodySettlement
from .forms import CustodySettlementForm

class CustodySettlementCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = CustodySettlement
    form_class = CustodySettlementForm
    template_name = 'expenses/custody/settlement_form.html'
    permission_required = 'expenses.add_custodysettlement'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from django.shortcuts import get_object_or_404
        custody = get_object_or_404(Custody, pk=self.kwargs['custody_pk'])
        ctx['custody'] = custody
        
        # Calculate pending expenses
        from django.db.models import Sum
        expenses = custody.expense_set.filter(status='posted')
        total_expenses = expenses.aggregate(t=Sum('amount'))['t'] or 0
        ctx['pending_expenses'] = expenses
        ctx['total_expenses'] = total_expenses
        ctx['remaining_balance'] = custody.amount - custody.settled_amount - total_expenses
        return ctx
        
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        from django.shortcuts import get_object_or_404
        form.custody_obj = get_object_or_404(Custody, pk=self.kwargs['custody_pk'])
        return form

    def form_valid(self, form):
        from django.shortcuts import get_object_or_404
        from .services import CustodyService
        from django.db import transaction
        
        with transaction.atomic():
            custody = form.custody_obj
            form.instance.custody = custody
            
            self.object = form.save()
            CustodyService.settle_custody(self.object, self.request.user)
            
            messages.success(self.request, 'تمت تسوية العهدة بنجاح')
            return redirect('expenses:custody-detail', pk=custody.pk)
