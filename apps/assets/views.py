from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404
from django.utils import timezone
from django.db import transaction
from apps.core.models import Account
from django.db.models import Sum, Count, Q
from .models import Asset, AssetCategory, DepreciationLog
from .services import AssetService
from .forms import AssetForm, AssetCategoryForm
from decimal import Decimal

class AssetDashboardView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Asset
    template_name = 'assets/dashboard.html'
    permission_required = 'assets.view_asset'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # 1. Financial Stats
        active_assets = Asset.objects.filter(status=Asset.Status.ACTIVE)
        totals = Asset.objects.aggregate(
            purchase_val=Sum('purchase_value'),
            initial_dep=Sum('initial_accumulated_depreciation')
        )
        
        total_purchase_val = totals['purchase_val'] or Decimal('0')
        total_initial_dep = totals['initial_dep'] or Decimal('0')
        total_system_dep = DepreciationLog.objects.aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        total_acc_dep = total_initial_dep + total_system_dep
        ctx['total_cost'] = total_purchase_val
        ctx['total_acc_dep'] = total_acc_dep
        ctx['net_book_value'] = total_purchase_val - total_acc_dep
        
        # 2. Category Distribution
        ctx['category_stats'] = AssetCategory.objects.annotate(
            asset_count=Count('assets'),
            total_cost=Sum('assets__purchase_value')
        ).filter(asset_count__gt=0).order_by('-total_cost')

        # 3. Status Distribution
        ctx['status_counts'] = Asset.objects.values('status').annotate(count=Count('id'))
        
        # 4. Recent Depreciation
        ctx['recent_depreciations'] = DepreciationLog.objects.select_related('asset').order_by('-date', '-id')[:10]
        
        # 5. Asset Count
        ctx['active_count'] = Asset.objects.filter(status=Asset.Status.ACTIVE).count()
        ctx['disposed_count'] = Asset.objects.filter(status=Asset.Status.DISPOSED).count()

        return ctx

class AssetListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Asset
    template_name = 'assets/asset_list.html'
    context_object_name = 'assets'
    permission_required = 'assets.view_asset'

class AssetCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Asset
    form_class = AssetForm
    template_name = 'assets/asset_form.html'
    success_url = reverse_lazy('assets:asset-list')
    permission_required = 'assets.add_asset'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # ح/35 = أرصدة افتتاحية (الأكثر شيوعاً للترحيل من نظام قديم)
        ctx['offset_accounts'] = Account.objects.filter(is_leaf=True).order_by('code')
        ctx['default_offset_account'] = Account.objects.filter(name__contains='افتتاحية').first()
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        from apps.core.services import DocumentService
        asset = form.save(commit=False)
        asset.code = DocumentService.generate_number(Asset, 'AST', field_name='code')
        asset.save()

        offset_account_id = self.request.POST.get('offset_account_id')
        if not offset_account_id:
            messages.error(self.request, 'يجب تحديد حساب المقابل لتسجيل الأصل محاسبياً.')
            asset.delete()
            return self.form_invalid(form)

        try:
            offset_account = Account.objects.get(pk=offset_account_id)
            AssetService.register_asset(
                asset=asset,
                offset_account=offset_account,
                created_by=self.request.user,
            )
            messages.success(
                self.request,
                f'تم تسجيل الأصل «{asset.name}» وإنشاء القيد المحاسبي بنجاح.'
            )
        except Exception as e:
            messages.error(self.request, f'خطأ أثناء إنشاء القيد: {e}')
            raise  # rollback via @transaction.atomic

        return redirect(self.success_url)

class AssetCategoryListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = AssetCategory
    template_name = 'assets/category_list.html'
    context_object_name = 'categories'
    permission_required = 'assets.view_assetcategory'

class AssetCategoryCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = AssetCategory
    form_class = AssetCategoryForm
    template_name = 'assets/category_form.html'
    success_url = reverse_lazy('assets:category-list')
    permission_required = 'assets.add_assetcategory'

    def form_valid(self, form):
        try:
            AssetService.create_category_with_accounts(
                name=form.cleaned_data['name'],
                depreciation_rate=form.cleaned_data['default_depreciation_rate'],
                created_by=self.request.user
            )
            messages.success(self.request, 'تم إنشاء التصنيف والحسابات المرتبطة به بنجاح.')
            return redirect(self.success_url)
        except Exception as e:
            messages.error(self.request, f'خطأ أثناء إنشاء الحسابات: {e}')
            return self.form_invalid(form)

class RunDepreciationView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    # We use ListView but it's actually a trigger view
    model = DepreciationLog
    template_name = 'assets/depreciation_run.html'
    permission_required = 'assets.add_depreciationlog'

    def post(self, request, *args, **kwargs):
        count = AssetService.run_depreciation(timezone.now().date(), request.user)
        messages.success(request, f'تم تنفيذ الإهلاك لـ {count} أصل بنجاح.')
        return redirect('assets:asset-list')

class AssetDisposeView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Asset
    template_name = 'assets/asset_dispose.html'
    context_object_name = 'asset'
    permission_required = 'assets.change_asset'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.core.models import Account
        ctx['offset_accounts'] = Account.objects.filter(is_leaf=True).order_by('code')
        return ctx

    def post(self, request, pk):
        asset = get_object_or_404(Asset, pk=pk)
        disposal_date = request.POST.get('disposal_date', timezone.now().date().isoformat())
        disposal_value = request.POST.get('disposal_value', '0')
        offset_account_id = request.POST.get('offset_account_id')

        if not offset_account_id:
            messages.error(request, 'يجب تحديد حساب التحصيل (البنك/الصندوق).')
            return redirect('assets:asset-detail', pk=pk)

        try:
            offset_account = Account.objects.get(pk=offset_account_id)
            AssetService.dispose_asset(
                asset=asset,
                disposal_date=date.fromisoformat(disposal_date),
                disposal_value=Decimal(disposal_value),
                offset_account=offset_account,
                created_by=request.user
            )
            messages.success(request, f'تم استبعاد الأصل {asset.name} بنجاح.')
        except Exception as e:
            messages.error(request, f'خطأ أثناء الاستبعاد: {e}')
            
        return redirect('assets:asset-list')

class AssetDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Asset
    template_name = 'assets/asset_detail.html'
    context_object_name = 'asset'
    permission_required = 'assets.view_asset'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.core.models import Account
        ctx['logs'] = self.object.depreciation_logs.select_related('journal_entry').order_by('-date')
        ctx['offset_accounts'] = Account.objects.filter(is_leaf=True).order_by('code')
        return ctx

class AssetUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Asset
    form_class = AssetForm
    template_name = 'assets/asset_form.html'
    success_url = reverse_lazy('assets:asset-list')
    permission_required = 'assets.change_asset'

