"""
Diagnostic script to compare sales figures between Dashboard and Net Sales Report.
Run: python manage.py shell < scratch/diagnose_sales_diff.py
"""
from decimal import Decimal
from django.db.models import Sum, F
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.sales.models import SalesInvoice, SalesInvoiceLine, SalesReturn

today = timezone.now().date()
first_day = today.replace(day=1)

print("=" * 70)
print(f"  تشخيص الفرق في المبيعات")
print(f"  الفترة: {first_day} → {today}")
print("=" * 70)

# ============================
# 1. Dashboard Calculation (core/views/general.py)
# ============================
dash_data = SalesInvoice.objects.filter(
    date__gte=first_day, status='posted'
).aggregate(
    gross=Sum('subtotal'),
    discount=Sum('discount_amount'),
    total_field=Sum('total'),
    tax=Sum('tax_amount'),
    count=Sum(Decimal('1'))  
)
dash_returns = SalesReturn.objects.filter(
    date__gte=first_day, status='posted'
).aggregate(
    returns_sub=Sum('subtotal'),
    returns_total=Sum('total'),
    count=Sum(Decimal('1'))
)

dash_gross = dash_data['gross'] or Decimal('0')
dash_discount = dash_data['discount'] or Decimal('0')
dash_returns_sub = dash_returns['returns_sub'] or Decimal('0')
dash_mtd = dash_gross - dash_discount - dash_returns_sub

print("\n[1] حساب لوحة الإدارة (Core Dashboard - mtd_sales)")
print(f"    Filter: date__gte={first_day}, status='posted'")
print(f"    عدد الفواتير: {dash_data['count'] or 0}")
print(f"    Sum(subtotal)      = {dash_gross}")
print(f"    Sum(discount)      = {dash_discount}")
print(f"    Sum(tax)           = {dash_data['tax'] or Decimal('0')}")
print(f"    Sum(total)         = {dash_data['total_field'] or Decimal('0')}")
print(f"    ---")
print(f"    عدد المرتجعات: {dash_returns['count'] or 0}")
print(f"    Sum(returns.sub)   = {dash_returns_sub}")
print(f"    Sum(returns.total) = {dash_returns['returns_total'] or Decimal('0')}")
print(f"    ===")
print(f"    mtd_sales = subtotal - discount - returns.subtotal")
print(f"    mtd_sales = {dash_gross} - {dash_discount} - {dash_returns_sub} = {dash_mtd}")

# ============================
# 2. Sales Dashboard Calculation (sales/report_views.py - SalesDashboardView)
# ============================
sales_dash_inv = SalesInvoice.objects.filter(
    status=SalesInvoice.Status.POSTED,
    date__gte=first_day
).aggregate(
    subtotal=Coalesce(Sum('subtotal'), Decimal('0')),
    discount=Coalesce(Sum('discount_amount'), Decimal('0'))
)
sales_dash_ret = SalesReturn.objects.filter(
    status=SalesReturn.Status.POSTED,
    date__gte=first_day
).aggregate(
    subtotal=Coalesce(Sum('subtotal'), Decimal('0'))
)
sales_dash_month = sales_dash_inv['subtotal'] - sales_dash_inv['discount'] - sales_dash_ret['subtotal']

print(f"\n[2] حساب لوحة المبيعات (Sales Dashboard - total_sales_month)")
print(f"    Filter: status=POSTED, date__gte={first_day}")
print(f"    subtotal  = {sales_dash_inv['subtotal']}")
print(f"    discount  = {sales_dash_inv['discount']}")
print(f"    returns   = {sales_dash_ret['subtotal']}")
print(f"    total_sales_month = {sales_dash_month}")

# ============================
# 3. Net Sales Profitability Report (reports/services.py)
# ============================
report_data = SalesInvoice.objects.filter(
    status=SalesInvoice.Status.POSTED,
    date__range=[first_day, today]
).aggregate(
    gross_sales=Sum('subtotal'),
    total_discounts=Sum('discount_amount')
)
report_returns = SalesReturn.objects.filter(
    status=SalesReturn.Status.POSTED,
    date__range=[first_day, today]
).aggregate(
    total_returns=Sum('subtotal')
)

rpt_gross = report_data['gross_sales'] or Decimal('0')
rpt_disc = report_data['total_discounts'] or Decimal('0')
rpt_ret = report_returns['total_returns'] or Decimal('0')
rpt_net = rpt_gross - rpt_disc - rpt_ret

# COGS
cogs = SalesInvoiceLine.objects.filter(
    invoice__status=SalesInvoice.Status.POSTED,
    invoice__date__range=[first_day, today]
).aggregate(
    total_cogs=Sum(F('quantity') * F('cost'))
)['total_cogs'] or Decimal('0')

gross_profit = rpt_net - cogs

print(f"\n[3] تقرير صافي المبيعات والربحية (Net Sales Report)")
print(f"    Filter: status=POSTED, date__range=[{first_day}, {today}]")
print(f"    gross_sales (subtotal)  = {rpt_gross}")
print(f"    total_discounts         = {rpt_disc}")
print(f"    total_returns           = {rpt_ret}")
print(f"    net_sales               = {rpt_net}")
print(f"    COGS                    = {cogs}")
print(f"    gross_profit            = {gross_profit}")

# ============================
# 4. Comparison
# ============================
print("\n" + "=" * 70)
print("  مقارنة النتائج:")
print("=" * 70)
print(f"  لوحة الإدارة (mtd_sales)          = {dash_mtd}")
print(f"  لوحة المبيعات (total_sales_month) = {sales_dash_month}")
print(f"  التقرير (net_sales)               = {rpt_net}")
print(f"  التقرير (gross_sales)             = {rpt_gross}")
print(f"  التقرير (gross_profit)            = {gross_profit}")

if dash_mtd != rpt_net:
    diff = dash_mtd - rpt_net
    print(f"\n  ⚠️ فرق بين اللوحة والتقرير (net_sales): {diff}")
    
    # Check if the dashboard number matches gross_sales
    if dash_mtd == rpt_gross:
        print(f"  → لوحة الإدارة تظهر gross_sales بدلاً من net_sales!")
    elif dash_mtd == gross_profit:
        print(f"  → لوحة الإدارة تظهر gross_profit!")
    
    # Check if difference = discounts
    if diff == rpt_disc:
        print(f"  → الفرق = مقدار الخصومات بالضبط!")
    elif diff == rpt_ret:
        print(f"  → الفرق = مقدار المرتجعات بالضبط!")
    elif diff == (rpt_disc + rpt_ret):
        print(f"  → الفرق = الخصومات + المرتجعات!")
else:
    print(f"\n  ✅ لوحة الإدارة = تقرير صافي المبيعات (متطابقين)")

# Check date filter difference
inv_gte = SalesInvoice.objects.filter(date__gte=first_day, status='posted').count()
inv_range = SalesInvoice.objects.filter(status='posted', date__range=[first_day, today]).count()
if inv_gte != inv_range:
    print(f"\n  ⚠️ عدد الفواتير مختلف!")
    print(f"     date__gte: {inv_gte} فواتير")
    print(f"     date__range: {inv_range} فواتير")
    future = SalesInvoice.objects.filter(date__gt=today, status='posted')
    if future.exists():
        print(f"     يوجد {future.count()} فاتورة بتاريخ مستقبلي!")
        for f in future[:5]:
            print(f"       - {f.number} بتاريخ {f.date}")
