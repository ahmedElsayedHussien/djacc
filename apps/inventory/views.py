import logging

from django.views.generic import ListView, CreateView, UpdateView, DetailView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.core.mixins import PermRequiredMixin
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.db.models import Sum, F, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect
from django.db import transaction
from django.utils import timezone
from django.views import View
from django.http import JsonResponse
from apps.core.services import DocumentService
from apps.core.models import SystemNotification
from apps.sales.models import SalesRepresentative
from .models import (
    Item, ItemCategory, Warehouse, UnitOfMeasure, ItemLedger, WarehouseTransfer,
    LoadingOrder, LoadingOrderLine, StockMovement, StockVoucher, StockVoucherLine,
)
from .forms import (
    ItemForm, ItemCategoryForm, WarehouseForm, WarehouseTransferForm,
    WarehouseTransferLineFormSet, LoadingOrderForm, LoadingOrderLineFormSet,
    UnitOfMeasureForm, StockVoucherForm, StockVoucherLineFormSet,
)
from .services import InventoryService, LoadingService, StockVoucherService
from decimal import Decimal

logger = logging.getLogger(__name__)

class InventoryDashboardView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'inventory/dashboard.html'
    permission_required = 'inventory.view_stockmovement'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # 1. Basic Stats
        ctx['total_items'] = Item.objects.filter(is_active=True).count()
        ctx['total_warehouses'] = Warehouse.objects.filter(is_active=True).count()
        
        inventory_totals = ItemLedger.objects.aggregate(
            total_qty=Sum('quantity_on_hand'),
            total_value=Sum('total_value')
        )
        ctx['total_inventory_qty'] = inventory_totals['total_qty'] or 0
        ctx['total_inventory_value'] = inventory_totals['total_value'] or 0
        
        # 2. Low Stock Alerts (Stock <= Min Stock)
        # We need to join Item with its total stock
        low_stock_items = Item.objects.annotate(
            current_stock=Coalesce(Sum('itemledger__quantity_on_hand'), Decimal('0'))
        ).filter(current_stock__lt=F('minimum_stock'), is_active=True).order_by('current_stock')
        
        low_stock_list = list(low_stock_items)
        ctx['low_stock_items'] = low_stock_list[:10]
        ctx['low_stock_count'] = len(low_stock_list)

        # 3. Recent Movements
        ctx['recent_movements'] = StockMovement.objects.select_related('item', 'warehouse').order_by('-date', '-id')[:10]

        # 4. Warehouse Distribution
        ctx['warehouse_stats'] = Warehouse.objects.annotate(
            total_qty=Sum('itemledger__quantity_on_hand'),
            total_val=Sum('itemledger__total_value')
        ).filter(is_active=True)

        # 5. Pending Tasks
        ctx['pending_loadings'] = LoadingOrder.objects.filter(status=LoadingOrder.Status.PENDING).count()
        ctx['draft_vouchers'] = StockVoucher.objects.filter(status=StockVoucher.Status.DRAFT).count()
        ctx['pending_transfers'] = WarehouseTransfer.objects.filter(status=WarehouseTransfer.Status.DRAFT).count()

        return ctx

class PendingTasksView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'inventory/partials/pending_tasks.html'
    permission_required = 'inventory.view_stockmovement'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['pending_loadings'] = LoadingOrder.objects.filter(status=LoadingOrder.Status.PENDING).count()
        ctx['draft_vouchers'] = StockVoucher.objects.filter(status=StockVoucher.Status.DRAFT).count()
        ctx['pending_transfers'] = WarehouseTransfer.objects.filter(status=WarehouseTransfer.Status.DRAFT).count()
        return ctx


class ItemListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = Item
    template_name = 'inventory/items/list.html'
    context_object_name = 'items'
    permission_required = 'inventory.view_item'
    paginate_by = 30

    def get_queryset(self):
        qs = Item.objects.select_related('category', 'base_unit').filter(is_active=True).order_by('code')
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(name__icontains=q) | qs.filter(code__icontains=q)
        category = self.request.GET.get('category')
        if category:
            qs = qs.filter(category_id=category)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['categories'] = ItemCategory.objects.all()
        return ctx

class ItemCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = Item
    form_class = ItemForm
    template_name = 'inventory/items/form.html'
    permission_required = 'inventory.add_item'

    def get_success_url(self):
        return reverse('inventory:item-detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        form.instance.code = InventoryService.generate_item_code()
        messages.success(self.request, f'تم إضافة الصنف "{form.instance.name}" بنجاح بالكود {form.instance.code}')
        return super().form_valid(form)

class ItemUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):
    model = Item
    form_class = ItemForm
    template_name = 'inventory/items/form.html'
    permission_required = 'inventory.change_item'
    success_url = reverse_lazy('inventory:item-list')

class ItemDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = Item
    template_name = 'inventory/items/detail.html'
    permission_required = 'inventory.view_item'

class WarehouseListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = Warehouse
    template_name = 'inventory/warehouses/list.html'
    permission_required = 'inventory.view_warehouse'
    paginate_by = 25

class WarehouseCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = Warehouse
    form_class = WarehouseForm
    template_name = 'inventory/warehouses/form.html'
    success_url = reverse_lazy('inventory:warehouse-list')
    permission_required = 'inventory.add_warehouse'

class WarehouseToggleActiveView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'inventory.change_warehouse'
    
    def post(self, request, pk):
        warehouse = get_object_or_404(Warehouse, pk=pk)
        warehouse.is_active = not warehouse.is_active
        warehouse.save(update_fields=['is_active'])
        
        status_str = "نشط" if warehouse.is_active else "غير نشط"
        messages.success(request, f'تم تغيير حالة المستودع "{warehouse.name}" إلى {status_str} بنجاح!')
        return redirect('inventory:warehouse-list')

class ItemCategoryListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = ItemCategory
    template_name = 'inventory/categories/list.html'
    permission_required = 'inventory.view_itemcategory'
    paginate_by = 25

class ItemCategoryCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = ItemCategory
    form_class = ItemCategoryForm
    template_name = 'inventory/categories/form.html'
    success_url = reverse_lazy('inventory:category-list')
    permission_required = 'inventory.add_itemcategory'

    def form_valid(self, form):
        # Generate code automatically before saving
        form.instance.code = InventoryService.generate_category_code()
        messages.success(self.request, f'تم إضافة الفئة "{form.instance.name}" بنجاح بالكود {form.instance.code}')
        return super().form_valid(form)

class UnitListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = UnitOfMeasure
    template_name = 'inventory/units/list.html'
    permission_required = 'inventory.view_unitofmeasure'
    paginate_by = 25

class UnitCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = UnitOfMeasure
    form_class = UnitOfMeasureForm
    template_name = 'inventory/units/form.html'
    success_url = reverse_lazy('inventory:unit-list')
    permission_required = 'inventory.add_unitofmeasure'

    def form_valid(self, form):
        form.instance.code = InventoryService.generate_unit_code()
        messages.success(self.request, f'تم إضافة الوحدة "{form.instance.name}" بنجاح بالكود {form.instance.code}')
        return super().form_valid(form)

class WarehouseTransferListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = WarehouseTransfer
    template_name = 'inventory/transfers/list.html'
    context_object_name = 'transfers'
    permission_required = 'inventory.view_warehousetransfer'
    paginate_by = 25

    def get_queryset(self):
        return WarehouseTransfer.objects.select_related('from_warehouse', 'to_warehouse').prefetch_related('lines__item').order_by('-date', '-id')

class WarehouseTransferCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = WarehouseTransfer
    form_class = WarehouseTransferForm
    template_name = 'inventory/transfers/form.html'
    success_url = reverse_lazy('inventory:transfer-list')
    permission_required = 'inventory.add_warehousetransfer'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx['lines'] = WarehouseTransferLineFormSet(self.request.POST)
        else:
            ctx['lines'] = WarehouseTransferLineFormSet()
        return ctx

    def form_valid(self, form):
        ctx = self.get_context_data()
        lines = ctx['lines']
        
        with transaction.atomic():
            if lines.is_valid():
                form.instance.number = DocumentService.generate_number(WarehouseTransfer, 'TRNF')
                self.object = form.save()
                lines.instance = self.object
                lines.save()
            else:
                return self.form_invalid(form)
                
        messages.success(self.request, f'تم تسجيل طلب التحويل {self.object.number}')
        return redirect(self.success_url)

class WarehouseTransferUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):
    model = WarehouseTransfer
    form_class = WarehouseTransferForm
    template_name = 'inventory/transfers/form.html'
    success_url = reverse_lazy('inventory:transfer-list')
    permission_required = 'inventory.change_warehousetransfer'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.status != WarehouseTransfer.Status.DRAFT:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied("لا يمكن تعديل طلب تحويل مخزني غير مسودة.")
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx['lines'] = WarehouseTransferLineFormSet(self.request.POST, instance=self.object)
        else:
            ctx['lines'] = WarehouseTransferLineFormSet(instance=self.object)
        return ctx

    def form_valid(self, form):
        ctx = self.get_context_data()
        lines = ctx['lines']
        if lines.is_valid():
            with transaction.atomic():
                self.object = form.save()
                lines.save()
            messages.success(self.request, f'تم تحديث طلب التحويل {self.object.number}')
            return redirect(self.success_url)
        return self.form_invalid(form)

class WarehouseTransferDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = WarehouseTransfer
    template_name = 'inventory/transfers/detail.html'
    context_object_name = 'transfer'
    permission_required = 'inventory.view_warehousetransfer'


class WarehouseTransferPostView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'inventory.change_warehousetransfer'
    
    def post(self, request, pk):
        transfer = get_object_or_404(WarehouseTransfer, pk=pk)
        try:
            InventoryService.process_transfer(transfer, request.user)
            messages.success(request, f'تم تنفيذ التحويل {transfer.number} وتحديث المخزون')
        except Exception as e:
            messages.error(request, f'خطأ: {e}')
        return redirect('inventory:transfer-list')

class WarehouseTransferReverseView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'inventory.change_warehousetransfer'
    
    def post(self, request, pk):
        transfer = get_object_or_404(WarehouseTransfer, pk=pk)
        try:
            InventoryService.reverse_transfer(transfer, request.user)
            messages.success(request, f'تم عكس التحويل {transfer.number} وتحديث المخزون')
            SystemNotification.notify_accountants(
                title="عكس تحويل مخزني",
                message=f"قام {request.user.username} بعكس التحويل المخزني رقم {transfer.number}.",
                url=reverse('inventory:transfer-list')
            )
        except Exception as e:
            messages.error(request, f'خطأ أثناء العكس: {e}')
        return redirect('inventory:transfer-list')

# --- Loading Order Views ---

class LoadingOrderListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = LoadingOrder
    template_name = 'inventory/loadings/list.html'
    context_object_name = 'orders'
    permission_required = 'inventory.view_loadingorder'
    paginate_by = 25

    def get_queryset(self):
        return LoadingOrder.objects.select_related('sales_rep', 'from_warehouse', 'to_warehouse', 'requested_by').order_by('-date', '-id')

class LoadingOrderCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = LoadingOrder
    form_class = LoadingOrderForm
    template_name = 'inventory/loadings/form.html'
    success_url = reverse_lazy('inventory:loading-list')
    permission_required = 'inventory.add_loadingorder'

    def get_initial(self):
        initial = super().get_initial()
        initial['date'] = timezone.now().date()
        
        rep_id = self.request.GET.get('sales_rep')
        if rep_id:
            initial['sales_rep'] = rep_id
        elif hasattr(self.request.user, 'salesrepresentative'):
            initial['sales_rep'] = self.request.user.salesrepresentative
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        
        # Exclude representative warehouses from the "From" warehouse list
        # We assume any warehouse linked to a SalesRepresentative is a "Rep Warehouse"
        form.fields['from_warehouse'].queryset = Warehouse.objects.exclude(
            salesrepresentative__isnull=False
        ).order_by('name')

        if hasattr(self.request.user, 'salesrepresentative'):
            form.fields['sales_rep'].widget.attrs['style'] = 'pointer-events: none; background-color: #f8f9fa;'
            form.fields['sales_rep'].widget.attrs['tabindex'] = '-1'
        return form

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        reps = SalesRepresentative.objects.select_related('warehouse')
        ctx['rep_warehouse_mapping'] = {rep.id: rep.warehouse.id for rep in reps if rep.warehouse}
        
        if 'lines' in kwargs:
            ctx['lines'] = kwargs['lines']
        elif self.request.POST:
            ctx['lines'] = LoadingOrderLineFormSet(self.request.POST, instance=self.object)
        else:
            ctx['lines'] = LoadingOrderLineFormSet(instance=self.object)
        return ctx

    def form_valid(self, form):
        # ✅ التأكد من أن المستخدم الحالي هو مندوب مبيعات
        if not hasattr(self.request.user, 'salesrepresentative'):
            messages.error(self.request, 'عذراً، طلبات تحميل البضاعة مخصصة للمناديب فقط. حسابك الحالي غير مرتبط بمندوب مبيعات. يمكنك بدلاً من ذلك عمل طلب تحويل مخزني.')
            return self.form_invalid(form)

        # Ensure to_warehouse matches rep warehouse
        if form.instance.sales_rep:
            if form.instance.sales_rep.warehouse:
                form.instance.to_warehouse = form.instance.sales_rep.warehouse
            else:
                form.add_error('sales_rep', 'هذا المندوب ليس لديه مستودع (سيارة) مرتبط به. يرجى ضبط مستودع المندوب في إعدادات المبيعات أولاً.')
                return self.form_invalid(form)
            
        # Bind the formset to form.instance (which contains the populated fields) so validation succeeds
        lines = LoadingOrderLineFormSet(self.request.POST, instance=form.instance)
            
        with transaction.atomic():
            if lines.is_valid():
                form.instance.number = DocumentService.generate_number(LoadingOrder, 'LOAD')
                form.instance.requested_by = self.request.user
                self.object = form.save()
                lines.instance = self.object
                lines.save()
                for obj in lines.deleted_objects:
                    obj.delete()
            else:
                return self.render_to_response(self.get_context_data(form=form, lines=lines))
                
        messages.success(self.request, f'تم إنشاء طلب التحميل {self.object.number}')
        return redirect('inventory:loading-detail', pk=self.object.pk)

class LoadingOrderDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = LoadingOrder
    template_name = 'inventory/loadings/detail.html'
    context_object_name = 'order'
    permission_required = 'inventory.view_loadingorder'

    def get(self, request, *args, **kwargs):
        if 'refresh' in request.GET:
            messages.success(request, 'تم تحديث كميات المخزون المتاحة بالمستودع الرئيسي بنجاح وفقاً لأحدث الحركات!')
            return redirect('inventory:loading-detail', pk=self.get_object().pk)
        return super().get(request, *args, **kwargs)

class LoadingOrderRequestView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'inventory.change_loadingorder'
    
    def post(self, request, pk):
        order = get_object_or_404(LoadingOrder, pk=pk)
        if order.status == LoadingOrder.Status.DRAFT:
            with transaction.atomic():
                order.status = LoadingOrder.Status.PENDING
                order.save()

            try:
                title = f"طلب تحميل بانتظار الاعتماد: {order.number}"
                message = f"قام المندوب {order.sales_rep.name} بتقديم طلب تحميل بضاعة رقم {order.number} وبانتظار اعتمادكم."
                url = reverse('inventory:loading-detail', args=[order.pk])
                SystemNotification.notify_accountants(title, message, url)
            except SystemNotification.DoesNotExist:
                logger.warning("SystemNotification model not available, skipping notification")
            except Exception as e:
                logger.exception("Failed to send notification for loading %s: %s", order.number, e)

            messages.success(request, f'تم إرسال طلب التحميل {order.number} للاعتماد')
        return redirect('inventory:loading-detail', pk=pk)

class LoadingOrderApproveView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'inventory.change_loadingorder'
    
    def post(self, request, pk):
        if hasattr(request.user, 'salesrepresentative'):
            messages.error(request, 'عذراً، غير مسموح لمناديب المبيعات اعتماد طلبات التحميل.')
            return redirect('inventory:loading-detail', pk=pk)
        order = get_object_or_404(LoadingOrder, pk=pk)
        try:
            LoadingService.approve_loading(order, request.user)
            messages.success(request, f'تم اعتماد طلب التحميل {order.number}')
        except Exception as e:
            messages.error(request, f'خطأ: {e}')
        return redirect('inventory:loading-detail', pk=pk)

class LoadingOrderIssueView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'inventory.change_loadingorder'
    
    def post(self, request, pk):
        if hasattr(request.user, 'salesrepresentative'):
            messages.error(request, 'عذراً، غير مسموح لمناديب المبيعات صرف طلبات التحميل.')
            return redirect('inventory:loading-detail', pk=pk)
        order = get_object_or_404(LoadingOrder, pk=pk)
        try:
            LoadingService.issue_loading(order, request.user)
            messages.success(request, f'تم تنفيذ صرف طلب التحميل {order.number} وتحديث المخزون')
        except Exception as e:
            messages.error(request, f'خطأ: {e}')
        return redirect('inventory:loading-detail', pk=pk)

class LoadingOrderCancelView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'inventory.change_loadingorder'
    
    def post(self, request, pk):
        order = get_object_or_404(LoadingOrder, pk=pk)
        try:
            LoadingService.cancel_loading(order, request.user)
            messages.success(request, f'تم إلغاء طلب التحميل {order.number} بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ: {e}')
        return redirect('inventory:loading-detail', pk=pk)


# --- Stock Voucher Views ---

class StockVoucherListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = StockVoucher
    template_name = 'inventory/vouchers/list.html'
    context_object_name = 'vouchers'
    permission_required = 'inventory.view_stockvoucher'
    paginate_by = 25

    def get_queryset(self):
        return StockVoucher.objects.select_related('warehouse', 'created_by').order_by('-date', '-id')

class StockVoucherCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = StockVoucher
    form_class = StockVoucherForm
    template_name = 'inventory/vouchers/form.html'
    success_url = reverse_lazy('inventory:voucher-list')
    permission_required = 'inventory.add_stockvoucher'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx['lines'] = StockVoucherLineFormSet(self.request.POST)
        else:
            ctx['lines'] = StockVoucherLineFormSet()
        return ctx

    def form_valid(self, form):
        ctx = self.get_context_data()
        lines = ctx['lines']
        with transaction.atomic():
            if lines.is_valid():
                vt_prefix = 'REC' if form.instance.voucher_type == StockVoucher.VoucherType.RECEIPT else 'ISS'
                form.instance.number = DocumentService.generate_number(StockVoucher, f'V-{vt_prefix}')
                form.instance.created_by = self.request.user
                self.object = form.save()
                lines.instance = self.object
                lines.save()
                for obj in lines.deleted_objects:
                    obj.delete()
            else:
                return self.form_invalid(form)
        messages.success(self.request, f'تم إنشاء الإذن {self.object.number}')
        return redirect(self.success_url)

class StockVoucherDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = StockVoucher
    template_name = 'inventory/vouchers/detail.html'
    context_object_name = 'voucher'
    permission_required = 'inventory.view_stockvoucher'

class StockVoucherPostView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'inventory.change_stockvoucher'
    
    def post(self, request, pk):
        voucher = get_object_or_404(StockVoucher, pk=pk)
        try:
            StockVoucherService.post_voucher(voucher, request.user)
            messages.success(request, f'تم ترحيل الإذن {voucher.number} وتحديث المخزون')
        except Exception as e:
            messages.error(request, f'خطأ أثناء الترحيل: {e}')
        return redirect('inventory:voucher-detail', pk=pk)

class StockVoucherReverseView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'inventory.change_stockvoucher'
    
    def post(self, request, pk):
        voucher = get_object_or_404(StockVoucher, pk=pk)
        try:
            StockVoucherService.reverse_voucher(voucher, request.user)
            messages.success(request, f'تم عكس الإذن {voucher.number} وتحديث المخزون')
            SystemNotification.notify_accountants(
                title="عكس إذن مخزني",
                message=f"قام {request.user.username} بعكس إذن المخزن رقم {voucher.number}.",
                url=reverse('inventory:voucher-detail', args=[voucher.id])
            )
        except Exception as e:
            messages.error(request, f'خطأ أثناء العكس: {e}')
        return redirect('inventory:voucher-detail', pk=pk)

class ItemDetailsAPIView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'inventory.view_item'
    def get(self, request, pk):
        item = get_object_or_404(Item, pk=pk)
        units = []
        if item.base_unit:
            units.append({'id': item.base_unit.id, 'name': item.base_unit.name, 'factor': 1})
        if item.sales_unit and item.sales_unit != item.base_unit:
            units.append({'id': item.sales_unit.id, 'name': item.sales_unit.name, 'factor': float(item.conversion_factor)})
        
        if item.purchase_unit and item.purchase_unit != item.base_unit and item.purchase_unit != item.sales_unit:
            units.append({
                'id': item.purchase_unit.id, 
                'name': item.purchase_unit.name, 
                'factor': float(item.purchase_conversion_factor)
            })
        
        warehouse_id = request.GET.get('warehouse_id')
        available_qty = 0
        if warehouse_id:
            ledger = ItemLedger.objects.filter(item=item, warehouse_id=warehouse_id).first()
            if ledger:
                available_qty = float(ledger.quantity_on_hand)

        price = item.standard_price
        customer_id = request.GET.get('customer_id')
        if customer_id:
            from apps.sales.models import Customer, PriceList, PriceListItem
            customer = Customer.objects.filter(id=customer_id).first()
            if customer:
                price_list = customer.price_list
                if not price_list:
                    price_list = PriceList.objects.filter(is_default=True, is_active=True).first()
                if price_list:
                    pli = PriceListItem.objects.filter(
                        price_list=price_list,
                        item=item,
                        min_qty__lte=1
                    ).order_by('-min_qty').first()
                    if pli:
                        price = pli.unit_price

        return JsonResponse({
            'units': units,
            'default_unit_id': item.sales_unit_id or item.base_unit_id,
            'standard_price': float(price),
            'available_qty': available_qty
        })

class InventoryReportDashboardView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'inventory/reports/dashboard.html'
    permission_required = 'inventory.view_item'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # We will add report stats here later
        return ctx
