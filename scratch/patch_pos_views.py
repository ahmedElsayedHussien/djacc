import re

def main():
    file_path = 'apps/pos/views.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    # open_session try/except
    old_open = """def open_session(request):
    if request.method == 'POST':
        station_id = request.POST.get('station')
        opening_cash = request.POST.get('opening_cash', 0)
        station = get_object_or_404(POSStation, pk=station_id)"""
    new_open = """def open_session(request):
    if request.method == 'POST':
        station_id = request.POST.get('station')
        if not station_id:
            messages.error(request, 'الرجاء اختيار نقطة البيع.')
            return redirect('pos:dashboard')
        try:
            opening_cash = Decimal(str(request.POST.get('opening_cash', 0)))
        except (ValueError, decimal.InvalidOperation, TypeError):
            messages.error(request, 'العهدة الافتتاحية غير صحيحة.')
            return redirect('pos:dashboard')
        station = get_object_or_404(POSStation, pk=station_id)"""
    content = content.replace(old_open, new_open)
    if 'import decimal' not in content:
        content = content.replace("from decimal import Decimal", "from decimal import Decimal\nimport decimal")

    # checkout payment method
    old_checkout = """    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            cart_items = data.get('cart', [])
            payment_method = data.get('payment_method', 'cash')
            customer_id = data.get('customer_id')"""
    new_checkout = """    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            cart_items = data.get('cart', [])
            payment_method = data.get('payment_method', 'cash')
            if payment_method not in ['cash', 'card', 'wallet']:
                return JsonResponse({'success': False, 'message': 'طريقة الدفع غير صالحة.'}, status=400)
            customer_id = data.get('customer_id') or None"""
    content = content.replace(old_checkout, new_checkout)

    # cancel_order ownership
    old_cancel = """def cancel_order(request, pk):
    order = get_object_or_404(POSOrder, pk=pk)
    if order.status != POSOrder.Status.DRAFT:"""
    new_cancel = """def cancel_order(request, pk):
    order = get_object_or_404(POSOrder, pk=pk)
    active_session = POSSessionService.get_active_session(request.user)
    if not active_session or order.session_id != active_session.id:
        return JsonResponse({'success': False, 'message': 'لا يمكنك إلغاء فاتورة من وردية أخرى.'}, status=403)
    if order.status != POSOrder.Status.DRAFT:"""
    content = content.replace(old_cancel, new_cancel)

    # return_order_items ownership and try/except
    old_return = """def return_order_items(request, pk):
    order = get_object_or_404(POSOrder, pk=pk)

    if request.method == 'POST':
        try:
            items_data = []
            for key, val in request.POST.items():
                if key.startswith('return_qty_'):
                    line_id = int(key.split('_')[2])
                    qty = val.strip()
                    if qty and Decimal(qty) > 0:
                        items_data.append({'line_id': line_id, 'qty': Decimal(qty)})"""
    new_return = """def return_order_items(request, pk):
    order = get_object_or_404(POSOrder, pk=pk)
    active_session = POSSessionService.get_active_session(request.user)
    if not active_session or order.session_id != active_session.id:
        messages.error(request, 'لا يمكنك إرجاع فاتورة من وردية أخرى.')
        return redirect('pos:session-list')

    if request.method == 'POST':
        try:
            items_data = []
            for key, val in request.POST.items():
                if key.startswith('return_qty_'):
                    try:
                        line_id = int(key.split('_')[2])
                        qty_str = val.strip()
                        if qty_str:
                            qty = Decimal(qty_str)
                            if qty > 0:
                                items_data.append({'line_id': line_id, 'qty': qty})
                    except (ValueError, TypeError, decimal.InvalidOperation, IndexError):
                        messages.error(request, 'بيانات الإرجاع غير صحيحة.')
                        return redirect('pos:session-list')"""
    content = content.replace(old_return, new_return)

    # close_session try/except
    old_close = """        data = json.loads(request.body)
        actual_cash = data.get('actual_cash', 0)"""
    new_close = """        data = json.loads(request.body)
        try:
            actual_cash = Decimal(str(data.get('actual_cash', 0)))
        except (ValueError, TypeError, decimal.InvalidOperation):
            return JsonResponse({'success': False, 'message': 'قيمة النقدية الفعلية غير صحيحة.'}, status=400)"""
    content = content.replace(old_close, new_close)

    # session_list filter
    old_list = """    orders_qs = POSOrder.objects.filter(status=POSOrder.Status.PAID).prefetch_related(
        'payments'
    )"""
    new_list = """    orders_qs = POSOrder.objects.filter(status__in=[POSOrder.Status.PAID, POSOrder.Status.POSTED]).prefetch_related(
        'payments'
    )"""
    content = content.replace(old_list, new_list)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Views patched.")

if __name__ == '__main__':
    main()
