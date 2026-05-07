from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404
from django.utils import timezone
from django.db import transaction
from apps.core.models import Account
from .models import Asset, AssetCategory, DepreciationLog
from .services import AssetService
from .forms import AssetForm, AssetCategoryForm

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
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        asset = form.save()

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

class AssetDisposeView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'assets.change_asset'
    template_name = 'assets/asset_dispose.html' # We'll need this template or just a post
    
    def post(self, request, pk):
        asset = get_object_or_404(Asset, pk=pk)
        disposal_date = request.POST.get('disposal_date', timezone.now().date().isoformat())
        disposal_value = request.POST.get('disposal_value', '0')
        offset_account_id = request.POST.get('offset_account_id')

        if not offset_account_id:
            messages.error(request, 'يجب تحديد حساب التحصيل (البنك/الصندوق).')
            return redirect('assets:asset-list')

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

