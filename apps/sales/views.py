from decimal import Decimal
from datetime import date as date_type
from django.views.generic import ListView, CreateView, UpdateView, DetailView, DeleteView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.db import transaction
from django.db.models import Sum
from django.views import View
from .models import (
    Customer, CustomerSector, SalesInvoice, SalesInvoiceLine, 
    CustomerReceipt, SalesRepresentative, SalesReturn, Quotation, 
    QuotationLine, PriceList, PriceListItem, RepDailySettlement, RepSettlementInvoice
)
from .forms import (
    CustomerForm, SalesInvoiceForm, SalesInvoiceLineFormSet, 
    CustomerReceiptForm, SalesRepresentativeForm, SalesReturnLineFormSet,
    QuotationForm, QuotationLineFormSet, PriceListForm, PriceListItemFormSet,
    CustomerSectorForm
)
from .services import CustomerService, SalesRepresentativeService, SalesService, RepSettlementService

class QuotationListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Quotation
    template_name = 'sales/quotations/list.html'
    context_object_name = 'quotations'
    permission_required = 'sales.view_quotation'
    ordering = ['-id']

class QuotationCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Quotation
    form_class = QuotationForm
    template_name = 'sales/quotations/form.html'
    permission_required = 'sales.add_quotation'
    success_url = reverse_lazy('sales:quotation-list')

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['lines'] = QuotationLineFormSet(self.request.POST)
        else:
            data['lines'] = QuotationLineFormSet()
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        lines = context['lines']
        
        is_valid = False
        with transaction.atomic():
            form.instance.created_by = self.request.user
            if not form.instance.number:
                from apps.core.services import DocumentService
                form.instance.number = DocumentService.generate_number(Quotation, 'OFFR')
            
            self.object = form.save()
            
            if lines.is_valid():
                lines.instance = self.object
                lines.save()
                is_valid = True
            else:
                transaction.set_rollback(True)
                
        if is_valid:
            messages.success(self.request, f"تم إنشاء العرض {self.object.name} بنجاح")
            return redirect('sales:quotation-list')
        else:
            messages.error(self.request, "يوجد خطأ في بيانات الأصناف المرفقة بالعرض. يرجى مراجعتها.")
            return self.form_invalid(form)

    def form_invalid(self, form):
        if not self.request.POST.getlist('lines-0-item'): # Just a general check, but we'll show message anyway
            messages.error(self.request, "يرجى التأكد من إدخال جميع الحقول الإلزامية بشكل صحيح.")
        return super().form_invalid(form)

class QuotationUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Quotation
    form_class = QuotationForm
    template_name = 'sales/quotations/form.html'
    permission_required = 'sales.change_quotation'
    success_url = reverse_lazy('sales:quotation-list')

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['lines'] = QuotationLineFormSet(self.request.POST, instance=self.object)
        else:
            data['lines'] = QuotationLineFormSet(instance=self.object)
        return data

    def form_valid(self, form):
        if self.object.status in [Quotation.Status.INVOICED, Quotation.Status.CANCELLED]:
            messages.error(self.request, "لا يمكن تعديل عرض سعر ملغي أو محول لفاتورة.")
            return redirect('sales:quotation-detail', pk=self.object.pk)

        context = self.get_context_data()
        lines = context['lines']
        
        is_valid = False
        with transaction.atomic():
            self.object = form.save()
            if lines.is_valid():
                lines.instance = self.object
                lines.save()
                is_valid = True
            else:
                transaction.set_rollback(True)
                
        if is_valid:
            messages.success(self.request, f"تم تحديث العرض {self.object.name} بنجاح")
            return redirect('sales:quotation-list')
        else:
            messages.error(self.request, "يوجد خطأ في بيانات الأصناف المرفقة بالعرض. يرجى مراجعتها.")
            return self.form_invalid(form)

    def form_invalid(self, form):
        messages.error(self.request, "يرجى التأكد من إدخال جميع الحقول الإلزامية بشكل صحيح.")
        return super().form_invalid(form)

class QuotationCancelView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'sales.change_quotation'
    def post(self, request, pk):
        quotation = get_object_or_404(Quotation, pk=pk)
        quotation.status = 'cancelled'
        quotation.save()
        messages.success(request, f"تم إلغاء عرض السعر {quotation.name}")
        return redirect('sales:quotation-list')

class QuotationDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Quotation
    template_name = 'sales/quotations/detail.html'
    context_object_name = 'quotation'
    permission_required = 'sales.view_quotation'

class CustomerSectorListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = CustomerSector
    template_name = 'sales/sectors/list.html'
    context_object_name = 'sectors'
    permission_required = 'sales.view_customersector'

class CustomerSectorCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = CustomerSector
    form_class = CustomerSectorForm
    template_name = 'sales/sectors/form.html'
    permission_required = 'sales.add_customersector'
    success_url = reverse_lazy('sales:sector-list')

    def form_valid(self, form):
        messages.success(self.request, "تم إنشاء القطاع بنجاح")
        return super().form_valid(form)

class CustomerSectorUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = CustomerSector
    form_class = CustomerSectorForm
    template_name = 'sales/sectors/form.html'
    permission_required = 'sales.change_customersector'
    success_url = reverse_lazy('sales:sector-list')

    def form_valid(self, form):
        messages.success(self.request, "تم تحديث القطاع بنجاح")
        return super().form_valid(form)

class PriceListListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = PriceList
    template_name = 'sales/price_lists/list.html'
    context_object_name = 'price_lists'
    permission_required = 'sales.view_pricelist'

class PriceListCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = PriceList
    form_class = PriceListForm
    template_name = 'sales/price_lists/form.html'
    permission_required = 'sales.add_pricelist'
    success_url = reverse_lazy('sales:pricelist-list')

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['items'] = PriceListItemFormSet(self.request.POST)
        else:
            data['items'] = PriceListItemFormSet()
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        items = context['items']
        
        is_valid = False
        with transaction.atomic():
            self.object = form.save()
            if items.is_valid():
                items.instance = self.object
                items.save()
                is_valid = True
            else:
                transaction.set_rollback(True)
                
        if is_valid:
            messages.success(self.request, f"تم إنشاء قائمة الأسعار {self.object.name} بنجاح")
            return redirect('sales:pricelist-list')
        else:
            return self.form_invalid(form)

class PriceListUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = PriceList
    form_class = PriceListForm
    template_name = 'sales/price_lists/form.html'
    permission_required = 'sales.change_pricelist'
    success_url = reverse_lazy('sales:pricelist-list')

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['items'] = PriceListItemFormSet(self.request.POST, instance=self.object)
        else:
            data['items'] = PriceListItemFormSet(instance=self.object)
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        items = context['items']
        
        is_valid = False
        with transaction.atomic():
            self.object = form.save()
            if items.is_valid():
                items.instance = self.object
                items.save()
                is_valid = True
            else:
                transaction.set_rollback(True)
                
        if is_valid:
            messages.success(self.request, f"تم تحديث قائمة الأسعار {self.object.name} بنجاح")
            return redirect('sales:pricelist-list')
        else:
            return self.form_invalid(form)

class PriceListDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'sales.change_pricelist'
    def post(self, request, pk):
        pricelist = get_object_or_404(PriceList, pk=pk)
        pricelist.is_active = False
        pricelist.save()
        messages.success(request, f"تم إيقاف قائمة الأسعار {pricelist.name}")
        return redirect('sales:pricelist-list')

class QuotationConvertToInvoiceView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'sales.add_salesinvoice'

    def post(self, request, pk):
        quotation = get_object_or_404(Quotation, pk=pk)
        if quotation.status == Quotation.Status.INVOICED:
            messages.warning(request, "هذا العرض تم تحويله بالفعل لفاتورة")
            return redirect('sales:quotation-detail', pk=pk)
        
        try:
            with transaction.atomic():
                # Create Invoice
                from apps.core.services import DocumentService
                invoice = SalesInvoice.objects.create(
                    number=DocumentService.generate_number(SalesInvoice, 'SINV'),
                    date=date.today(),
                    customer=quotation.customer,
                    sales_rep=quotation.sales_rep,
                    due_date=date.today(),
                    subtotal=quotation.subtotal,
                    discount_amount=quotation.discount_amount,
                    tax_amount=quotation.tax_amount,
                    total=quotation.total,
                    created_by=request.user,
                    notes=f"محول من عرض سعر رقم {quotation.number}"
                )
                
                # Create Lines
                from apps.core.models import Account
                from django.conf import settings
                default_sales_acc = Account.objects.get(code=getattr(settings, 'DEFAULT_SALES_ACCOUNT', '411'))

                from apps.inventory.services import InventoryService
                for q_line in quotation.lines.all():
                    warehouse = quotation.sales_rep.warehouse if (quotation.sales_rep and quotation.sales_rep.warehouse) else None
                    cost = InventoryService.get_item_cost(q_line.item, warehouse) if warehouse else 0
                    
                    # Calculate base quantity
                    base_qty = q_line.quantity
                    if hasattr(q_line, 'unit') and q_line.unit:
                        base_qty = q_line.item.convert_to_base(q_line.quantity, q_line.unit)

                    SalesInvoiceLine.objects.create(
                        invoice=invoice,
                        item=q_line.item,
                        warehouse=warehouse,
                        unit=getattr(q_line, 'unit', None),
                        quantity=q_line.quantity,
                        base_quantity=base_qty,
                        unit_price=q_line.unit_price,
                        discount_percent=q_line.discount_percent,
                        tax_type=q_line.tax_type,
                        tax_percent=q_line.tax_percent,
                        total=q_line.total,
                        cost=cost,
                        revenue_account=q_line.item.sales_account or default_sales_acc,
                        cost_of_goods_account=q_line.item.cogs_account
                    )
                
                quotation.status = Quotation.Status.INVOICED
                quotation.save()
                
                messages.success(request, f"تم تحويل عرض السعر لفاتورة بنجاح: {invoice.number}")
                return redirect('sales:invoice-detail', pk=invoice.pk)
        except Exception as e:
            messages.error(request, f"خطأ أثناء التحويل: {e}")
            return redirect('sales:quotation-detail', pk=pk)

from apps.core.models import JournalLine
from datetime import datetime, date

class CustomerListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Customer
    template_name = 'sales/customers/list.html'
    context_object_name = 'customers'
    permission_required = 'sales.view_customer'
    paginate_by = 25

    def get_queryset(self):
        qs = Customer.objects.select_related('account').order_by('code')
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(name__icontains=q) | qs.filter(code__icontains=q)
        return qs

class CustomerCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'sales/customers/form.html'
    permission_required = 'sales.add_customer'
    success_url = reverse_lazy('sales:customer-list')

    def form_valid(self, form):
        try:
            customer = CustomerService.create_customer(form.cleaned_data)
            messages.success(
                self.request,
                f'تم إنشاء العميل "{customer.name}" بنجاح — كود الحساب: {customer.account.code}'
            )
            from django.shortcuts import redirect
            return redirect(self.success_url)
        except Exception as e:
            messages.error(self.request, f'خطأ: {e}')
            return self.form_invalid(form)

class CustomerUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'sales/customers/form.html'
    permission_required = 'sales.change_customer'
    success_url = reverse_lazy('sales:customer-list')

    def form_valid(self, form):
        CustomerService.update_customer(self.object, form.cleaned_data)
        messages.success(self.request, 'تم تحديث بيانات العميل بنجاح')
        from django.shortcuts import redirect
        return redirect(self.success_url)

class CustomerDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Customer
    template_name = 'sales/customers/detail.html'
    permission_required = 'sales.view_customer'

    def get_context_data(self, **kwargs):
        from apps.core.utils import get_account_balance
        from datetime import date
        ctx = super().get_context_data(**kwargs)
        ctx['invoices'] = self.object.salesinvoice_set.order_by('-date')[:10]
        ctx['balance'] = get_account_balance(self.object.account) if self.object.account else 0
        return ctx

# --- Sales Representative Views ---

class SalesRepresentativeListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'sales.view_salesrepresentative'
    model = SalesRepresentative
    template_name = 'sales/reps/list.html'
    context_object_name = 'reps'

class SalesRepresentativeDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = 'sales.view_salesrepresentative'
    model = SalesRepresentative
    template_name = 'sales/reps/detail.html'
    context_object_name = 'rep'

class SalesRepresentativeCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'sales.add_salesrepresentative'
    model = SalesRepresentative
    form_class = SalesRepresentativeForm
    template_name = 'sales/reps/form.html'
    success_url = reverse_lazy('sales:rep-list')

    def form_valid(self, form):
        self.object = SalesRepresentativeService.create_rep(form.cleaned_data)
        return redirect(self.success_url)

class SalesRepresentativeUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'sales.change_salesrepresentative'
    model = SalesRepresentative
    form_class = SalesRepresentativeForm
    template_name = 'sales/reps/form.html'
    success_url = reverse_lazy('sales:rep-list')

class SalesInvoiceListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = SalesInvoice
    template_name = 'sales/invoices/list.html'
    context_object_name = 'invoices'

    ordering = ['-date', '-id']
    permission_required = 'sales.view_salesinvoice'

    def get_queryset(self):
        qs = super().get_queryset().select_related('customer')
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(number__icontains=q) | qs.filter(customer__name__icontains=q)
        return qs

class SalesInvoiceCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = SalesInvoice
    form_class = SalesInvoiceForm
    template_name = 'sales/invoices/form.html'
    permission_required = 'sales.add_salesinvoice'
    success_url = reverse_lazy('sales:invoice-list')

    def get_initial(self):
        initial = super().get_initial()
        if hasattr(self.request.user, 'salesrepresentative'):
            initial['sales_rep'] = self.request.user.salesrepresentative
        return initial

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        from apps.sales.models import SalesRepresentative
        reps = SalesRepresentative.objects.select_related('warehouse')
        data['rep_warehouse_mapping'] = {rep.id: rep.warehouse.id for rep in reps if rep.warehouse}
        if self.request.POST:
            data['lines'] = SalesInvoiceLineFormSet(self.request.POST)
        else:
            data['lines'] = SalesInvoiceLineFormSet()
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        lines = context['lines']
        
        is_valid = False
        with transaction.atomic():
            form.instance.created_by = self.request.user
            from apps.core.services import DocumentService
            form.instance.number = DocumentService.generate_number(SalesInvoice, 'SINV')
            
            form.instance.subtotal = 0
            form.instance.total = 0
            self.object = form.save()
            
            if lines.is_valid():
                from apps.core.models import Account
                from django.conf import settings
                default_sales_acc = Account.objects.get(code=getattr(settings, 'DEFAULT_SALES_ACCOUNT', '411'))

                lines.instance = self.object
                instances = lines.save(commit=False)
                from apps.inventory.services import InventoryService
                for instance in instances:
                    instance.revenue_account = instance.item.sales_account or default_sales_acc
                    instance.cost_of_goods_account = instance.item.cogs_account
                    # Store current cost for accurate COGS tracking
                    instance.cost = InventoryService.get_item_cost(instance.item, instance.warehouse)
                    
                    # ✅ Fix: Calculate base quantity
                    if instance.unit:
                        instance.base_quantity = instance.item.convert_to_base(instance.quantity, instance.unit)
                    else:
                        instance.base_quantity = instance.quantity
                        
                    instance.save()
                
                # Also handle deleted lines if any
                for obj in lines.deleted_objects:
                    obj.delete()

                # Calculate totals from lines
                gross_total = 0
                discount_total = 0
                tax_total_added = 0      # VAT, Table, etc.
                tax_total_deducted = 0   # WHT, etc.
                
                for line in self.object.lines.all():
                    gross_line = line.quantity * line.unit_price
                    disc_line = gross_line * (line.discount_percent / 100)
                    net_line = gross_line - disc_line
                    
                    # Tax 1 logic
                    tax1 = net_line * (line.tax_percent / 100)
                    if line.tax_type and line.tax_type.category in ['wht', 'salary', 'insurance']:
                        tax_total_deducted += tax1
                        tax1_signed = -tax1
                    else:
                        tax_total_added += tax1
                        tax1_signed = tax1

                    # Tax 2 logic
                    tax2 = net_line * (line.tax_percent2 / 100)
                    if line.tax_type2 and line.tax_type2.category in ['wht', 'salary', 'insurance']:
                        tax_total_deducted += tax2
                        tax2_signed = -tax2
                    else:
                        tax_total_added += tax2
                        tax2_signed = tax2
                    
                    # Update line total in DB (Net + Additions - Deductions)
                    line.total = net_line + tax1_signed + tax2_signed
                    line.save()
                    
                    gross_total += gross_line
                    discount_total += disc_line

                self.object.subtotal = gross_total
                self.object.discount_amount = discount_total
                self.object.tax_amount = tax_total_added - tax_total_deducted
                self.object.total = gross_total - discount_total + tax_total_added - tax_total_deducted
                self.object.save()
                is_valid = True
            else:
                transaction.set_rollback(True)
                
        if is_valid:
            messages.success(self.request, f"تم حفظ فاتورة المبيعات {self.object.number} بنجاح (مسودة)")
            return redirect('sales:invoice-list')
        else:
            return self.form_invalid(form)

class SalesInvoiceUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = SalesInvoice
    form_class = SalesInvoiceForm
    template_name = 'sales/invoices/form.html'
    success_url = reverse_lazy('sales:invoice-list')
    permission_required = 'sales.change_salesinvoice'

    def get_queryset(self):
        # Only allow editing draft invoices
        return super().get_queryset().filter(status='draft')

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['lines'] = SalesInvoiceLineFormSet(self.request.POST, instance=self.object)
        else:
            data['lines'] = SalesInvoiceLineFormSet(instance=self.object)
        return data

    def form_valid(self, form):
        if self.object.status != SalesInvoice.Status.DRAFT:
            messages.error(self.request, "لا يمكن تعديل فاتورة غير مسودة. يرجى عكسها أولاً.")
            return redirect('sales:invoice-detail', pk=self.object.pk)

        context = self.get_context_data()
        lines = context['lines']
        
        is_valid = False
        with transaction.atomic():
            if lines.is_valid():
                self.object = form.save()
                lines.instance = self.object
                lines.save()
                
                # Calculate totals from lines (Standardized logic)
                gross_total = 0
                discount_total = 0
                tax_total_added = 0
                tax_total_deducted = 0
                
                for line in self.object.lines.all():
                    # ✅ Fix: Calculate base quantity on update
                    if line.unit:
                        line.base_quantity = line.item.convert_to_base(line.quantity, line.unit)
                    else:
                        line.base_quantity = line.quantity

                    gross_line = line.quantity * line.unit_price
                    disc_line = gross_line * (line.discount_percent / 100)
                    net_line = gross_line - disc_line
                    
                    # Tax logic ... (rest is same)
                    
                    # Tax 1 logic
                    tax1 = net_line * (line.tax_percent / 100)
                    if line.tax_type and line.tax_type.category in ['wht', 'salary', 'insurance']:
                        tax_total_deducted += tax1
                        tax1_signed = -tax1
                    else:
                        tax_total_added += tax1
                        tax1_signed = tax1

                    # Tax 2 logic
                    tax2 = net_line * (line.tax_percent2 / 100)
                    if line.tax_type2 and line.tax_type2.category in ['wht', 'salary', 'insurance']:
                        tax_total_deducted += tax2
                        tax2_signed = -tax2
                    else:
                        tax_total_added += tax2
                        tax2_signed = tax2
                    
                    # Update line in DB (Total + Base Quantity)
                    line.total = net_line + tax1_signed + tax2_signed
                    line.save()
                    
                    gross_total += gross_line
                    discount_total += disc_line

                self.object.subtotal = gross_total
                self.object.discount_amount = discount_total
                self.object.tax_amount = tax_total_added - tax_total_deducted
                self.object.total = gross_total - discount_total + tax_total_added - tax_total_deducted
                self.object.save()
                is_valid = True
            else:
                transaction.set_rollback(True)
                
        if is_valid:
            messages.success(self.request, f"تم تحديث الفاتورة {self.object.number} بنجاح")
            return redirect('sales:invoice-list')
        else:
            return self.form_invalid(form)

class SalesInvoiceReverseView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'sales.change_salesinvoice'
    
    def post(self, request, pk):
        invoice = get_object_or_404(SalesInvoice, pk=pk)
        if invoice.status == SalesInvoice.Status.DRAFT:
            invoice.status = SalesInvoice.Status.CANCELLED
            invoice.save()
            messages.success(request, f"تم إلغاء الفاتورة {invoice.number} (مسودة)")
        elif invoice.status == SalesInvoice.Status.POSTED:
            try:
                SalesService.reverse_invoice(invoice, request.user)
                messages.success(request, f"تم عكس الفاتورة {invoice.number} وإنشاء قيد عكسي")
            except Exception as e:
                messages.error(request, f"خطأ أثناء العكس: {e}")
        else:
            messages.warning(request, "لا يمكن عكس هذه الفاتورة")
            
        return redirect('sales:invoice-detail', pk=pk)

class SalesInvoicePostView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'sales.change_salesinvoice'
    
    def post(self, request, pk):
        invoice = get_object_or_404(SalesInvoice, pk=pk)
        try:
            SalesService.post_invoice(invoice, request.user)
            messages.success(request, f'تم ترحيل الفاتورة {invoice.number} بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ أثناء الترحيل: {e}')
        return redirect('sales:invoice-list')

class CustomerReceiptListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = CustomerReceipt
    template_name = 'sales/receipts/list.html'
    context_object_name = 'receipts'
    permission_required = 'sales.view_customerreceipt'

class CustomerReceiptCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = CustomerReceipt
    form_class = CustomerReceiptForm
    template_name = 'sales/receipts/form.html'
    success_url = reverse_lazy('sales:receipt-list')
    permission_required = 'sales.add_customerreceipt'

    def form_valid(self, form):
        with transaction.atomic():
            from apps.core.services import DocumentService
            form.instance.number = DocumentService.generate_number(CustomerReceipt, 'RCPT')
            form.instance.created_by = self.request.user
            self.object = form.save()
            
            SalesService.record_receipt(self.object, self.request.user)
            messages.success(self.request, f'تم تسجيل السند {self.object.number} وترحيله بنجاح')
        return redirect('sales:receipt-detail', pk=self.object.pk)

class CustomerReceiptDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = CustomerReceipt
    template_name = 'sales/receipts/detail.html'
    context_object_name = 'receipt'
    permission_required = 'sales.view_customerreceipt'

class ChequeCollectionView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'sales.change_customerreceipt'

    def post(self, request, pk):
        from .services import SalesService
        from apps.treasury.models import BankAccount
        from datetime import date as date_type
        
        receipt = get_object_or_404(CustomerReceipt, pk=pk)
        bank_id = request.POST.get('bank')
        collection_date_str = request.POST.get('date')
        
        if not bank_id or not collection_date_str:
            messages.error(request, "يجب تحديد البنك وتاريخ التحصيل")
            return redirect('sales:receipt-detail', pk=pk)
            
        try:
            bank = BankAccount.objects.get(pk=bank_id)
            collection_date = date_type.fromisoformat(collection_date_str)
            SalesService.collect_cheque(receipt, bank, collection_date, request.user)
            messages.success(request, f'تم تحصيل الشيك {receipt.cheque_number} بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ أثناء التحصيل: {e}')
            
        return redirect('sales:receipt-detail', pk=pk)

class CustomerStatementView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Customer
    template_name = 'sales/customers/statement.html'
    context_object_name = 'customer'
    permission_required = 'sales.view_customer'

    def get_context_data(self, **kwargs):
        from apps.reports.services import ReportService
        from datetime import date
        ctx = super().get_context_data(**kwargs)
        customer = self.get_object()
        
        start_date_str = self.request.GET.get('start_date')
        end_date_str = self.request.GET.get('end_date')
        
        if not start_date_str:
            start_date = date(date.today().year, date.today().month, 1)
        else:
            start_date = date.fromisoformat(start_date_str)
            
        if not end_date_str:
            end_date = date.today()
        else:
            end_date = date.fromisoformat(end_date_str)
            
        ctx['start_date'] = start_date.strftime('%Y-%m-%d')
        ctx['end_date'] = end_date.strftime('%Y-%m-%d')
        
        report = ReportService.customer_statement(customer.id, start_date, end_date)
        
        ctx['opening_balance'] = report['opening_balance']
        ctx['statement_lines'] = report['lines']
        ctx['closing_balance'] = report['closing_balance']
        return ctx

class SalesInvoiceDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = SalesInvoice
    template_name = 'sales/invoices/detail.html'
    context_object_name = 'invoice'
    permission_required = 'sales.view_salesinvoice'

from decimal import Decimal
from django.shortcuts import render
from apps.treasury.models import CashBox

class RepDailySettlementListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = RepDailySettlement
    template_name = 'sales/settlements/list.html'
    permission_required = 'sales.view_repdailysettlement'
    paginate_by = 25

    def get_queryset(self):
        qs = RepDailySettlement.objects.select_related(
            'sales_rep', 'to_cash_box', 'to_bank'
        ).order_by('-date', '-created_at')
        rep_id = self.request.GET.get('rep')
        if rep_id:
            qs = qs.filter(sales_rep_id=rep_id)
        date = self.request.GET.get('date')
        if date:
            qs = qs.filter(date=date)
        return qs

class RepDailySettlementCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    صفحة إنشاء تسوية المندوب.
    تعرض: المندوب + التاريخ + الفواتير النقدية تلقائياً + حقل النقدية المستلمة.
    """
    template_name = 'sales/settlements/form.html'
    permission_required = 'sales.add_repdailysettlement'

    def get(self, request):
        from datetime import date as today_date
        reps = SalesRepresentative.objects.filter(is_active=True)
        cash_boxes = CashBox.objects.filter(is_active=True)
        return render(request, self.template_name, {
            'reps': reps,
            'cash_boxes': cash_boxes,
            'today': today_date.today().isoformat(),
        })

    def post(self, request):
        rep_id       = request.POST.get('rep')
        date_val     = request.POST.get('date')
        cash_delivered = Decimal(request.POST.get('cash_delivered', '0'))
        to_cash_box_id = request.POST.get('to_cash_box')
        to_bank_id     = request.POST.get('to_bank')
        invoice_ids    = request.POST.getlist('invoice_ids')  # checkboxes

        if not invoice_ids:
            messages.error(request, 'يجب اختيار فاتورة واحدة على الأقل لإجراء التسوية')
            return redirect('sales:settlement-create')

        from django.db import transaction
        try:
            with transaction.atomic():
                from apps.core.services import DocumentService
                
                rep  = SalesRepresentative.objects.get(pk=rep_id)
                date = date_type.fromisoformat(date_val)

                settlement = RepDailySettlement.objects.create(
                    number=DocumentService.generate_number(RepDailySettlement, 'RS'),
                    date=date,
                    sales_rep=rep,
                    cash_delivered=cash_delivered,
                    to_cash_box_id=to_cash_box_id or None,
                    to_bank_id=to_bank_id or None,
                    created_by=request.user,
                )

                # ربط الفواتير المختارة
                invoices = SalesInvoice.objects.filter(pk__in=invoice_ids)
                for inv in invoices:
                    RepSettlementInvoice.objects.create(
                        settlement=settlement, invoice=inv
                    )

                # ترحيل مباشر
                RepSettlementService.post_settlement(settlement, request.user)

                messages.success(
                    request,
                    f'تم ترحيل تسوية المندوب {rep.name} بنجاح — '
                    f'الفرق: {settlement.difference}'
                )
            return redirect('sales:settlement-list')

        except Exception as e:
            messages.error(request, f'خطأ: {e}')
            return redirect('sales:settlement-create')

class RepDailySettlementDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = RepDailySettlement
    template_name = 'sales/settlements/detail.html'
    context_object_name = 'settlement'
    permission_required = 'sales.view_repdailysettlement'

class RepUnsettledInvoicesView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'sales.view_repdailysettlement'
    """
    HTMX endpoint — يجيب الفواتير غير المسواة للمندوب في يوم معين
    يُستدعى عند تغيير المندوب أو التاريخ في الـ form
    """
    def get(self, request):
        from .services import RepSettlementService
        rep_id   = request.GET.get('rep')
        date_val = request.GET.get('date')
        if not rep_id or not date_val:
            from django.http import HttpResponse
            return HttpResponse('')
        from datetime import date as date_type
        rep  = get_object_or_404(SalesRepresentative, pk=rep_id)
        date = date_type.fromisoformat(date_val)
        invoices = RepSettlementService.get_unsettled_invoices(rep, date)
        total    = sum(inv.total for inv in invoices)
        return render(request, 'sales/settlements/_invoice_table.html', {
            'invoices': invoices,
            'total': total,
            'rep': rep,
        })

class RepReceivableCollectView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """تحصيل ذمة متراكمة على مندوب"""
    permission_required = 'sales.change_repdailysettlement'
    template_name = 'sales/reps/collect_form.html'

    def get(self, request, rep_pk):
        from apps.treasury.models import CashBox, BankAccount
        from datetime import date as today_date
        rep = get_object_or_404(SalesRepresentative, pk=rep_pk)
        cash_boxes = CashBox.objects.filter(is_active=True)
        banks = BankAccount.objects.filter(is_active=True)
        return render(request, self.template_name, {
            'rep': rep,
            'cash_boxes': cash_boxes,
            'banks': banks,
            'today': today_date.today().isoformat(),
        })

    def post(self, request, rep_pk):
        from decimal import Decimal
        from datetime import date as date_type
        from .services import RepSettlementService
        rep      = get_object_or_404(SalesRepresentative, pk=rep_pk)
        amount   = Decimal(request.POST.get('amount', '0'))
        date     = date_type.fromisoformat(request.POST.get('date'))
        cash_box_id = request.POST.get('cash_box')
        bank_id     = request.POST.get('bank')

        if not cash_box_id and not bank_id:
            messages.error(request, 'يجب تحديد خزنة أو حساب بنكي لاستلام المبلغ')
            return redirect('sales:rep-detail', pk=rep_pk)

        if cash_box_id:
            from apps.treasury.models import CashBox
            dest = CashBox.objects.get(pk=cash_box_id).account
        else:
            from apps.treasury.models import BankAccount
            dest = BankAccount.objects.get(pk=bank_id).account

        try:
            RepSettlementService.collect_rep_receivable(
                rep, amount, dest, date, request.user
            )
            messages.success(request, f'تم تحصيل {amount} من ذمة المندوب {rep.name}')
        except Exception as e:
            messages.error(request, f'خطأ: {e}')

        return redirect('sales:rep-detail', pk=rep_pk)

class SalesReturnListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = SalesReturn
    template_name = 'sales/returns/list.html'
    context_object_name = 'returns'
    permission_required = 'sales.view_salesreturn'
    ordering = ['-date', '-id']

class SalesReturnCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = SalesReturn
    fields = ['date', 'invoice', 'customer', 'sales_rep', 'notes']
    template_name = 'sales/returns/form.html'
    permission_required = 'sales.add_salesreturn'
    success_url = reverse_lazy('sales:return-list')

    def get_context_data(self, **kwargs):
        from .forms import SalesReturnLineFormSet
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['lines'] = SalesReturnLineFormSet(self.request.POST)
        else:
            data['lines'] = SalesReturnLineFormSet()
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        lines = context['lines']
        with transaction.atomic():
            form.instance.created_by = self.request.user
            from apps.core.services import DocumentService
            form.instance.number = DocumentService.generate_number(SalesReturn, 'SRET')
            
            form.instance.subtotal = 0
            form.instance.total = 0
            
            if lines.is_valid():
                self.object = form.save()
                from apps.core.models import Account
                from django.conf import settings
                default_ret_acc = Account.objects.get(code=getattr(settings, 'DEFAULT_SALES_RETURN_ACCOUNT', '413'))
                default_cogs_acc = Account.objects.get(code=getattr(settings, 'DEFAULT_COGS_ACCOUNT', '511'))

                lines.instance = self.object
                instances = lines.save(commit=False)
                from apps.inventory.services import InventoryService
                for instance in instances:
                    if not instance.return_account_id:
                        instance.return_account = default_ret_acc
                    if not instance.cogs_account_id:
                        instance.cogs_account = instance.item.cogs_account or default_cogs_acc
                    
                    # Store current cost for accurate reversal
                    instance.cost = InventoryService.get_item_cost(instance.item, instance.warehouse)
                    
                    # ✅ Fix: Calculate base quantity
                    if hasattr(instance, 'unit') and instance.unit:
                        instance.base_quantity = instance.item.convert_to_base(instance.quantity, instance.unit)
                    else:
                        instance.base_quantity = instance.quantity
                        
                    instance.save()
                
                for obj in lines.deleted_objects:
                    obj.delete()

                # Calculate totals from lines (Standardized logic)
                gross_total = 0
                discount_total = 0
                tax_total_added = 0
                tax_total_deducted = 0
                
                for line in self.object.lines.all():
                    gross_line = line.quantity * line.unit_price
                    disc_line = gross_line * (line.discount_percent / Decimal('100'))
                    net_line = gross_line - disc_line
                    
                    # Tax logic
                    tax_val = net_line * (line.tax_percent / Decimal('100'))
                    if line.tax_type and line.tax_type.category in ['wht', 'salary', 'insurance']:
                        tax_total_deducted += tax_val
                        tax_signed = -tax_val
                    else:
                        tax_total_added += tax_val
                        tax_signed = tax_val

                    # Update line total in DB
                    line.total = net_line + tax_signed
                    line.save()
                    
                    gross_total += gross_line
                    discount_total += disc_line

                self.object.subtotal = gross_total
                self.object.discount_amount = discount_total
                self.object.tax_amount = tax_total_added - tax_total_deducted
                self.object.total = gross_total - discount_total + tax_total_added - tax_total_deducted
                self.object.save()
                messages.success(self.request, f"تم إنشاء مرتجع المبيعات {self.object.number} بنجاح (مسودة)")
            else:
                return self.form_invalid(form)
        return redirect(self.success_url)

class SalesReturnDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = SalesReturn
    template_name = 'sales/returns/detail.html'
    context_object_name = 'sales_return'
    permission_required = 'sales.view_salesreturn'

class SalesReturnPostView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'sales.change_salesreturn'
    
    def post(self, request, pk):
        sales_return = get_object_or_404(SalesReturn, pk=pk)
        try:
            SalesService.post_return(sales_return, request.user)
            messages.success(request, f'تم ترحيل المرتجع {sales_return.number} بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ أثناء الترحيل: {e}')
        return redirect('sales:return-detail', pk=pk)

from django.http import JsonResponse

class RepDetailsAPIView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'sales.view_salesrepresentative'
    def get(self, request, pk):
        rep = get_object_or_404(SalesRepresentative, pk=pk)
        return JsonResponse({
            'warehouse_id': rep.warehouse_id,
            'cash_box_id': rep.cash_box_id
        })
class RepStockStatusView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """عرض بضاعة المندوب الحالية في مخزنه الخاص"""
    template_name = 'sales/reps/my_stock.html'
    permission_required = 'sales.view_salesrepresentative'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            # التأكد من أن المستخدم مرتبط بملف مندوب
            rep = self.request.user.salesrepresentative
            from apps.reports.services import ReportService
            context['rep'] = rep
            context['report'] = ReportService.stock_status(warehouse_id=rep.warehouse_id)
        except SalesRepresentative.DoesNotExist:
            messages.error(self.request, "عفواً، حسابك غير مرتبط بملف مندوب مبيعات.")
            context['error'] = True
        return context
