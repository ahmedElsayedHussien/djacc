from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from apps.core.mixins import perm_required
from apps.sales.models import SalesInvoice, Customer
from apps.purchases.models import PurchaseInvoice
from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.hr.models import Employee
from apps.inventory.models import Item, ItemLedger
from apps.core.models import JournalEntry, AuditLog, Account, JournalLine, SystemNotification
from apps.core.utils import compute_account_balances, clear_balance_cache
from django.utils import timezone
from django.db.models import Sum, Q, F
from decimal import Decimal
from django.conf import settings

@login_required
def login_redirect(request):
    """توجيه المستخدم بعد تسجيل الدخول إلى لوحة التحكم المختصة حسب صلاحياته"""
    user = request.user

    # 1. مندوب المبيعات → لوحة أداء المندوب (أولوية قصوى)
    if hasattr(user, 'salesrepresentative'):
        return redirect('reports:rep_dashboard')

    # 2. السوبر ادمن فقط → اللوحة العامة
    if user.is_superuser:
        return redirect('core:dashboard')

    # 3. صلاحيات المبيعات → لوحة المبيعات
    if user.has_perm('sales.view_salesinvoice'):
        return redirect('sales:dashboard')

    # 4. صلاحيات المشتريات → لوحة المشتريات
    if user.has_perm('purchases.view_purchaseinvoice'):
        return redirect('purchases:dashboard')

    # 5. صلاحيات المخازن → لوحة المخازن
    if user.has_perm('inventory.view_item'):
        return redirect('inventory:dashboard')

    # 6. صلاحيات نقاط البيع → لوحة POS
    if user.has_perm('pos.view_posstation'):
        return redirect('pos:dashboard')

    # 7. صلاحيات الخزينة → لوحة الخزينة
    if user.has_perm('treasury.view_cashbox'):
        return redirect('treasury:dashboard')

    # 8. صلاحيات الموارد البشرية → لوحة HR
    if user.has_perm('hr.view_employee'):
        return redirect('hr:dashboard')

    # 9. صلاحيات الأصول → لوحة الأصول
    if user.has_perm('assets.view_asset'):
        return redirect('assets:dashboard')

    # 10. صلاحيات المصروفات → لوحة المصروفات
    if user.has_perm('expenses.view_expense'):
        return redirect('expenses:dashboard')

    # 11. أي صلاحية تقارير → التقارير المالية
    if user.has_perm('core.view_account'):
        return redirect('reports:financial_dashboard')

    # Fallback
    return redirect('reports:financial_dashboard')


@login_required
@perm_required('core.view_account', raise_exception=True)
def dashboard(request):
    if not request.user.is_superuser:
        # توجيه غير المشرفين (غير السوبر ادمن) لتجنب دخول لوحة الإدارة العامة
        if hasattr(request.user, 'salesrepresentative'):
            return redirect('reports:rep_dashboard')
        elif request.user.has_perm('core.view_account'):
            return redirect('reports:financial_dashboard')
        elif request.user.has_perm('sales.view_salesinvoice'):
            return redirect('sales:dashboard')
        elif request.user.has_perm('purchases.view_purchaseinvoice'):
            return redirect('purchases:dashboard')
        elif request.user.has_perm('inventory.view_item'):
            return redirect('inventory:dashboard')
        elif request.user.has_perm('pos.view_posstation'):
            return redirect('pos:dashboard')
        elif request.user.has_perm('treasury.view_cashbox'):
            return redirect('treasury:dashboard')
        elif request.user.has_perm('hr.view_employee'):
            return redirect('hr:dashboard')
        elif request.user.has_perm('assets.view_asset'):
            return redirect('assets:dashboard')
        elif request.user.has_perm('expenses.view_expense'):
            return redirect('expenses:dashboard')
        else:
            return redirect('reports:financial_dashboard')
        
    today = timezone.now().date()
    first_day_of_month = today.replace(day=1)
    
    # ==========================
    # 1. Sales & Purchases (MTD)
    # ==========================
    mtd_sales = SalesInvoice.objects.filter(
        date__gte=first_day_of_month, status='posted'
    ).aggregate(total=Sum('total'))['total'] or Decimal('0')
    
    mtd_purchases = PurchaseInvoice.objects.filter(
        date__gte=first_day_of_month, status='posted'
    ).aggregate(total=Sum('total'))['total'] or Decimal('0')
    
    # ==========================
    # 2. Finance & Treasury
    # ==========================
    clear_balance_cache()
    all_bals = compute_account_balances()

    def get_parent_balance(parent_code):
        try:
            parent = Account.objects.get(code=parent_code)
        except Account.DoesNotExist:
            return Decimal(0)
        return all_bals.get(parent.pk, Decimal(0))

    # Total Cash & Bank Liquidity
    total_cash = get_parent_balance(getattr(settings, 'CASH_PARENT_ACCOUNT', '1111'))
    total_bank = get_parent_balance(getattr(settings, 'BANK_PARENT_ACCOUNT', '1112'))
    total_liquidity = total_cash + total_bank
    
    # Receivables (What customers owe us) & Payables (What we owe suppliers)
    total_receivables = get_parent_balance(getattr(settings, 'CUSTOMERS_PARENT_ACCOUNT', '1121'))
    total_payables = get_parent_balance(getattr(settings, 'SUPPLIERS_PARENT_ACCOUNT', '2111')) * Decimal('-1')

    # ==========================
    # 3. Inventory KPIs
    # ==========================
    # Total Inventory Value (Current Cost)
    inventory_value = ItemLedger.objects.aggregate(total=Sum('total_value'))['total'] or Decimal('0')
    
    low_stock = ItemLedger.objects.values('item__name', 'item__minimum_stock').annotate(
        total_qty=Sum('quantity_on_hand')
    ).filter(total_qty__lt=F('item__minimum_stock'))[:5]
    low_stock_count = low_stock.count()

    # ==========================
    # 4. HR KPIs
    # ==========================
    active_employees = Employee.objects.filter(status='active').count()
    payroll_load = Employee.objects.filter(status='active').aggregate(total=Sum('basic_salary'))['total'] or Decimal('0')
    
    context = {
        # Financials
        'total_liquidity': total_liquidity,
        'total_receivables': total_receivables,
        'total_payables': total_payables,
        # Sales & Purchases
        'mtd_sales': mtd_sales,
        'mtd_purchases': mtd_purchases,
        # Inventory
        'inventory_value': inventory_value,
        'low_stock': low_stock,
        'low_stock_count': low_stock_count,
        # HR
        'active_employees': active_employees,
        'payroll_load': payroll_load,
        # General Logs
        'recent_entries': JournalEntry.objects.order_by('-id')[:5],
        'recent_logs': AuditLog.objects.select_related('user', 'content_type').order_by('-timestamp')[:5],
    }
    return render(request, 'core/dashboard.html', context)


@login_required
def notification_read(request, pk):
    notification = get_object_or_404(SystemNotification, pk=pk, recipient=request.user)
    notification.is_read = True
    notification.save(update_fields=['is_read'])
    
    if notification.url:
        return redirect(notification.url)
    return redirect('core:dashboard')


@login_required
def notification_mark_read(request, pk):
    notification = get_object_or_404(SystemNotification, pk=pk, recipient=request.user)
    notification.is_read = True
    notification.save(update_fields=['is_read'])
    return redirect('core:notification-list')


class NotificationListView(LoginRequiredMixin, ListView):
    model = SystemNotification
    template_name = 'core/notifications/list.html'
    context_object_name = 'notifications'
    paginate_by = 20

    def get_queryset(self):
        return SystemNotification.objects.filter(recipient=self.request.user).order_by('-created_at')


@login_required
@require_POST
def mark_all_notifications_read(request):
    SystemNotification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    messages.success(request, "تم تحديد جميع الإشعارات كمقروءة بنجاح.")
    return redirect('core:notification-list')

@login_required
@require_POST
def delete_all_notifications(request):
    count, _ = SystemNotification.objects.filter(recipient=request.user).delete()
    if count > 0:
        messages.success(request, f"تم مسح {count} إشعار بنجاح.")
    else:
        messages.info(request, "لا توجد إشعارات لمسحها.")
    return redirect('core:notification-list')

@login_required
@require_POST
def delete_notification(request, pk):
    notification = get_object_or_404(SystemNotification, pk=pk, recipient=request.user)
    notification.delete()
    messages.success(request, "تم مسح الإشعار بنجاح.")
    return redirect('core:notification-list')
