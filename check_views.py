import django, os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.base'
django.setup()

print('=== MISSING VIEWS/TEMPLATES ANALYSIS ===')
print()

from apps.purchases import views as pv
from apps.expenses import views as ev
from apps.treasury import views as tv
from apps.inventory import views as iv
from apps.sales import views as sv

checks = [
    ('PurchaseInvoice DetailView', hasattr(pv, 'PurchaseInvoiceDetailView')),
    ('PurchaseInvoice PostView', hasattr(pv, 'PurchaseInvoicePostView')),
    ('SupplierPayment DetailView', hasattr(pv, 'SupplierPaymentDetailView')),
    ('Expense PostView', hasattr(ev, 'ExpensePostView')),
    ('CashTransfer DetailView', hasattr(tv, 'CashTransferDetailView')),
    ('BankAccount DetailView', hasattr(tv, 'BankAccountDetailView')),
    ('CashBox DetailView', hasattr(tv, 'CashBoxDetailView')),
    ('Item DetailView', hasattr(iv, 'ItemDetailView')),
    ('CustomerReceipt DetailView', hasattr(sv, 'CustomerReceiptDetailView')),
    ('RepReceivableCollect form template', os.path.exists('e:/djacc/templates/sales/reps/collect_form.html')),
]

missing = []
for name, exists in checks:
    status = 'EXISTS' if exists else 'MISSING!'
    print(f'  {name}: {status}')
    if not exists:
        missing.append(name)

print()

# Also check for URLs that reference invoice-detail/post for purchases
from apps.purchases.urls import urlpatterns as purch_urls
print('=== Purchases URL patterns ===')
for u in purch_urls:
    print(f'  {u.pattern} -> {u.name}')

print()
# Check for missing PurchaseReturn form
has_form = hasattr(pv, 'PurchaseReturnForm')
print(f'PurchaseReturn Form class: {"EXISTS" if has_form else "uses inline formset likely"}')

# Check forms
from apps.purchases import forms as pf
has_pr_form = hasattr(pf, 'PurchaseReturnForm')
print(f'PurchaseReturnForm in forms.py: {"EXISTS" if has_pr_form else "MISSING!"}')
if not has_pr_form:
    missing.append('PurchaseReturnForm')

# Check for invoice detail/post in purchases URLs
has_inv_detail_url = any(u.name == 'invoice-detail' for u in purch_urls)
has_inv_post_url = any(u.name == 'invoice-post' for u in purch_urls)
print(f'Purchase invoice-detail URL: {"EXISTS" if has_inv_detail_url else "MISSING!"}')
print(f'Purchase invoice-post URL: {"EXISTS" if has_inv_post_url else "MISSING!"}')
if not has_inv_detail_url: missing.append('Purchase invoice-detail URL')
if not has_inv_post_url: missing.append('Purchase invoice-post URL')

print()
print(f'=== TOTAL MISSING: {len(missing)} ===')
for m in missing:
    print(f'  - {m}')
