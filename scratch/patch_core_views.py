import re

def main():
    # 1. taxes.py
    file_path = 'apps/core/views/taxes.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    old_dispatch = """    def dispatch(self, request, *args, **kwargs):
        self.kwargs = kwargs
        self.args = args
        obj = self.get_object()
        
        # Check if in use
        in_use = (
            SalesInvoiceLine.objects.filter(Q(tax_type=obj) | Q(tax_type2=obj)).exists() or
            SalesReturnLine.objects.filter(Q(tax_type=obj) | Q(tax_type2=obj)).exists() or
            PurchaseInvoiceLine.objects.filter(Q(tax_type=obj) | Q(tax_type2=obj)).exists() or
            PurchaseReturnLine.objects.filter(Q(tax_type=obj) | Q(tax_type2=obj)).exists() or
            Expense.objects.filter(Q(tax_type=obj) | Q(tax_type2=obj)).exists()
        )
        
        if in_use:
            messages.error(self.request, f'لا يمكن تعديل الضريبة "{obj.name}" لأنها مستخدمة في فواتير سابقة. قم بإنشاء ضريبة جديدة بدلاً من ذلك.')
            return redirect('core:taxtype-list')
            
        return super().dispatch(request, *args, **kwargs)"""
        
    new_get_post = """    def _is_in_use(self, obj):
        return (
            SalesInvoiceLine.objects.filter(Q(tax_type=obj) | Q(tax_type2=obj)).exists() or
            SalesReturnLine.objects.filter(Q(tax_type=obj) | Q(tax_type2=obj)).exists() or
            PurchaseInvoiceLine.objects.filter(Q(tax_type=obj) | Q(tax_type2=obj)).exists() or
            PurchaseReturnLine.objects.filter(Q(tax_type=obj) | Q(tax_type2=obj)).exists() or
            Expense.objects.filter(Q(tax_type=obj) | Q(tax_type2=obj)).exists()
        )

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self._is_in_use(self.object):
            messages.error(self.request, f'لا يمكن تعديل الضريبة "{self.object.name}" لأنها مستخدمة في فواتير سابقة. قم بإنشاء ضريبة جديدة بدلاً من ذلك.')
            return redirect('core:taxtype-list')
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self._is_in_use(self.object):
            messages.error(self.request, f'لا يمكن تعديل الضريبة "{self.object.name}" لأنها مستخدمة في فواتير سابقة. قم بإنشاء ضريبة جديدة بدلاً من ذلك.')
            return redirect('core:taxtype-list')
        return super().post(request, *args, **kwargs)"""
    
    content = content.replace(old_dispatch, new_get_post)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Taxes views updated successfully.")

    # 2. journal.py
    file_path2 = 'apps/core/views/journal.py'
    try:
        with open(file_path2, 'r', encoding='utf-8') as f:
            content2 = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return
        
    old_post = """    def post(self, request, pk):
        entry = get_object_or_404(JournalEntry, pk=pk)
        if entry.is_posted:
            messages.error(request, "هذا القيد مرحل بالفعل.")
        else:
            entry.is_posted = True"""
    new_post = """    def post(self, request, pk):
        entry = get_object_or_404(JournalEntry, pk=pk)
        if entry.is_posted:
            messages.error(request, "هذا القيد مرحل بالفعل.")
        elif entry.fiscal_year and entry.fiscal_year.is_closed:
            messages.error(request, "لا يمكن ترحيل قيد في سنة مالية مقفلة.")
        else:
            total_debit = sum(line.debit for line in entry.lines.all())
            total_credit = sum(line.credit for line in entry.lines.all())
            if total_debit != total_credit:
                messages.error(request, f"القيد غير متزن. إجمالي المدين: {total_debit}، إجمالي الدائن: {total_credit}")
                return redirect('core:journal-detail', pk=pk)
                
            entry.is_posted = True"""
    content2 = content2.replace(old_post, new_post)
    with open(file_path2, 'w', encoding='utf-8') as f:
        f.write(content2)
    print("Journal views updated successfully.")

    # 3. general.py
    file_path3 = 'apps/core/views/general.py'
    try:
        with open(file_path3, 'r', encoding='utf-8') as f:
            content3 = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    content3 = content3.replace('from django.contrib.auth.decorators import login_required', 'from django.contrib.auth.decorators import login_required\nfrom django.views.decorators.http import require_POST')
    
    old_notify = """@login_required
def mark_all_notifications_read(request):"""
    new_notify = """@login_required
@require_POST
def mark_all_notifications_read(request):"""
    content3 = content3.replace(old_notify, new_notify)
    with open(file_path3, 'w', encoding='utf-8') as f:
        f.write(content3)
    print("General views updated successfully.")

if __name__ == '__main__':
    main()
