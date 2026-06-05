import json
import logging
from decimal import Decimal
import decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from apps.core.mixins import perm_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Sum, Prefetch, Q
from apps.inventory.models import Item, ItemCategory
from .models import POSStation, POSSession, POSOrder, POSPayment
from .services import POSSessionService, POSCheckoutService
from .forms import POSStationForm
from apps.core.models import SystemNotification
from django.urls import reverse

logger = logging.getLogger(__name__)

@login_required
@perm_required('pos.view_possession', raise_exception=True)
def pos_dashboard(request):
    active_session = POSSessionService.get_active_session(request.user)
    
    stations = []
    if not active_session:
        stations = POSStation.objects.filter(is_active=True)
        
    categories = ItemCategory.objects.all()

    search = request.GET.get('search', '')
    items = Item.objects.filter(is_active=True).select_related(
        'category', 'base_unit', 'sales_unit'
    ).order_by('name')
    if search:
        items = items.filter(Q(name__icontains=search) | Q(code__icontains=search) | Q(barcode__icontains=search))
    items = items[:500]

    items_list = []
    for item in items:
        items_list.append({
            'id': item.id,
            'name': item.name,
            'code': item.code,
            'barcode': item.barcode or '',
            'price': str(item.standard_price) if item.standard_price else '0',
            'category_id': item.category_id if item.category else None,
            'category_name': item.category.name if item.category else 'عام',
            'unit_name': item.base_unit.name if item.base_unit else 'حبة',
            'base_unit_id': item.base_unit.id if item.base_unit else None,
            'base_unit_name': item.base_unit.name if item.base_unit else 'حبة',
            'sales_unit_id': item.sales_unit.id if item.sales_unit else None,
            'sales_unit_name': item.sales_unit.name if item.sales_unit else '',
            'conversion_factor': str(item.conversion_factor) if item.conversion_factor else '1',
        })
        
    context = {
        'active_session': active_session,
        'stations': stations,
        'categories': categories,
        'items_json': items_list,
    }
    
    return render(request, 'pos/dashboard.html', context)

@login_required
@perm_required('pos.add_possession', raise_exception=True)
@require_POST
def open_session(request):
    station_id = request.POST.get('station')
    opening_cash = request.POST.get('opening_cash', 0)
    
    try:
        station = POSStation.objects.get(id=station_id, is_active=True)
        POSSessionService.open_session(request.user, station, opening_cash)
        messages.success(request, 'تم فتح الوردية بنجاح.')
        return redirect('pos:dashboard')
    except POSStation.DoesNotExist:
        messages.error(request, 'نقطة البيع المحددة غير موجودة أو غير نشطة.')
    except ValueError as e:
        logger.warning('ValueError opening session: %s', e)
        messages.error(request, str(e))
    except Exception as e:
        logger.exception('Error opening session')
        messages.error(request, f'حدث خطأ أثناء فتح الوردية: {str(e)}')
    return redirect('pos:dashboard')

@login_required
@perm_required('pos.add_posorder', raise_exception=True)
@require_POST
def checkout(request):
    active_session = POSSessionService.get_active_session(request.user)
    if not active_session:
        return JsonResponse({'success': False, 'message': 'لا توجد جلسة عمل مفتوحة حالياً. قد تم إغلاقها من الإدارة.', 'session_closed': True}, status=400)
        
    try:
        data = json.loads(request.body)
        cart = data.get('cart', [])
        payment_method = data.get('payment_method', 'cash')
        customer_id = data.get('customer_id')
        is_taxable = data.get('is_taxable', True)
        payment_reference = data.get('payment_reference', '')
        
        order = POSCheckoutService.create_order(
            session=active_session,
            cart_items=cart,
            payment_method=payment_method,
            customer_id=customer_id,
            is_taxable=is_taxable,
            payment_reference=payment_reference
        )
        
        lines_data = []
        for line in order.lines.select_related('item').all():
            lines_data.append({
                'name': line.item.name,
                'qty': float(line.qty),
                'price': float(line.price),
                'total': float(line.total),
            })

        warnings = getattr(active_session, '_cost_warnings', [])

        return JsonResponse({
            'success': True,
            'message': 'تم حفظ ودفع الفاتورة بنجاح وصرف المخزون.',
            'receipt_number': order.receipt_number,
            'grand_total': float(order.grand_total),
            'subtotal': float(order.subtotal),
            'tax': float(order.tax),
            'lines': lines_data,
            'warnings': warnings,
        })
    except Exception as e:
        logger.exception('Error during checkout')
        return JsonResponse({'success': False, 'message': str(e)}, status=400)

@login_required
@perm_required('pos.change_posorder', raise_exception=True)
@require_POST
def cancel_order(request, pk):
    order = get_object_or_404(POSOrder, pk=pk)
    try:
        POSCheckoutService.cancel_order(order, request.user)
        SystemNotification.notify_accountants(
            title="إلغاء فاتورة POS",
            message=f"قام {request.user.username} بإلغاء فاتورة النقدي رقم {order.receipt_number} بقيمة {order.grand_total:.2f} ج.م من وردية #{order.session_id}.",
            url=reverse('pos:session-orders', args=[order.session_id]),
        )
        messages.success(request, f'تم إلغاء الفاتورة {order.receipt_number} بنجاح.')
    except Exception as e:
        logger.exception('Error cancelling order %s', order.receipt_number)
        messages.error(request, str(e))
    return redirect('pos:session-orders', pk=order.session_id)

@login_required
@perm_required('pos.change_posorder', raise_exception=True)
def return_order_items(request, pk):
    order = get_object_or_404(POSOrder.objects.prefetch_related('lines__item'), pk=pk)
    if order.status not in [POSOrder.Status.PAID, POSOrder.Status.POSTED]:
        messages.error(request, "يمكن فقط إرجاع أصناف من الفواتير المدفوعة أو المرحّلة.")
        return redirect('pos:session-orders', pk=order.session_id)

    if request.method == 'POST':
        try:
            items_data = []
            for key, val in request.POST.items():
                if key.startswith('return_qty_'):
                    line_id = int(key.split('_')[2])
                    qty = val.strip()
                    if qty and Decimal(qty) > 0:
                        items_data.append({'line_id': line_id, 'qty': qty})
            if not items_data:
                messages.warning(request, "لم يتم تحديد أي أصناف للإرجاع.")
                return redirect('pos:session-orders', pk=order.session_id)
            total_refund = POSCheckoutService.return_items(order, items_data, request.user)
            # Custom notification logic for closed sessions
            if order.session.status != 'open':
                notif_title = "⚠️ تنبيه: مرتجع من وردية مغلقة"
                notif_msg = f"تحذير: قام {request.user.username} بعمل مرتجع جزئي بقيمة {total_refund:.2f} ج.م للفاتورة رقم {order.receipt_number} التابعة لوردية مغلقة (#{order.session_id})."
            else:
                notif_title = "مرتجع POS جزئي"
                notif_msg = f"قام {request.user.username} بعمل مرتجع جزئي من الفاتورة رقم {order.receipt_number} بقيمة {total_refund:.2f} ج.م في ورديته الحالية."

            SystemNotification.notify_accountants(
                title=notif_title,
                message=notif_msg,
                url=reverse('pos:session-orders', args=[order.session_id]),
            )
            messages.success(request, f'تم إرجاع الأصناف بنجاح. المبلغ المسترد: {total_refund} EGP')
        except Exception as e:
            logger.exception('Error returning items from order %s', order.receipt_number)
            messages.error(request, str(e))
        return redirect('pos:session-orders', pk=order.session_id)

    return render(request, 'pos/order_return.html', {'order': order})

@login_required
@perm_required('pos.change_possession', raise_exception=True)
@require_POST
def close_session(request):
    active_session = POSSessionService.get_active_session(request.user)
    if not active_session:
        return JsonResponse({'success': False, 'message': 'لا توجد جلسة عمل مفتوحة لإغلاقها.'}, status=400)
        
    try:
        data = json.loads(request.body)
        try:
            actual_cash = Decimal(str(data.get('actual_cash', 0)))
        except (ValueError, TypeError, decimal.InvalidOperation):
            return JsonResponse({'success': False, 'message': 'قيمة النقدية الفعلية غير صحيحة.'}, status=400)
        notes = data.get('notes', '')
        
        POSSessionService.close_session(active_session, actual_cash, notes)
        
        # Refresh to get computed fields (difference)
        active_session.refresh_from_db()
        if active_session.difference != 0:
            diff_type = "عجز" if active_session.difference < 0 else "زيادة"
            SystemNotification.notify_accountants(
                title=f"{diff_type} في وردية POS",
                message=f"تم إغلاق وردية #{active_session.id} للكاشير {active_session.user.username} ب{diff_type} قيمته {abs(active_session.difference):.2f} ج.م (المتوقع: {active_session.expected_cash:.2f}، الفعلي: {active_session.actual_cash:.2f}).",
                url=reverse('pos:session-list'),
            )
        
        return JsonResponse({
            'success': True,
            'message': 'تم إغلاق الوردية بنجاح وترحيل القيود المحاسبية للمبيعات وتوليد تسوية الخزنة.'
        })
    except Exception as e:
        logger.exception('Error closing session')
        return JsonResponse({'success': False, 'message': str(e)}, status=400)

@login_required
@perm_required('pos.view_posstation', raise_exception=True)
def station_list(request):
    stations = POSStation.objects.all().select_related('warehouse', 'cash_box', 'bank_account', 'mobile_wallet')
    return render(request, 'pos/station_list.html', {'stations': stations})

@login_required
@perm_required('pos.add_posstation', raise_exception=True)
def station_create(request):
    if request.method == 'POST':
        form = POSStationForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم إضافة نقطة البيع بنجاح.')
            return redirect('pos:station-list')
    else:
        form = POSStationForm(user=request.user)
    return render(request, 'pos/station_form.html', {'form': form, 'title': 'إضافة نقطة بيع جديدة'})

@login_required
@perm_required('pos.change_posstation', raise_exception=True)
def station_update(request, pk):
    station = get_object_or_404(POSStation, pk=pk)
    if request.method == 'POST':
        form = POSStationForm(request.POST, instance=station, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم تحديث نقطة البيع بنجاح.')
            return redirect('pos:station-list')
    else:
        form = POSStationForm(instance=station, user=request.user)
    return render(request, 'pos/station_form.html', {'form': form, 'title': f'تعديل نقطة البيع: {station.name}'})

@login_required
@perm_required('pos.delete_posstation', raise_exception=True)
def station_delete(request, pk):
    station = get_object_or_404(POSStation, pk=pk)
    if request.method == 'POST':
        if station.sessions.exists():
            messages.error(request, 'لا يمكن حذف نقطة البيع لوجود ورديات عمل مسجلة عليها. قم بتعطيلها بدلاً من ذلك.')
            return redirect('pos:station-list')
        station.delete()
        messages.success(request, 'تم حذف نقطة البيع بنجاح.')
        return redirect('pos:station-list')
    return render(request, 'pos/station_confirm_delete.html', {'station': station})

@login_required
@perm_required('pos.view_possession', raise_exception=True)
def session_list(request):
    orders_qs = POSOrder.objects.filter(status__in=[POSOrder.Status.PAID, POSOrder.Status.POSTED]).prefetch_related(
        Prefetch('payments', queryset=POSPayment.objects.all())
    )
    sessions = POSSession.objects.all().select_related('station', 'user').prefetch_related(
        Prefetch('orders', queryset=orders_qs)
    ).order_by('-start_time')
    
    paginator = Paginator(sessions, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    sessions_data = []
    for s in page_obj:
        orders = list(s.orders.all())
        total_sales = sum(o.grand_total for o in orders) if orders else Decimal('0')
        payments = [p for o in orders for p in o.payments.all()]
        total_cash = sum(p.amount for p in payments if p.method == 'cash')
        total_card = sum(p.amount for p in payments if p.method == 'card')
        total_wallet = sum(p.amount for p in payments if p.method == 'wallet')
        
        sessions_data.append({
            'session': s,
            'total_sales': total_sales,
            'total_cash': total_cash,
            'total_card': total_card,
            'total_wallet': total_wallet,
        })
        
    return render(request, 'pos/session_list.html', {
        'sessions_data': sessions_data,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
    })


@login_required
@perm_required('pos.view_possession', raise_exception=True)
def session_orders(request, pk):
    session = get_object_or_404(POSSession, pk=pk)
    orders = session.orders.all().select_related('customer').prefetch_related('payments').order_by('-date')
    
    paginator = Paginator(orders, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'pos/session_orders.html', {
        'session': session,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
    })


@login_required
@perm_required('pos.view_posorder', raise_exception=True)
def order_detail(request, pk):
    order = get_object_or_404(POSOrder.objects.prefetch_related('lines__item', 'payments'), pk=pk)
    return render(request, 'pos/order_detail.html', {'order': order})


@login_required
@perm_required('pos.change_possession', raise_exception=True)
@require_POST
def collect_shortage(request, pk):
    """تحصيل العجز النقدي من كاشير بعد إغلاق الوردية"""
    session = get_object_or_404(POSSession, pk=pk)
    try:
        POSSessionService.collect_shortage(session, request.user)
        SystemNotification.notify_accountants(
            title="تحصيل عجز وردية POS",
            message=f"قام {request.user.username} بتحصيل عجز بقيمة {abs(session.difference):.2f} جنيه من وردية الكاشير رقم {session.id} ({session.user.username}).",
            url=reverse('pos:session-list'),
        )
        messages.success(request, f'تم تحصيل العجز بقيمة {abs(session.difference):.2f} جنيه للوردية رقم {session.id}.')
    except ValueError as e:
        logger.warning('ValueError collecting shortage: %s', e)
        messages.error(request, str(e))
    except Exception as e:
        logger.exception('Error collecting shortage')
        messages.error(request, f'حدث خطأ أثناء تحصيل العجز: {str(e)}')
    
    return redirect('pos:session-list')
