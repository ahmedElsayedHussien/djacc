from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.db import transaction
from django.views import View
from .models import Supplier, PurchaseInvoice, PurchaseInvoiceLine, SupplierPayment, PurchaseReturn, PurchaseReturnLine
from .forms import SupplierForm, PurchaseInvoiceForm, PurchaseInvoiceLineFormSet, SupplierPaymentForm, PurchaseReturnForm, PurchaseReturnLineFormSet
from .services import SupplierService, PurchaseService

class PurchaseReturnListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = PurchaseReturn
    template_name = 'purchases/returns/list.html'
    context_object_name = 'returns'
    permission_required = 'purchases.view_purchasereturn'
    ordering = ['-date', '-id']
    paginate_by = 50

class PurchaseReturnCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
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
            from apps.core.services import DocumentService
            form.instance.number = DocumentService.generate_number(PurchaseReturn, 'PRET')
            
            form.instance.subtotal = 0
            form.instance.total = 0
            self.object = form.save()
            
            try:
                if lines.is_valid():
                    lines.instance = self.object
                    lines.save()
                    
                    # ... (rest of the logic inside the previous block)
                    # I will replace the whole block to be safe
                    gross_total = 0
                    discount_total = 0
                    tax_total_added = 0
                    tax_total_deducted = 0
                    
                    for line in self.object.lines.all():
                        # ✅ Fix: Quantity validation against original invoice
                        if self.object.invoice:
                            from django.db.models import Sum
                            original_line = self.object.invoice.lines.filter(item=line.item).first()
                            if not original_line:
                                raise ValueError(f"الصنف {line.item.name} غير موجود في الفاتورة الأصلية")
                            
                            previous_returned = PurchaseReturnLine.objects.filter(
                                purchase_return__invoice=self.object.invoice,
                                purchase_return__status='posted',
                                item=line.item
                            ).aggregate(total=Sum('quantity'))['total'] or 0
                            
                            available = original_line.quantity - previous_returned
                            if line.quantity > available:
                                raise ValueError(
                                    f"الكمية المرتجعة للصنف {line.item.name} ({line.quantity}) "
                                    f"تتجاوز الكمية المتاحة للإرجاع ({available})"
                                )

                        line_subtotal = line.quantity * line.unit_cost
                        line_discount = line_subtotal * (line.discount_percent / 100)
                        net_line = line_subtotal - line_discount
                        
                        tax1 = net_line * (line.tax_percent / 100)
                        if line.tax_type and line.tax_type.category in ['wht', 'salary', 'insurance']:
                            tax_total_deducted += tax1
                            tax1_signed = -tax1
                        else:
                            tax_total_added += tax1
                            tax1_signed = tax1

                        tax2 = net_line * (line.tax_percent2 / 100)
                        if line.tax_type2 and line.tax_type2.category in ['wht', 'salary', 'insurance']:
                            tax_total_deducted += tax2
                            tax2_signed = -tax2
                        else:
                            tax_total_added += tax2
                            tax2_signed = tax2
                        
                        line.total = net_line + tax1_signed + tax2_signed
                        if hasattr(line, 'unit') and line.unit:
                            line.base_quantity = line.item.convert_to_base(line.quantity, line.unit)
                        else:
                            line.base_quantity = line.quantity
                        line.save()
                        
                        gross_total += line_subtotal
                        discount_total += line_discount

                    self.object.subtotal = gross_total
                    self.object.discount_amount = discount_total
                    self.object.tax_amount = tax_total_added - tax_total_deducted
                    self.object.total = gross_total - discount_total + tax_total_added - tax_total_deducted
                    self.object.save()
                else:
                    return self.form_invalid(form)
            except ValueError as e:
                messages.error(self.request, str(e))
                transaction.set_rollback(True)
                return self.form_invalid(form)
        return redirect(self.success_url)

class PurchaseReturnDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = PurchaseReturn
    template_name = 'purchases/returns/detail.html'
    context_object_name = 'purchase_return'
    permission_required = 'purchases.view_purchasereturn'

class PurchaseReturnPostView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'purchases.change_purchasereturn'
    
    def post(self, request, pk):
        purchase_return = get_object_or_404(PurchaseReturn, pk=pk)
        try:
            PurchaseService.post_return(purchase_return, request.user)
            messages.success(request, f'تم ترحيل مرتجع المشتريات {purchase_return.number}')
        except Exception as e:
            messages.error(request, f'خطأ: {e}')
        return redirect('purchases:return-detail', pk=pk)


class SupplierListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
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

class SupplierCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Supplier
    form_class = SupplierForm
    template_name = 'purchases/suppliers/form.html'
    permission_required = 'purchases.add_supplier'
    success_url = reverse_lazy('purchases:supplier-list')

    def form_valid(self, form):
        supplier = SupplierService.create_supplier(form.cleaned_data)
        messages.success(self.request,
            f'تم إنشاء المورد "{supplier.name}" — كود الحساب: {supplier.account.code}')
        return redirect(self.success_url)

class SupplierUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Supplier
    form_class = SupplierForm
    template_name = 'purchases/suppliers/form.html'
    permission_required = 'purchases.change_supplier'
    success_url = reverse_lazy('purchases:supplier-list')

    def form_valid(self, form):
        SupplierService.update_supplier(self.object, form.cleaned_data)
        messages.success(self.request, 'تم تحديث بيانات المورد بنجاح')
        return redirect(self.success_url)

class SupplierDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Supplier
    template_name = 'purchases/suppliers/detail.html'
    permission_required = 'purchases.view_supplier'

    def get_context_data(self, **kwargs):
        from apps.core.utils import get_account_balance
        from datetime import date
        ctx = super().get_context_data(**kwargs)
        ctx['invoices'] = self.object.purchaseinvoice_set.order_by('-date')[:10]
        ctx['balance'] = get_account_balance(self.object.account, as_of_date=date.today())
        return ctx

class PurchaseInvoiceListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = PurchaseInvoice
    template_name = 'purchases/invoices/list.html'
    context_object_name = 'invoices'
    permission_required = 'purchases.view_purchaseinvoice'
    ordering = ['-date', '-id']
    paginate_by = 50

class PurchaseInvoiceCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = PurchaseInvoice
    form_class = PurchaseInvoiceForm
    template_name = 'purchases/invoices/form.html'
    permission_required = 'purchases.add_purchaseinvoice'
    success_url = reverse_lazy('purchases:invoice-list')

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
            from apps.core.services import DocumentService
            form.instance.number = DocumentService.generate_number(PurchaseInvoice, 'PINV')
            form.instance.subtotal = 0
            form.instance.total = 0
            form.instance.created_by = self.request.user
            self.object = form.save()
            
            if lines.is_valid():
                lines.instance = self.object
                lines.save()
                
                # Calculate totals (Egyptian Tax Compliance)
                gross_total = 0
                discount_total = 0
                tax_total_added = 0      # VAT, Table, Customs, Stamp
                tax_total_deducted = 0   # WHT, Salary, Insurance
                
                for line in self.object.lines.all():
                    line_subtotal = line.quantity * line.unit_cost
                    line_discount = line_subtotal * (line.discount_percent / 100)
                    net_line = line_subtotal - line_discount
                    
                    # Tax 1
                    tax1 = net_line * (line.tax_percent / 100)
                    if line.tax_type and line.tax_type.category in ['wht', 'salary', 'insurance']:
                        tax_total_deducted += tax1
                        tax1_signed = -tax1
                    else:
                        tax_total_added += tax1
                        tax1_signed = tax1

                    # Tax 2
                    tax2 = net_line * (line.tax_percent2 / 100)
                    if line.tax_type2 and line.tax_type2.category in ['wht', 'salary', 'insurance']:
                        tax_total_deducted += tax2
                        tax2_signed = -tax2
                    else:
                        tax_total_added += tax2
                        tax2_signed = tax2
                    
                    line.total = net_line + tax1_signed + tax2_signed
                    # Calculate base quantity
                    if line.unit:
                        line.base_quantity = line.item.convert_to_base(line.quantity, line.unit)
                    else:
                        line.base_quantity = line.quantity
                    line.save()
                    
                    gross_total += line_subtotal
                    discount_total += line_discount

                self.object.subtotal = gross_total
                self.object.discount_amount = discount_total
                self.object.tax_amount = tax_total_added - tax_total_deducted
                self.object.total = gross_total - discount_total + tax_total_added - tax_total_deducted
                self.object.save()
            else:
                return self.form_invalid(form)
        return redirect(self.success_url)

class PurchaseInvoiceDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = PurchaseInvoice
    template_name = 'purchases/invoices/detail.html'
    context_object_name = 'invoice'
    permission_required = 'purchases.view_purchaseinvoice'

class PurchaseInvoicePostView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'purchases.change_purchaseinvoice'
    
    def post(self, request, pk):
        invoice = get_object_or_404(PurchaseInvoice, pk=pk)
        try:
            PurchaseService.post_invoice(invoice, request.user)
            messages.success(request, f'تم ترحيل فاتورة المشتريات {invoice.number}')
        except Exception as e:
            messages.error(request, f'خطأ: {e}')
        return redirect('purchases:invoice-detail', pk=pk)

class PurchaseInvoiceReverseView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'purchases.change_purchaseinvoice'
    
    def post(self, request, pk):
        invoice = get_object_or_404(PurchaseInvoice, pk=pk)
        if invoice.status == PurchaseInvoice.Status.DRAFT:
            invoice.status = PurchaseInvoice.Status.CANCELLED
            invoice.save()
            messages.success(request, f"تم إلغاء الفاتورة {invoice.number} (مسودة)")
        elif invoice.status == PurchaseInvoice.Status.POSTED:
            try:
                PurchaseService.reverse_invoice(invoice, request.user)
                messages.success(request, f"تم عكس الفاتورة {invoice.number} وإنشاء قيد عكسي")
            except Exception as e:
                messages.error(request, f"خطأ أثناء العكس: {e}")
        else:
            messages.warning(request, "لا يمكن عكس هذه الفاتورة")
            
        return redirect('purchases:invoice-detail', pk=pk)

class SupplierPaymentListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = SupplierPayment
    template_name = 'purchases/payments/list.html'
    context_object_name = 'payments'
    permission_required = 'purchases.view_supplierpayment'
    paginate_by = 50

class SupplierPaymentCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = SupplierPayment
    form_class = SupplierPaymentForm
    template_name = 'purchases/payments/form.html'
    success_url = reverse_lazy('purchases:payment-list')
    permission_required = 'purchases.add_supplierpayment'

    def form_valid(self, form):
        with transaction.atomic():
            from apps.core.services import DocumentService
            form.instance.number = DocumentService.generate_number(SupplierPayment, 'PAY')
            form.instance.created_by = self.request.user
            self.object = form.save()
            
            # This will now rollback if it fails
            PurchaseService.record_payment(self.object, self.request.user)
            messages.success(self.request, f'تم تسجيل سند الصرف {self.object.number} وترحيله')
            
        return redirect(self.success_url)

class SupplierPaymentDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = SupplierPayment
    template_name = 'purchases/payments/detail.html'
    context_object_name = 'payment'
    permission_required = 'purchases.view_supplierpayment'
