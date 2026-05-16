from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect
from django.db import transaction
from django.views import View
from .models import Item, ItemCategory, Warehouse, UnitOfMeasure, ItemLedger, WarehouseTransfer, LoadingOrder, LoadingOrderLine, StockMovement, StockVoucher
from .forms import ItemForm, ItemCategoryForm, WarehouseForm, WarehouseTransferForm, WarehouseTransferLineFormSet, LoadingOrderForm, LoadingOrderLineFormSet, UnitOfMeasureForm

from .services import InventoryService, LoadingService
from django.db.models import F, ExpressionWrapper, DecimalField
from django.db.models.functions import Coalesce
from decimal import Decimal

class InventoryDashboardView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = StockMovement
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
        ctx['low_stock_items'] = low_stock_items[:10]
        ctx['low_stock_count'] = low_stock_items.count()

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

        return ctx

class ItemListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
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
        # Annotate with current stock from ItemLedger
        stock_map = {
            l['item_id']: l['total_qty']
            for l in ItemLedger.objects.values('item_id').annotate(total_qty=Sum('quantity_on_hand'))
        }
        for item in ctx['items']:
            item.current_stock = stock_map.get(item.id, 0)
        return ctx

class ItemCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Item
    form_class = ItemForm
    template_name = 'inventory/items/form.html'
    permission_required = 'inventory.add_item'
    success_url = reverse_lazy('inventory:item-list')

    def form_valid(self, form):
        form.instance.code = InventoryService.generate_item_code()
        messages.success(self.request, f'تم إضافة الصنف "{form.instance.name}" بنجاح بالكود {form.instance.code}')
        return super().form_valid(form)

class ItemUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Item
    form_class = ItemForm
    template_name = 'inventory/items/form.html'
    permission_required = 'inventory.change_item'
    success_url = reverse_lazy('inventory:item-list')

class ItemDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Item
    template_name = 'inventory/items/detail.html'
    permission_required = 'inventory.view_item'

class WarehouseListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Warehouse
    template_name = 'inventory/warehouses/list.html'
    permission_required = 'inventory.view_warehouse'

class WarehouseCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Warehouse
    form_class = WarehouseForm
    template_name = 'inventory/warehouses/form.html'
    success_url = reverse_lazy('inventory:warehouse-list')
    permission_required = 'inventory.add_warehouse'

class ItemCategoryListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = ItemCategory
    template_name = 'inventory/categories/list.html'
    permission_required = 'inventory.view_itemcategory'

class ItemCategoryCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
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

class UnitListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = UnitOfMeasure
    template_name = 'inventory/units/list.html'
    permission_required = 'inventory.view_unitofmeasure'

class UnitCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = UnitOfMeasure
    form_class = UnitOfMeasureForm
    template_name = 'inventory/units/form.html'
    success_url = reverse_lazy('inventory:unit-list')
    permission_required = 'inventory.add_unitofmeasure'

    def form_valid(self, form):
        form.instance.code = InventoryService.generate_unit_code()
        messages.success(self.request, f'تم إضافة الوحدة "{form.instance.name}" بنجاح بالكود {form.instance.code}')
        return super().form_valid(form)

class WarehouseTransferListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = WarehouseTransfer
    template_name = 'inventory/transfers/list.html'
    context_object_name = 'transfers'
    permission_required = 'inventory.view_warehousetransfer'

class WarehouseTransferCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
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
                from apps.core.services import DocumentService
                form.instance.number = DocumentService.generate_number(WarehouseTransfer, 'TRNF')
                self.object = form.save()
                lines.instance = self.object
                lines.save()
            else:
                return self.form_invalid(form)
                
        messages.success(self.request, f'تم تسجيل طلب التحويل {self.object.number}')
        return redirect(self.success_url)

class WarehouseTransferUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = WarehouseTransfer
    form_class = WarehouseTransferForm
    template_name = 'inventory/transfers/form.html'
    success_url = reverse_lazy('inventory:transfer-list')
    permission_required = 'inventory.change_warehousetransfer'

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

class WarehouseTransferDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = WarehouseTransfer
    template_name = 'inventory/transfers/detail.html'
    context_object_name = 'transfer'
    permission_required = 'inventory.view_warehousetransfer'


class WarehouseTransferPostView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'inventory.change_warehousetransfer'
    
    def post(self, request, pk):
        transfer = get_object_or_404(WarehouseTransfer, pk=pk)
        try:
            from .services import InventoryService
            InventoryService.process_transfer(transfer, request.user)
            messages.success(request, f'تم تنفيذ التحويل {transfer.number} وتحديث المخزون')
        except Exception as e:
            messages.error(request, f'خطأ: {e}')
        return redirect('inventory:transfer-list')

class WarehouseTransferReverseView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'inventory.change_warehousetransfer'
    
    def post(self, request, pk):
        transfer = get_object_or_404(WarehouseTransfer, pk=pk)
        try:
            from .services import InventoryService
            InventoryService.reverse_transfer(transfer, request.user)
            messages.success(request, f'تم عكس التحويل {transfer.number} وتحديث المخزون')
        except Exception as e:
            messages.error(request, f'خطأ أثناء العكس: {e}')
        return redirect('inventory:transfer-list')

# --- Loading Order Views ---

class LoadingOrderListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = LoadingOrder
    template_name = 'inventory/loadings/list.html'
    context_object_name = 'orders'
    permission_required = 'inventory.view_loadingorder'
    ordering = ['-date', '-id']

class LoadingOrderCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = LoadingOrder
    form_class = LoadingOrderForm
    template_name = 'inventory/loadings/form.html'
    success_url = reverse_lazy('inventory:loading-list')
    permission_required = 'inventory.add_loadingorder'

    def get_initial(self):
        from django.utils import timezone
        initial = super().get_initial()
        initial['date'] = timezone.now().date()
        if hasattr(self.request.user, 'salesrepresentative'):
            initial['sales_rep'] = self.request.user.salesrepresentative
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        from apps.inventory.models import Warehouse
        
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
        from apps.sales.models import SalesRepresentative
        reps = SalesRepresentative.objects.select_related('warehouse')
        ctx['rep_warehouse_mapping'] = {rep.id: rep.warehouse.id for rep in reps if rep.warehouse}
        
        if self.request.POST:
            ctx['lines'] = LoadingOrderLineFormSet(self.request.POST)
        else:
            ctx['lines'] = LoadingOrderLineFormSet()
        return ctx

    def form_valid(self, form):
        # ✅ التأكد من أن المستخدم الحالي هو مندوب مبيعات
        if not hasattr(self.request.user, 'salesrepresentative'):
            messages.error(self.request, 'عذراً، طلبات تحميل البضاعة مخصصة للمناديب فقط. حسابك الحالي غير مرتبط بمندوب مبيعات. يمكنك بدلاً من ذلك عمل طلب تحويل مخزني.')
            return self.form_invalid(form)


        ctx = self.get_context_data()
        lines = ctx['lines']

        
        # Ensure to_warehouse matches rep warehouse
        if form.instance.sales_rep:
            if form.instance.sales_rep.warehouse:
                form.instance.to_warehouse = form.instance.sales_rep.warehouse
            else:
                form.add_error('sales_rep', 'هذا المندوب ليس لديه مستودع (سيارة) مرتبط به. يرجى ضبط مستودع المندوب في إعدادات المبيعات أولاً.')
                return self.form_invalid(form)
            
        with transaction.atomic():
            if lines.is_valid():
                from apps.core.services import DocumentService
                form.instance.number = DocumentService.generate_number(LoadingOrder, 'LOAD')
                form.instance.requested_by = self.request.user
                self.object = form.save()
                lines.instance = self.object
                lines.save()
                for obj in lines.deleted_objects:
                    obj.delete()
            else:
                return self.form_invalid(form)
        messages.success(self.request, f'تم إنشاء طلب التحميل {self.object.number}')
        return redirect(self.success_url)

class LoadingOrderDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = LoadingOrder
    template_name = 'inventory/loadings/detail.html'
    context_object_name = 'order'
    permission_required = 'inventory.view_loadingorder'

class LoadingOrderRequestView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'inventory.change_loadingorder'
    
    def post(self, request, pk):
        order = get_object_or_404(LoadingOrder, pk=pk)
        if order.status == LoadingOrder.Status.DRAFT:
            with transaction.atomic():
                order.status = LoadingOrder.Status.PENDING
                order.save()
            messages.success(request, f'تم إرسال طلب التحميل {order.number} للاعتماد')
        return redirect('inventory:loading-detail', pk=pk)

class LoadingOrderApproveView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'inventory.change_loadingorder'
    
    def post(self, request, pk):
        order = get_object_or_404(LoadingOrder, pk=pk)
        try:
            LoadingService.approve_loading(order, request.user)
            messages.success(request, f'تم اعتماد طلب التحميل {order.number}')
        except Exception as e:
            messages.error(request, f'خطأ: {e}')
        return redirect('inventory:loading-detail', pk=pk)

class LoadingOrderIssueView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'inventory.change_loadingorder'
    
    def post(self, request, pk):
        order = get_object_or_404(LoadingOrder, pk=pk)
        try:
            LoadingService.issue_loading(order, request.user)
            messages.success(request, f'تم تنفيذ صرف طلب التحميل {order.number} وتحديث المخزون')
        except Exception as e:
            messages.error(request, f'خطأ: {e}')
        return redirect('inventory:loading-detail', pk=pk)

class LoadingOrderCancelView(LoginRequiredMixin, PermissionRequiredMixin, View):
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
from .models import StockVoucher, StockVoucherLine
from .forms import StockVoucherForm, StockVoucherLineFormSet
from .services import StockVoucherService

class StockVoucherListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = StockVoucher
    template_name = 'inventory/vouchers/list.html'
    context_object_name = 'vouchers'
    permission_required = 'inventory.view_stockvoucher'
    ordering = ['-date', '-id']

class StockVoucherCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
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
                from apps.core.services import DocumentService
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

class StockVoucherDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = StockVoucher
    template_name = 'inventory/vouchers/detail.html'
    context_object_name = 'voucher'
    permission_required = 'inventory.view_stockvoucher'

class StockVoucherPostView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'inventory.change_stockvoucher'
    
    def post(self, request, pk):
        voucher = get_object_or_404(StockVoucher, pk=pk)
        try:
            StockVoucherService.post_voucher(voucher, request.user)
            messages.success(request, f'تم ترحيل الإذن {voucher.number} وتحديث المخزون')
        except Exception as e:
            messages.error(request, f'خطأ أثناء الترحيل: {e}')
        return redirect('inventory:voucher-detail', pk=pk)

class StockVoucherReverseView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'inventory.change_stockvoucher'
    
    def post(self, request, pk):
        voucher = get_object_or_404(StockVoucher, pk=pk)
        try:
            StockVoucherService.reverse_voucher(voucher, request.user)
            messages.success(request, f'تم عكس الإذن {voucher.number} وتحديث المخزون')
        except Exception as e:
            messages.error(request, f'خطأ أثناء العكس: {e}')
        return redirect('inventory:voucher-detail', pk=pk)

from django.http import JsonResponse

class ItemDetailsAPIView(LoginRequiredMixin, PermissionRequiredMixin, View):
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
        
        return JsonResponse({
            'units': units,
            'default_unit_id': item.sales_unit_id or item.base_unit_id,
            'standard_price': float(item.standard_price)
        })

class InventoryReportDashboardView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Item
    template_name = 'inventory/reports/dashboard.html'
    permission_required = 'inventory.view_item'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # We will add report stats here later
        return ctx
