from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from apps.sales.models import SalesInvoice, Customer
from apps.purchases.models import PurchaseInvoice
from apps.inventory.models import Item, ItemLedger
from apps.core.models import JournalEntry, AuditLog, Account, JournalLine
from django.utils import timezone
from django.db.models import Sum, Q, F
from decimal import Decimal
from django.conf import settings

@login_required
def dashboard(request):
    today = timezone.now().date()
    
    # 1. Today's Sales
    today_sales = SalesInvoice.objects.filter(
        date=today, status='posted'
    ).aggregate(total=Sum('total'))['total'] or Decimal('0')
    
    # 2. Total Cash (Sum of balances of all CashBox accounts)
    cash_parent = getattr(settings, 'CASH_PARENT_ACCOUNT', '1111')
    cash_accounts = Account.objects.filter(parent__code=cash_parent, is_leaf=True)
    
    # Identify which of these cash accounts already have an opening journal entry
    accounts_with_opening = set(JournalLine.objects.filter(
        account__in=cash_accounts,
        entry__entry_type=JournalEntry.EntryType.OPENING,
        entry__is_posted=True
    ).values_list('account_id', flat=True))

    total_cash = Decimal('0')
    for acc in cash_accounts:
        stats = JournalLine.objects.filter(
            account=acc, entry__is_posted=True
        ).aggregate(d=Sum('debit'), c=Sum('credit'))
        
        debit = stats['d'] or Decimal('0')
        credit = stats['c'] or Decimal('0')
        
        if acc.id not in accounts_with_opening:
            if acc.initial_balance_type == 'debit':
                debit += acc.initial_balance
            else:
                credit += acc.initial_balance
        
        total_cash += (debit - credit)
    
    # 3. Low Stock Items (Quantity < item.minimum_stock)
    low_stock = ItemLedger.objects.values('item__name', 'item__minimum_stock').annotate(
        total_qty=Sum('quantity_on_hand')
    ).filter(total_qty__lt=F('item__minimum_stock'))[:5]
    
    context = {
        'total_sales': SalesInvoice.objects.filter(status='posted').count(),
        'today_sales_amount': today_sales,
        'total_cash': total_cash,
        'total_purchases': PurchaseInvoice.objects.count(),
        'total_customers': Customer.objects.count(),
        'total_items': Item.objects.count(),
        'recent_entries': JournalEntry.objects.order_by('-id')[:5],
        'recent_logs': AuditLog.objects.select_related('user', 'content_type').order_by('-timestamp')[:5],
        'low_stock': low_stock,
    }
    return render(request, 'core/dashboard.html', context)
