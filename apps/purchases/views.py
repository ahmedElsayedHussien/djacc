import logging
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.core.mixins import PermRequiredMixin
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.db import transaction
from django.views import View
from django.db.models import Sum, Count, Q, F
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import date
from apps.core.tax_utils import calculate_line_taxes
from apps.core.utils import get_account_balance
from apps.core.models import SystemNotification
from .models import Supplier, PurchaseInvoice, PurchaseInvoiceLine, SupplierPayment, PurchaseReturn, PurchaseReturnLine, PurchaseOrder, PaymentAllocation
from .forms import SupplierForm, PurchaseInvoiceForm, PurchaseInvoiceLineFormSet, SupplierPaymentForm, PurchaseReturnForm, PurchaseReturnLineFormSet
from .services import SupplierService, PurchaseService

logger = logging.getLogger(__name__)

class PurchaseDashboardView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    template_name = 'purchases/dashboard.html'
    permission_required = 'purchases.view_purchaseinvoice'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        month_start = date.today().replace(day=1)
        
        # 1. Monthly Summary
        monthly_stats = PurchaseInvoice.objects.filter(
            date__gte=month_start, 
            status=PurchaseInvoice.Status.POSTED
        ).aggregate(
            total_amount=Sum('total'),
            count=Count('id')
        )
        ctx['monthly_total'] = monthly_stats['total_amount'] or 0
        ctx['monthly_count'] = monthly_stats['count'] or 0

        # 2. Supplier Distribution (Current Month)
        ctx['supplier_stats'] = Supplier.objects.annotate(
            total=Sum('purchaseinvoice__total', filter=Q(purchaseinvoice__date__gte=month_start, purchaseinvoice__status=PurchaseInvoice.Status.POSTED))
        ).filter(total__gt=0).order_by('-total')[:5]

        # 3. Pending Tasks
        ctx['pending_orders'] = PurchaseOrder.objects.filter(status=PurchaseOrder.Status.APPROVED).count()
        ctx['draft_invoices'] = PurchaseInvoice.objects.filter(status=PurchaseInvoice.Status.DRAFT).count()
        
        # 4. Debts Summary (Total Unpaid)
        unpaid = PurchaseInvoice.objects.filter(status=PurchaseInvoice.Status.POSTED).annotate(
            balance=F('total') - F('paid_amount')
        ).filter(balance__gt=0).aggregate(total_due=Sum('balance'))
        ctx['total_unpaid'] = unpaid['total_due'] or 0

        # 5. Recent Activity
        ctx['recent_invoices'] = PurchaseInvoice.objects.select_related('supplier').order_by('-date', '-id')[:10]

        # 6. Monthly Payments (Aggregation)
        monthly_payments = SupplierPayment.objects.filter(
            date__gte=month_start
        ).aggregate(total=Sum('amount'))['total'] or 0
        ctx['monthly_payments'] = monthly_payments

        return ctx

class PurchaseReturnListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = PurchaseReturn
    template_name = 'purchases/returns/list.html'
    context_object_name = 'returns'
    permission_required = 'purchases.view_purchasereturn'
    ordering = ['-date', '-id']
    paginate_by = 50

    def get_queryset(self):
        return super().get_queryset().select_related('supplier')

class PurchaseReturnCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = PurchaseReturn
    form_class = PurchaseReturnForm
    template_name = 'purchases/returns/form.html'
    permission_required = 'purchases.add_purchasereturn'
    success_url = reverse_lazy('purchases:return-list')

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['lines'] = PurchaseReturnLineFormSet(self.request.POST)
        else:
            data['lines'] = PurchaseReturnLineFormSet()
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        lines = context['lines']
        with transaction.atomic():
            form.instance.created_by = self.request.user
            
            form.instance.subtotal = 0
            form.instance.total = 0
            try:
                if lines.is_valid():
                    self.object = form.save()
                    lines.instance = self.object
                    instances = lines.save(commit=False)
                    
                    # ... (rest of the logic inside the previous block)
                    # I will replace the whole block to be safe
                    gross_total = 0
                    discount_total = 0
                    tax_total_added = 0
                    tax_total_deducted = 0
                    
                    for line in instances:
                        if self.object.invoice:
                            original_line = self.object.invoice.lines.select_for_update().filter(item=line.item).first()
                            if not original_line:
                                raise ValidationError(f"الصنف {line.item.name} غير موجود في الفاتورة الأصلية")
                            
                            previous_returned = PurchaseReturnLine.objects.filter(
                                purchase_return__invoice=self.object.invoice,
                                purchase_return__status='posted',
                                item=line.item
                            ).aggregate(total=Sum('quantity'))['total'] or 0
                            
                            available = original_line.quantity - previous_returned
                            if line.quantity > available:
                                raise ValidationError(
                                    f"الكمية المرتجعة للصنف {line.item.name} ({line.quantity}) "
                                    f"تتجاوز الكمية المتاحة للإرجاع ({available})"
                                )

                        line_subtotal = Decimal(str(line.quantity * line.unit_cost))
                        line_discount = line_subtotal * (Decimal(str(line.discount_percent)) / Decimal('100'))
                        net_line = line_subtotal - line_discount
                        
                        res = calculate_line_taxes(
                            net_line,
                            line.tax_type,
                            line.tax_percent,
                            line.tax_type2,
                            line.tax_percent2,
                            is_purchase_or_expense=True
                        )
                        
                        line.total = net_line + res['tax1_signed'] + res['tax2_signed']
                        if hasattr(line, 'unit') and line.unit:
                            line.base_quantity = line.item.convert_to_base(line.quantity, line.unit)
                        else:
                            line.base_quantity = line.quantity
                        line.save()
                        
                        gross_total += line_subtotal
                        discount_total += line_discount
                        tax_total_added += res['tax_total_added']
                        tax_total_deducted += res['tax_total_deducted']

                    self.object.subtotal = gross_total
                    self.object.discount_amount = discount_total
                    self.object.tax_amount = tax_total_added - tax_total_deducted
                    self.object.total = gross_total - discount_total + tax_total_added - tax_total_deducted
                    self.object.save()
                else:
                    return self.form_invalid(form)
            except ValidationError as e:
                messages.error(self.request, str(e))
                logger.exception('Validation error in PurchaseReturnCreateView')
                transaction.set_rollback(True)
                return self.form_invalid(form)
        return redirect(self.success_url)

class PurchaseReturnDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = PurchaseReturn
    template_name = 'purchases/returns/detail.html'
    context_object_name = 'purchase_return'
    permission_required = 'purchases.view_purchasereturn'

    def get_queryset(self):
        return super().get_queryset().select_related('supplier', 'invoice', 'cost_center').prefetch_related('lines__item', 'lines__unit')

class PurchaseReturnPostView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'purchases.change_purchasereturn'
    
    def post(self, request, pk):
        purchase_return = get_object_or_404(PurchaseReturn.objects.select_related('supplier'), pk=pk)
        try:
            PurchaseService.post_return(purchase_return, request.user)
            messages.success(request, f'تم ترحيل مرتجع المشتريات {purchase_return.number}')
        except Exception as e:
            logger.exception('Error posting purchase return %s', purchase_return.number)
            messages.error(request, f'خطأ: {e}')
        return redirect('purchases:return-detail', pk=pk)


class SupplierListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = Supplier
    template_name = 'purchases/suppliers/list.html'
    context_object_name = 'suppliers'
    permission_required = 'purchases.view_supplier'
    paginate_by = 50

    def get_queryset(self):
        qs = Supplier.objects.select_related('account').order_by('code')
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(name__icontains=q) | qs.filter(code__icontains=q)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        suppliers = ctx.get(self.context_object_name)
        if suppliers:
            for s in suppliers:
                if s.account_id:
                    s._cached_balance = get_account_balance(s.account)
        return ctx

class SupplierCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = Supplier
    form_class = SupplierForm
    template_name = 'purchases/suppliers/form.html'
    permission_required = 'purchases.add_supplier'
    success_url = reverse_lazy('purchases:supplier-list')

    def form_valid(self, form):
        try:
            supplier = SupplierService.create_supplier(form.cleaned_data)
            messages.success(self.request,
                f'تم إنشاء المورد "{supplier.name}" بكود {supplier.code} — كود الحساب: {supplier.account.code}')
            return redirect(self.success_url)
        except Exception as e:
            logger.exception('Error creating supplier')
            messages.error(self.request, f'خطأ أثناء إنشاء المورد: {e}')
            return self.form_invalid(form)

class SupplierUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):
    model = Supplier
    form_class = SupplierForm
    template_name = 'purchases/suppliers/form.html'
    permission_required = 'purchases.change_supplier'
    success_url = reverse_lazy('purchases:supplier-list')

    def form_valid(self, form):
        try:
            SupplierService.update_supplier(self.object, form.cleaned_data)
            messages.success(self.request, 'تم تحديث بيانات المورد بنجاح')
            return redirect(self.success_url)
        except Exception as e:
            logger.exception('Error updating supplier')
            messages.error(self.request, f'خطأ أثناء تحديث المورد: {e}')
            return self.form_invalid(form)

class SupplierDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = Supplier
    template_name = 'purchases/suppliers/detail.html'
    permission_required = 'purchases.view_supplier'

    def get_queryset(self):
        return super().get_queryset().select_related('account')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['invoices'] = self.object.purchaseinvoice_set.select_related('supplier').order_by('-date')[:10]
        ctx['balance'] = get_account_balance(self.object.account, as_of_date=date.today())
        return ctx

class PurchaseInvoiceListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = PurchaseInvoice
    template_name = 'purchases/invoices/list.html'
    context_object_name = 'invoices'
    permission_required = 'purchases.view_purchaseinvoice'
    ordering = ['-date', '-id']
    paginate_by = 50

    def get_queryset(self):
        return super().get_queryset().select_related('supplier')

class PurchaseInvoiceCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = PurchaseInvoice
    form_class = PurchaseInvoiceForm
    template_name = 'purchases/invoices/form.html'
    permission_required = 'purchases.add_purchaseinvoice'
    success_url = reverse_lazy('purchases:invoice-list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['lines'] = PurchaseInvoiceLineFormSet(self.request.POST)
        else:
            data['lines'] = PurchaseInvoiceLineFormSet()
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        lines = context['lines']
        with transaction.atomic():
            form.instance.subtotal = 0
            form.instance.total = 0
            form.instance.created_by = self.request.user
            if lines.is_valid():
                self.object = form.save()
                lines.instance = self.object
                instances = lines.save(commit=False)
                
                gross_total = Decimal('0')
                discount_total = Decimal('0')
                tax_total_added = Decimal('0')
                tax_total_deducted = Decimal('0')
                
                for instance in instances:
                    line_subtotal = Decimal(str(instance.quantity * instance.unit_cost))
                    line_discount = line_subtotal * (Decimal(str(instance.discount_percent)) / Decimal('100'))
                    net_line = line_subtotal - line_discount
                    
                    res = calculate_line_taxes(
                        net_line,
                        instance.tax_type,
                        instance.tax_percent,
                        instance.tax_type2,
                        instance.tax_percent2,
                        is_purchase_or_expense=True
                    )
                    
                    instance.total = net_line + res['tax1_signed'] + res['tax2_signed']
                    # Calculate base quantity
                    if instance.unit:
                        instance.base_quantity = instance.item.convert_to_base(instance.quantity, instance.unit)
                    else:
                        instance.base_quantity = instance.quantity
                    instance.save()
                    
                    gross_total += line_subtotal
                    discount_total += line_discount
                    tax_total_added += res['tax_total_added']
                    tax_total_deducted += res['tax_total_deducted']

                self.object.subtotal = gross_total
                self.object.discount_amount = discount_total
                self.object.tax_amount = tax_total_added - tax_total_deducted
                self.object.total = gross_total - discount_total + tax_total_added - tax_total_deducted
                self.object.save()
            else:
                return self.form_invalid(form)
        return redirect(self.success_url)

class PurchaseInvoiceDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = PurchaseInvoice
    template_name = 'purchases/invoices/detail.html'
    context_object_name = 'invoice'
    permission_required = 'purchases.view_purchaseinvoice'

    def get_queryset(self):
        return super().get_queryset().select_related('supplier', 'cost_center', 'purchase_order').prefetch_related('lines__item', 'lines__unit')

class PurchaseInvoicePostView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'purchases.change_purchaseinvoice'
    
    def post(self, request, pk):
        invoice = get_object_or_404(PurchaseInvoice, pk=pk)
        try:
            PurchaseService.post_invoice(invoice, request.user)
            messages.success(request, f'تم ترحيل فاتورة المشتريات {invoice.number}')
        except Exception as e:
            logger.exception('Error posting purchase invoice %s', invoice.number)
            messages.error(request, f'خطأ: {e}')
        return redirect('purchases:invoice-detail', pk=pk)

class PurchaseInvoiceReverseView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'purchases.change_purchaseinvoice'
    
    def post(self, request, pk):
        with transaction.atomic():
            invoice = get_object_or_404(PurchaseInvoice.objects.select_for_update(), pk=pk)
            if invoice.status == PurchaseInvoice.Status.DRAFT:
                invoice.paid_amount = Decimal('0')
                invoice.status = PurchaseInvoice.Status.CANCELLED
                invoice.save()
                messages.success(request, f"تم إلغاء الفاتورة {invoice.number} (مسودة)")
                SystemNotification.notify_accountants(
                    title="إلغاء فاتورة مشتريات",
                    message=f"قام {request.user.username} بإلغاء فاتورة المشتريات رقم {invoice.number} للمورد {invoice.supplier.name} بقيمة {invoice.total:.2f} ج.م.",
                    url=reverse('purchases:invoice-detail', args=[invoice.id])
                )
            elif invoice.status == PurchaseInvoice.Status.POSTED:
                try:
                    PurchaseService.reverse_invoice(invoice, request.user)
                    messages.success(request, f"تم عكس الفاتورة {invoice.number} وإنشاء قيد عكسي")
                    SystemNotification.notify_accountants(
                        title="عكس فاتورة مشتريات",
                        message=f"قام {request.user.username} بعكس فاتورة المشتريات رقم {invoice.number} للمورد {invoice.supplier.name} بقيمة {invoice.total:.2f} ج.م.",
                        url=reverse('purchases:invoice-detail', args=[invoice.id])
                    )
                except Exception as e:
                    logger.exception('Error reversing purchase invoice %s', invoice.number)
                    messages.error(request, f"خطأ أثناء العكس: {e}")
            else:
                messages.warning(request, "لا يمكن عكس هذه الفاتورة")
            
        return redirect('purchases:invoice-detail', pk=pk)

class SupplierPaymentListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = SupplierPayment
    template_name = 'purchases/payments/list.html'
    context_object_name = 'payments'
    permission_required = 'purchases.view_supplierpayment'
    paginate_by = 50

    def get_queryset(self):
        return super().get_queryset().select_related('supplier')

class SupplierPaymentCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = SupplierPayment
    form_class = SupplierPaymentForm
    template_name = 'purchases/payments/form.html'
    success_url = reverse_lazy('purchases:payment-list')
    permission_required = 'purchases.add_supplierpayment'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        with transaction.atomic():
            form.instance.created_by = self.request.user
            self.object = form.save()

            selected_invoices = form.cleaned_data.get('invoices', [])
            if selected_invoices:
                total_allocated = Decimal('0')
                # Re-fetch with row lock to prevent race conditions
                locked_invoices = PurchaseInvoice.objects.filter(
                    pk__in=[inv.pk for inv in selected_invoices]
                ).select_for_update()
                for inv in locked_invoices:
                    if total_allocated >= self.object.amount:
                        break
                    remaining = inv.total - inv.paid_amount
                    alloc_amount = min(remaining, self.object.amount - total_allocated)
                    if alloc_amount > 0:
                        PaymentAllocation.objects.create(
                            payment=self.object,
                            invoice=inv,
                            amount=alloc_amount,
                        )
                        inv.paid_amount += alloc_amount
                        inv.save(update_fields=['paid_amount'])
                        total_allocated += alloc_amount

            PurchaseService.record_payment(self.object, self.request.user)
            messages.success(self.request, f'تم تسجيل سند الصرف {self.object.number} وترحيله')

        return redirect(self.success_url)

class SupplierPaymentDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = SupplierPayment
    template_name = 'purchases/payments/detail.html'
    context_object_name = 'payment'
    permission_required = 'purchases.view_supplierpayment'

    def get_queryset(self):
        return super().get_queryset().select_related('supplier', 'cash_box', 'bank_account')
