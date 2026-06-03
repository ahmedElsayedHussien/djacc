import re

def main():
    file_path = 'apps/assets/views.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    # 1. AssetDashboardView
    old_dash = """    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        # إحصائيات عامة
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
        
        ctx['category_stats'] = AssetCategory.objects.annotate(
            asset_count=Count('assets'),
            total_cost=Sum('assets__purchase_value')
        ).filter(asset_count__gt=0).order_by('-total_cost')"""
    new_dash = """    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        
        from django.db.models import Q
        active_qs = Asset.objects.exclude(status=Asset.Status.DISPOSED)
        totals = active_qs.aggregate(
            purchase_val=Sum('purchase_value'),
            initial_dep=Sum('initial_accumulated_depreciation')
        )
        
        total_purchase_val = totals['purchase_val'] or Decimal('0')
        total_initial_dep = totals['initial_dep'] or Decimal('0')
        total_system_dep = DepreciationLog.objects.filter(asset__in=active_qs).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        total_acc_dep = total_initial_dep + total_system_dep
        ctx['total_cost'] = total_purchase_val
        ctx['total_acc_dep'] = total_acc_dep
        ctx['net_book_value'] = total_purchase_val - total_acc_dep
        
        active_q = ~Q(assets__status=Asset.Status.DISPOSED)
        ctx['category_stats'] = AssetCategory.objects.annotate(
            asset_count=Count('assets', filter=active_q),
            total_cost=Sum('assets__purchase_value', filter=active_q)
        ).filter(asset_count__gt=0).order_by('-total_cost')"""
    content = content.replace(old_dash, new_dash)

    # 2. AssetCreateView Exception Handling
    old_create_view = """    def form_valid(self, form):
        offset_account_id = self.request.POST.get('offset_account_id')
        if not offset_account_id:
            messages.error(self.request, 'يجب تحديد حساب المقابل لتسجيل الأصل محاسبياً.')
            return self.form_invalid(form)

        try:
            with transaction.atomic():
                asset = form.save(commit=False)
                asset.code = DocumentService.generate_number(Asset, 'AST', field_name='code')
                asset.save()

                offset_account = Account.objects.get(pk=offset_account_id)
                AssetService.register_asset(
                    asset=asset,
                    offset_account=offset_account,
                    created_by=self.request.user,
                )
        except Exception as e:
            raise e

        messages.success(self.request, f'تم تسجيل الأصل «{asset.name}» وإنشاء القيد المحاسبي بنجاح.')
        return redirect(self.success_url)"""
    new_create_view = """    def form_valid(self, form):
        offset_account_id = self.request.POST.get('offset_account_id')
        if not offset_account_id:
            messages.error(self.request, 'يجب تحديد حساب المقابل لتسجيل الأصل محاسبياً.')
            return self.form_invalid(form)

        try:
            with transaction.atomic():
                asset = form.save(commit=False)
                asset.code = DocumentService.generate_number(Asset, 'AST', field_name='code')
                asset.save()

                offset_account = Account.objects.get(pk=offset_account_id)
                AssetService.register_asset(
                    asset=asset,
                    offset_account=offset_account,
                    created_by=self.request.user,
                )
        except Account.DoesNotExist:
            messages.error(self.request, 'الحساب المحدد غير موجود.')
            return self.form_invalid(form)
        except Exception as e:
            messages.error(self.request, f'خطأ أثناء إنشاء القيد: {str(e)}')
            return self.form_invalid(form)

        messages.success(self.request, f'تم تسجيل الأصل «{asset.name}» وإنشاء القيد المحاسبي بنجاح.')
        return redirect(self.success_url)"""
    content = content.replace(old_create_view, new_create_view)

    # 3. AssetUpdateView Disable fields
    old_update = """class AssetUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):
    model = Asset
    form_class = AssetForm
    template_name = 'assets/asset_form.html'
    success_url = reverse_lazy('assets:asset-list')
    permission_required = 'assets.change_asset'

    def get_context_data(self, **kwargs):"""
    new_update = """class AssetUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):
    model = Asset
    form_class = AssetForm
    template_name = 'assets/asset_form.html'
    success_url = reverse_lazy('assets:asset-list')
    permission_required = 'assets.change_asset'

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        readonly_fields = [
            'purchase_value', 'initial_accumulated_depreciation', 
            'purchase_date', 'salvage_value', 'category'
        ]
        for field in readonly_fields:
            if field in form.fields:
                form.fields[field].disabled = True
                form.fields[field].help_text = "لا يمكن تعديل هذا الحقل بعد تسجيل الأصل وارتباطه بقيد محاسبي."
        return form

    def get_context_data(self, **kwargs):"""
    content = content.replace(old_update, new_update)

    # 4. AssetDisposeView Try/except
    old_disp = """    def post(self, request, pk):
        asset = get_object_or_404(Asset, pk=pk)
        disposal_date_str = request.POST.get('disposal_date', timezone.now().date().isoformat())
        disposal_value_str = request.POST.get('disposal_value', '0')
        offset_account_id = request.POST.get('offset_account_id')

        if not offset_account_id:
            messages.error(request, 'يجب تحديد حساب التحصيل (البنك/الصندوق).')
            return redirect('assets:asset-detail', pk=pk)

        disposal_date = date.fromisoformat(disposal_date_str)
        disposal_value = Decimal(disposal_value_str)

        offset_account = Account.objects.get(pk=offset_account_id)
        
        try:
            AssetService.dispose_asset(
                asset=asset,
                disposal_date=disposal_date,
                disposal_value=disposal_value,
                offset_account=offset_account,
                created_by=request.user
            )
            messages.success(request, f'تم استبعاد الأصل {asset.name} بنجاح.')
        except Exception as e:
            messages.error(request, f'خطأ أثناء الاستبعاد: {str(e)}')
            
        return redirect('assets:asset-list')"""
    new_disp = """    def post(self, request, pk):
        asset = get_object_or_404(Asset, pk=pk)
        
        if asset.status != Asset.Status.ACTIVE and asset.status != Asset.Status.FULLY_DEPRECIATED:
            messages.error(request, 'لا يمكن استبعاد هذا الأصل، قد يكون مستبعداً بالفعل.')
            return redirect('assets:asset-detail', pk=pk)

        disposal_date_str = request.POST.get('disposal_date', timezone.now().date().isoformat())
        disposal_value_str = request.POST.get('disposal_value', '0')
        offset_account_id = request.POST.get('offset_account_id')

        if not offset_account_id:
            messages.error(request, 'يجب تحديد حساب التحصيل (البنك/الصندوق).')
            return redirect('assets:asset-detail', pk=pk)

        try:
            disposal_date = date.fromisoformat(disposal_date_str)
            disposal_value = Decimal(disposal_value_str or '0')
        except Exception:
            messages.error(request, 'قيم التاريخ أو مبلغ الاستبعاد غير صالحة.')
            return redirect('assets:asset-detail', pk=pk)

        try:
            offset_account = Account.objects.get(pk=offset_account_id)
            AssetService.dispose_asset(
                asset=asset,
                disposal_date=disposal_date,
                disposal_value=disposal_value,
                offset_account=offset_account,
                created_by=request.user
            )
            messages.success(request, f'تم استبعاد الأصل {asset.name} بنجاح.')
        except Exception as e:
            messages.error(request, f'خطأ أثناء الاستبعاد: {str(e)}')
            
        return redirect('assets:asset-list')"""
    content = content.replace(old_disp, new_disp)

    # 5. RunDepreciationView
    old_run = """    def post(self, request):
        count = AssetService.run_depreciation(timezone.now().date(), request.user)
        messages.success(request, f'تم تنفيذ الإهلاك لـ {count} أصل بنجاح.')
        return redirect('assets:asset-list')"""
    new_run = """    def post(self, request):
        try:
            count = AssetService.run_depreciation(timezone.now().date(), request.user)
            messages.success(request, f'تم تنفيذ الإهلاك لـ {count} أصل بنجاح.')
        except Exception as e:
            messages.error(request, f'خطأ أثناء تنفيذ الإهلاك: {str(e)}')
        return redirect('assets:asset-list')"""
    content = content.replace(old_run, new_run)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Views patched.")

if __name__ == '__main__':
    main()
