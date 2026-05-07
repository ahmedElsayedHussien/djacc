from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect
from django.db import transaction
from django.views import View
from .models import Item, ItemCategory, Warehouse, UnitOfMeasure, ItemLedger, WarehouseTransfer, LoadingOrder, LoadingOrderLine
from .forms import ItemForm, ItemCategoryForm, WarehouseForm, WarehouseTransferForm, LoadingOrderForm, LoadingOrderLineFormSet
from .services import InventoryService, LoadingService

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
        messages.success(self.request, f'تم إنشاء الصنف "{form.instance.name}" بنجاح')
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

class UnitListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = UnitOfMeasure
    template_name = 'inventory/units/list.html'
    permission_required = 'inventory.view_unitofmeasure'

class UnitCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = UnitOfMeasure
    fields = ['code', 'name']
    template_name = 'inventory/units/form.html'
    success_url = reverse_lazy('inventory:unit-list')
    permission_required = 'inventory.add_unitofmeasure'

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

    def form_valid(self, form):
        with transaction.atomic():
            from apps.core.services import DocumentService
            form.instance.number = DocumentService.generate_number(WarehouseTransfer, 'TRNF')
            self.object = form.save()
        messages.success(self.request, f'تم تسجيل طلب التحويل {self.object.number}')
        return redirect(self.success_url)

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
        ctx = self.get_context_data()
        lines = ctx['lines']
        
        # Ensure to_warehouse matches rep warehouse
        if form.instance.sales_rep and form.instance.sales_rep.warehouse:
            form.instance.to_warehouse = form.instance.sales_rep.warehouse
            
        with transaction.atomic():
            from apps.core.services import DocumentService
            form.instance.number = DocumentService.generate_number(LoadingOrder, 'LOAD')
            form.instance.requested_by = self.request.user
            self.object = form.save()
            if lines.is_valid():
                lines.instance = self.object
                lines.save()
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
            from apps.core.services import DocumentService
            vt_prefix = 'REC' if form.instance.voucher_type == StockVoucher.VoucherType.RECEIPT else 'ISS'
            form.instance.number = DocumentService.generate_number(StockVoucher, f'V-{vt_prefix}')
            form.instance.created_by = self.request.user
            self.object = form.save()
            if lines.is_valid():
                lines.instance = self.object
                lines.save()
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
        if item.sales_unit:
            units.append({'id': item.sales_unit.id, 'name': item.sales_unit.name, 'factor': float(item.conversion_factor)})
        if item.purchase_unit and item.purchase_unit != item.base_unit and item.purchase_unit != item.sales_unit:
            units.append({
                'id': item.purchase_unit.id, 
                'name': item.purchase_unit.name, 
                'factor': float(item.purchase_conversion_factor)
            })
        
        return JsonResponse({
            'units': units,
            'default_unit_id': item.sales_unit_id or item.base_unit_id
        })

