import logging
from decimal import Decimal
from datetime import date as date_type, datetime, date, timedelta
from django import forms
from django.views.generic import ListView, CreateView, UpdateView, DetailView, DeleteView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.core.mixins import PermRequiredMixin
from django.urls import reverse_lazy, reverse
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.db import transaction
from django.db.models import Sum, Q, F, ExpressionWrapper, DecimalField
from django.db.models.functions import Coalesce
from django.views import View
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from apps.hr.models import Employee
from apps.core.models import Account, JournalLine, SystemNotification, JournalEntry
from apps.core.services import DocumentService
from apps.core.tax_utils import calculate_line_taxes
from apps.inventory.models import Warehouse, Item
from apps.inventory.services import InventoryService
from apps.treasury.models import CashBox, BankAccount
from apps.treasury.utils import get_available_cash_boxes
from apps.core.utils import get_account_balance
from apps.reports.services import ReportService
from .models import (
    Customer, CustomerSector, SalesInvoice, SalesInvoiceLine, 
    CustomerReceipt, SalesRepresentative, SalesReturn, SalesReturnLine, Quotation, 
    QuotationLine, PriceList, PriceListItem, RepDailySettlement, RepSettlementInvoice,
    ReceiptAllocation
)
from .forms import (
    CustomerForm, SalesInvoiceForm, SalesInvoiceLineFormSet, 
    CustomerReceiptForm, SalesRepresentativeForm, SalesReturnLineFormSet,
    QuotationForm, QuotationLineFormSet, PriceListForm, PriceListItemFormSet,
    CustomerSectorForm
)
from .services import CustomerService, SalesRepresentativeService, SalesService, RepSettlementService

logger = logging.getLogger(__name__)

class QuotationListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = Quotation
    template_name = 'sales/quotations/list.html'
    context_object_name = 'quotations'
    permission_required = 'sales.view_quotation'
    paginate_by = 25
    ordering = ['-id']

class QuotationCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
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
                form.instance.number = DocumentService.generate_number(Quotation, 'OFFR')

            self.object = form.save()

            if lines.is_valid():
                lines.instance = self.object
                lines.save()
                self._recalculate_quotation_totals(self.object)
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

    @staticmethod
    def _recalculate_quotation_totals(quotation):
        subtotal = Decimal('0')
        discount_amount = Decimal('0')
        tax_amount = Decimal('0')
        for line in quotation.lines.all():
            line_subtotal = (line.unit_price or Decimal('0')) * (line.quantity or Decimal('0'))
            line_discount = line_subtotal * ((line.discount_percent or Decimal('0')) / Decimal('100'))
            line_net = line_subtotal - line_discount
            tax_result = calculate_line_taxes(
                line_net,
                tax_type1=line.tax_type,
                tax_percent1=line.tax_percent,
            )
            line_total = line_net + tax_result.get('tax_total_added', Decimal('0')) - tax_result.get('tax_total_deducted', Decimal('0'))
            line.total = line_total.quantize(Decimal('0.01'))
            line.save(update_fields=['total'])
            subtotal += line_subtotal
            discount_amount += line_discount
            tax_amount += tax_result.get('tax_total_added', Decimal('0')) - tax_result.get('tax_total_deducted', Decimal('0'))
        quotation.subtotal = subtotal.quantize(Decimal('0.01'))
        quotation.discount_amount = discount_amount.quantize(Decimal('0.01'))
        quotation.tax_amount = tax_amount.quantize(Decimal('0.01'))
        quotation.total = (quotation.subtotal - quotation.discount_amount + quotation.tax_amount).quantize(Decimal('0.01'))
        quotation.save(update_fields=['subtotal', 'discount_amount', 'tax_amount', 'total'])

class QuotationUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):
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
                QuotationCreateView._recalculate_quotation_totals(self.object)
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

class QuotationCancelView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'sales.change_quotation'
    def post(self, request, pk):
        quotation = get_object_or_404(Quotation, pk=pk)
        quotation.status = 'cancelled'
        quotation.save()
        messages.success(request, f"تم إلغاء عرض السعر {quotation.name}")
        return redirect('sales:quotation-list')

class QuotationDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = Quotation
    template_name = 'sales/quotations/detail.html'
    context_object_name = 'quotation'
    permission_required = 'sales.view_quotation'

    def get_queryset(self):
        return super().get_queryset().prefetch_related('lines__item', 'lines__unit')

class CustomerSectorListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = CustomerSector
    template_name = 'sales/sectors/list.html'
    context_object_name = 'sectors'
    permission_required = 'sales.view_customersector'
    paginate_by = 25

class CustomerSectorCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = CustomerSector
    form_class = CustomerSectorForm
    template_name = 'sales/sectors/form.html'
    permission_required = 'sales.add_customersector'
    success_url = reverse_lazy('sales:sector-list')

    def form_valid(self, form):
        messages.success(self.request, "تم إنشاء القطاع بنجاح")
        return super().form_valid(form)

class CustomerSectorUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):
    model = CustomerSector
    form_class = CustomerSectorForm
    template_name = 'sales/sectors/form.html'
    permission_required = 'sales.change_customersector'
    success_url = reverse_lazy('sales:sector-list')

    def form_valid(self, form):
        messages.success(self.request, "تم تحديث القطاع بنجاح")
        return super().form_valid(form)

class PriceListListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = PriceList
    template_name = 'sales/price_lists/list.html'
    context_object_name = 'price_lists'
    permission_required = 'sales.view_pricelist'
    paginate_by = 25

class PriceListCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
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

class PriceListUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):
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

class PriceListDeleteView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'sales.delete_pricelist'
    def post(self, request, pk):
        pricelist = get_object_or_404(PriceList, pk=pk)
        pricelist.is_active = False
        pricelist.save()
        messages.success(request, f"تم إيقاف قائمة الأسعار {pricelist.name}")
        return redirect('sales:pricelist-list')

class QuotationConvertToInvoiceView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'sales.add_salesinvoice'

    def post(self, request, pk):
        quotation = get_object_or_404(Quotation, pk=pk)
        if quotation.status == Quotation.Status.INVOICED:
            messages.warning(request, "هذا العرض تم تحويله بالفعل لفاتورة")
            return redirect('sales:quotation-detail', pk=pk)
        
        try:
            with transaction.atomic():
                # Create Invoice
                payment_terms_days = quotation.customer.payment_terms_days if quotation.customer else 0
                due_date_value = date.today() + timedelta(days=payment_terms_days)
                invoice = SalesInvoice.objects.create(
                    number=DocumentService.generate_number(SalesInvoice, 'SINV'),
                    date=date.today(),
                    customer=quotation.customer,
                    sales_rep=quotation.sales_rep,
                    due_date=due_date_value,
                    subtotal=quotation.subtotal,
                    discount_amount=quotation.discount_amount,
                    tax_amount=quotation.tax_amount,
                    total=quotation.total,
                    created_by=request.user,
                    notes=f"محول من عرض سعر رقم {quotation.number}"
                )
                
                # Create Lines
                default_sales_acc = Account.objects.get(code=getattr(settings, 'DEFAULT_SALES_ACCOUNT', '411'))

                q_lines = quotation.lines.select_related('item', 'unit', 'tax_type', 'tax_type2').all()
                for q_line in q_lines:
                    warehouse = quotation.sales_rep.warehouse if (quotation.sales_rep and quotation.sales_rep.warehouse) else None
                    cost = InventoryService.get_item_cost(q_line.item, warehouse) if warehouse else 0

                    base_qty = q_line.quantity
                    if q_line.unit:
                        base_qty = q_line.item.convert_to_base(q_line.quantity, q_line.unit)

                    SalesInvoiceLine.objects.create(
                        invoice=invoice,
                        item=q_line.item,
                        warehouse=warehouse,
                        unit=q_line.unit,
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
            logger.exception("Error converting quotation to invoice")
            messages.error(request, f"خطأ أثناء التحويل: {e}")
            return redirect('sales:quotation-detail', pk=pk)

class CustomerListView(LoginRequiredMixin, PermRequiredMixin, ListView):
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

class CustomerCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
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
            return redirect(self.success_url)
        except Exception as e:
            logger.exception("Error creating customer")
            messages.error(self.request, f'خطأ: {e}')
            return self.form_invalid(form)

class CustomerUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'sales/customers/form.html'
    permission_required = 'sales.change_customer'
    success_url = reverse_lazy('sales:customer-list')

    def form_valid(self, form):
        CustomerService.update_customer(self.object, form.cleaned_data)
        messages.success(self.request, 'تم تحديث بيانات العميل بنجاح')
        return redirect(self.success_url)

class CustomerDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = Customer
    template_name = 'sales/customers/detail.html'
    permission_required = 'sales.view_customer'

    def get_queryset(self):
        return super().get_queryset().select_related('account', 'sector')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['invoices'] = self.object.salesinvoice_set.select_related('customer').order_by('-date')[:10]
        ctx['balance'] = get_account_balance(self.object.account) if self.object.account else 0
        return ctx

# --- Sales Representative Views ---

class SalesRepresentativeListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    permission_required = 'sales.view_salesrepresentative'
    model = SalesRepresentative
    template_name = 'sales/reps/list.html'
    context_object_name = 'reps'
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        # المشرفين (change) يشوفوا الكل — المندوب العادي يشوف نفسه بس
        if not user.has_perm('sales.change_salesrepresentative') and user.has_perm('sales.view_salesrepresentative'):
            try:
                rep = user.salesrepresentative
                return qs.filter(pk=rep.pk)
            except SalesRepresentative.DoesNotExist:
                return qs.none()
        return qs

class SalesRepresentativeDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    permission_required = 'sales.view_salesrepresentative'
    model = SalesRepresentative
    template_name = 'sales/reps/detail.html'
    context_object_name = 'rep'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        user = self.request.user
        if not user.has_perm('sales.change_salesrepresentative') and user.has_perm('sales.view_salesrepresentative'):
            try:
                my_rep = user.salesrepresentative
                if obj.pk != my_rep.pk:
                    raise PermissionDenied('لا يمكنك عرض بيانات مندوب آخر.')
            except SalesRepresentative.DoesNotExist:
                raise PermissionDenied
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rep = self.get_object()
        today = date.today()
        
        if rep.cash_box and rep.cash_box.account:
            context['cash_box_balance'] = get_account_balance(rep.cash_box.account, as_of_date=today)
        else:
            context['cash_box_balance'] = 0.0
            
        if rep.account:
            context['receivable_balance'] = get_account_balance(rep.account, as_of_date=today)
        else:
            context['receivable_balance'] = 0.0
            
        return context

class SalesRepresentativeCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    permission_required = 'sales.add_salesrepresentative'
    model = SalesRepresentative
    form_class = SalesRepresentativeForm
    template_name = 'sales/reps/form.html'
    success_url = reverse_lazy('sales:rep-list')

    @transaction.atomic
    def form_valid(self, form):
        data = form.cleaned_data
        user = data.get('user')

        # البحث عن موظف مرتبط بهذا المستخدم
        try:
            employee = Employee.objects.get(user=user)
            employee.national_id = data.get('national_id', employee.national_id)
            employee.phone = data.get('phone', employee.phone)
            if data.get('department'):
                employee.department = data['department']
            if data.get('job_title'):
                employee.job_title = data['job_title']
            employee.hiring_date = data.get('hiring_date', employee.hiring_date)
            employee.basic_salary = data.get('basic_salary', employee.basic_salary)
            employee.save()
        except Employee.DoesNotExist:
            employee = Employee.objects.create(
                user=user,
                first_name=user.first_name,
                last_name=user.last_name,
                national_id=data.get('national_id', ''),
                phone=data.get('phone', ''),
                department=data.get('department'),
                job_title=data.get('job_title'),
                hiring_date=data.get('hiring_date'),
                basic_salary=data.get('basic_salary', 0),
            )

        rep_data = {
            'employee': employee,
            'commission_rate': data.get('commission_rate', 0),
            'territory': data.get('territory', ''),
            'supervisor': data.get('supervisor'),
            'is_active': data.get('is_active', True),
        }

        self.object = SalesRepresentativeService.create_rep(rep_data)
        messages.success(self.request, f'تم إنشاء مندوب المبيعات "{self.object.name}" بنجاح.')
        return redirect(self.success_url)

class SalesRepresentativeUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):
    permission_required = 'sales.change_salesrepresentative'
    model = SalesRepresentative
    form_class = SalesRepresentativeForm
    template_name = 'sales/reps/form.html'
    success_url = reverse_lazy('sales:rep-list')

class SalesInvoiceListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = SalesInvoice
    template_name = 'sales/invoices/list.html'
    context_object_name = 'invoices'
    paginate_by = 25
    ordering = ['-date', '-id']
    permission_required = 'sales.view_salesinvoice'

    def get_queryset(self):
        qs = super().get_queryset().select_related('customer')
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(number__icontains=q) | qs.filter(customer__name__icontains=q)
        return qs

class SalesInvoiceCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = SalesInvoice
    form_class = SalesInvoiceForm
    template_name = 'sales/invoices/form.html'
    permission_required = 'sales.add_salesinvoice'
    success_url = reverse_lazy('sales:invoice-list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if hasattr(self.request.user, 'salesrepresentative'):
            rep = self.request.user.salesrepresentative
            if 'cash_box' in form.fields:
                form.fields['cash_box'].initial = rep.cash_box
                form.fields['cash_box'].empty_label = None
        return form

    def get_initial(self):
        initial = super().get_initial()
        if hasattr(self.request.user, 'salesrepresentative'):
            initial['sales_rep'] = self.request.user.salesrepresentative
        return initial

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
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
            form.instance.number = DocumentService.generate_number(SalesInvoice, 'SINV')
            
            form.instance.subtotal = 0
            form.instance.total = 0
            self.object = form.save()
            
            if lines.is_valid():
                default_sales_acc = Account.objects.get(code=getattr(settings, 'DEFAULT_SALES_ACCOUNT', '411'))

                lines.instance = self.object
                instances = lines.save(commit=False)
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

                # Calculate totals from lines using unified tax engine
                gross_total = Decimal('0')
                discount_total = Decimal('0')
                tax_total_added = Decimal('0')
                tax_total_deducted = Decimal('0')
                
                for line in self.object.lines.all():
                    gross_line = Decimal(str(line.quantity * line.unit_price))
                    disc_line = gross_line * (Decimal(str(line.discount_percent)) / Decimal('100'))
                    net_line = gross_line - disc_line
                    
                    res = calculate_line_taxes(
                        net_line,
                        line.tax_type,
                        line.tax_percent,
                        line.tax_type2,
                        line.tax_percent2,
                        is_purchase_or_expense=False
                    )
                    
                    # Update line total in DB (Net + Additions - Deductions)
                    raw_total = net_line + res['tax1_signed'] + res['tax2_signed']
                    line.total = raw_total.quantize(Decimal('0.01'))
                    line.save()
                    
                    gross_total += gross_line
                    discount_total += disc_line
                    tax_total_added += res['tax_total_added']
                    tax_total_deducted += res['tax_total_deducted']

                q = Decimal('0.01')
                self.object.subtotal = gross_total.quantize(q)
                self.object.discount_amount = discount_total.quantize(q)
                self.object.tax_amount = (tax_total_added - tax_total_deducted).quantize(q)
                self.object.total = (gross_total - discount_total + tax_total_added - tax_total_deducted).quantize(q)
                self.object.save()
                is_valid = True
            else:
                transaction.set_rollback(True)
                
        if is_valid:
            messages.success(self.request, f"تم حفظ فاتورة المبيعات {self.object.number} بنجاح (مسودة)")
            if hasattr(self.request.user, 'salesrepresentative'):
                return redirect('reports:rep_dashboard')
            return redirect('sales:invoice-list')
        else:
            return self.form_invalid(form)

class SalesInvoiceUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):
    model = SalesInvoice
    form_class = SalesInvoiceForm
    template_name = 'sales/invoices/form.html'
    success_url = reverse_lazy('sales:invoice-list')
    permission_required = 'sales.change_salesinvoice'

    def has_permission(self):
        if super().has_permission():
            return True
        if hasattr(self.request.user, 'salesrepresentative'):
            invoice = get_object_or_404(SalesInvoice, pk=self.kwargs.get('pk'))
            if invoice.sales_rep == self.request.user.salesrepresentative and invoice.status == SalesInvoice.Status.DRAFT:
                return True
        return False

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if hasattr(self.request.user, 'salesrepresentative'):
            rep = self.request.user.salesrepresentative
            if 'cash_box' in form.fields:
                form.fields['cash_box'].initial = rep.cash_box
                form.fields['cash_box'].empty_label = None
        return form

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
                instances = lines.save(commit=False)
                
                try:
                    default_sales_acc = Account.objects.get(code=getattr(settings, 'DEFAULT_SALES_ACCOUNT', '411'))
                except Account.DoesNotExist:
                    default_sales_acc = None

                for instance in instances:
                    if not instance.pk:
                        # It's a newly added line during update
                        if not hasattr(instance, 'revenue_account') or not instance.revenue_account_id:
                            instance.revenue_account = instance.item.sales_account or default_sales_acc
                        if not hasattr(instance, 'cost_of_goods_account') or not instance.cost_of_goods_account_id:
                            instance.cost_of_goods_account = instance.item.cogs_account
                        if not hasattr(instance, 'cost') or not instance.cost:
                            instance.cost = InventoryService.get_item_cost(instance.item, instance.warehouse)
                            
                    # Calculate base quantity on update
                    if instance.unit:
                        instance.base_quantity = instance.item.convert_to_base(instance.quantity, instance.unit)
                    else:
                        instance.base_quantity = instance.quantity
                        
                    instance.save()
                    
                # Handle deleted lines
                for obj in lines.deleted_objects:
                    obj.delete()
                
                # Calculate totals from lines using unified tax engine
                gross_total = Decimal('0')
                discount_total = Decimal('0')
                tax_total_added = Decimal('0')
                tax_total_deducted = Decimal('0')
                
                for line in self.object.lines.all():
                    gross_line = Decimal(str(line.quantity * line.unit_price))
                    disc_line = gross_line * (Decimal(str(line.discount_percent)) / Decimal('100'))
                    net_line = gross_line - disc_line
                    
                    res = calculate_line_taxes(
                        net_line,
                        line.tax_type,
                        line.tax_percent,
                        line.tax_type2,
                        line.tax_percent2,
                        is_purchase_or_expense=False
                    )
                    
                    # Update line in DB (Total + Base Quantity)
                    raw_total = net_line + res['tax1_signed'] + res['tax2_signed']
                    line.total = raw_total.quantize(Decimal('0.01'))
                    line.save()
                    
                    gross_total += gross_line
                    discount_total += disc_line
                    tax_total_added += res['tax_total_added']
                    tax_total_deducted += res['tax_total_deducted']

                q = Decimal('0.01')
                self.object.subtotal = gross_total.quantize(q)
                self.object.discount_amount = discount_total.quantize(q)
                self.object.tax_amount = (tax_total_added - tax_total_deducted).quantize(q)
                self.object.total = (gross_total - discount_total + tax_total_added - tax_total_deducted).quantize(q)
                self.object.save()
                is_valid = True
                
            else:
                transaction.set_rollback(True)
                
        if is_valid:
            messages.success(self.request, f"تم تحديث الفاتورة {self.object.number} بنجاح")
            if hasattr(self.request.user, 'salesrepresentative'):
                return redirect('reports:rep_dashboard')
            return redirect('sales:invoice-list')
        else:
            return self.form_invalid(form)

class SalesInvoiceReverseView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'sales.change_salesinvoice'
    
    def has_permission(self):
        if super().has_permission():
            return True
        if hasattr(self.request.user, 'salesrepresentative'):
            invoice = get_object_or_404(SalesInvoice, pk=self.kwargs.get('pk'))
            if invoice.sales_rep == self.request.user.salesrepresentative and invoice.status == SalesInvoice.Status.DRAFT:
                return True
        return False
        
    def post(self, request, pk):
        invoice = get_object_or_404(SalesInvoice.objects.select_for_update(), pk=pk)
        if invoice.status == SalesInvoice.Status.DRAFT:
            invoice.status = SalesInvoice.Status.CANCELLED
            invoice.save()
            messages.success(request, f"تم إلغاء الفاتورة {invoice.number} (مسودة)")
            SystemNotification.notify_accountants(
                title="إلغاء فاتورة مبيعات",
                message=f"قام {request.user.username} بإلغاء فاتورة المبيعات رقم {invoice.number} للعميل {invoice.customer.name} بقيمة {invoice.total:.2f} ج.م.",
                url=reverse('sales:invoice-detail', args=[invoice.id])
            )
        elif invoice.status == SalesInvoice.Status.POSTED:
            try:
                SalesService.reverse_invoice(invoice, request.user)
                messages.success(request, f"تم عكس الفاتورة {invoice.number} وإنشاء قيد عكسي")
                SystemNotification.notify_accountants(
                    title="عكس فاتورة مبيعات",
                    message=f"قام {request.user.username} بعكس فاتورة المبيعات رقم {invoice.number} للعميل {invoice.customer.name} بقيمة {invoice.total:.2f} ج.م.",
                    url=reverse('sales:invoice-detail', args=[invoice.id])
                )
            except Exception as e:
                logger.exception("Error reversing invoice")
                messages.error(request, f"خطأ أثناء العكس: {e}")
        else:
            messages.warning(request, "لا يمكن عكس هذه الفاتورة")
            
        return redirect('sales:invoice-detail', pk=pk)

class SalesInvoicePostView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'sales.change_salesinvoice'
    
    def has_permission(self):
        if super().has_permission():
            return True
        if hasattr(self.request.user, 'salesrepresentative'):
            invoice = get_object_or_404(SalesInvoice, pk=self.kwargs.get('pk'))
            if invoice.sales_rep == self.request.user.salesrepresentative and invoice.status == SalesInvoice.Status.DRAFT:
                return True
        return False
    
    def post(self, request, pk):
        from datetime import date as date_type
        invoice = get_object_or_404(SalesInvoice, pk=pk)
        try:
            SalesService.post_invoice(invoice, request.user)
            
            # Dynamic notification for cash customers on credit terms
            if invoice.customer.customer_type == 'cash' and invoice.payment_type == 'credit':
                title = f"فاتورة بيع استثنائية لعميل نقدي"
                message = f"قام المستخدم {request.user.username} بترحيل فاتورة بيع بالآجل رقم {invoice.number} للعميل {invoice.customer.name} بقيمة {invoice.total:.2f} ج.م رغم أن العميل نقدي."
                url = reverse('sales:invoice-detail', args=[invoice.id])
                SystemNotification.notify_accountants(title, message, url)
                messages.warning(request, "⚠️ تنبيه: لقد قمت بعمل فاتورة (آجل) لعميل (نقدي). تم إرسال إشعار بذلك للإدارة.")

            # Send notification and flash warning if invoice date is not today
            today_date = date_type.today()
            if invoice.date != today_date:
                title = "فاتورة بيع بتاريخ استثنائي (سابق/لاحق)"
                message = f"قام المستخدم {request.user.username} بترحيل فاتورة مبيعات رقم {invoice.number} للعميل {invoice.customer.name} بقيمة {invoice.total:.2f} ج.م بتاريخ استثنائي {invoice.date} (سابق أو لاحق لتاريخ اليوم {today_date})."
                url = reverse('sales:invoice-detail', args=[invoice.id])
                SystemNotification.notify_accountants(title, message, url)
                messages.warning(
                    request,
                    f"تنبيه: تم ترحيل الفاتورة بتاريخ استثنائي {invoice.date} (سابق أو لاحق لتاريخ اليوم)، وتم إخطار المحاسب والمدير بذلك تلقائياً."
                )

            messages.success(request, f'تم ترحيل الفاتورة {invoice.number} بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ أثناء الترحيل: {e}')
        if hasattr(request.user, 'salesrepresentative'):
            return redirect('reports:rep_dashboard')
        return redirect('sales:invoice-list')

class CustomerReceiptListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = CustomerReceipt
    template_name = 'sales/receipts/list.html'
    context_object_name = 'receipts'
    permission_required = 'sales.view_customerreceipt'
    paginate_by = 25

    def get_queryset(self):
        return super().get_queryset().select_related('customer')

class CustomerReceiptCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = CustomerReceipt
    form_class = CustomerReceiptForm
    template_name = 'sales/receipts/form.html'
    success_url = reverse_lazy('sales:receipt-list')
    permission_required = 'sales.add_customerreceipt'

    def get_success_url(self):
        if hasattr(self.request.user, 'salesrepresentative'):
            return str(reverse_lazy('reports:rep_dashboard')) + "?tab=credit"
        return str(self.success_url)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        customer_id = self.request.GET.get('customer')
        amount = self.request.GET.get('amount')
        
        if customer_id:
            initial['customer'] = customer_id
        if amount:
            initial['amount'] = amount
            
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if hasattr(self.request.user, 'salesrepresentative'):
            rep = self.request.user.salesrepresentative
            if 'cash_box' in form.fields:
                form.fields['cash_box'].initial = rep.cash_box
                form.fields['cash_box'].empty_label = None
                
        if self.request.GET.get('customer') and 'customer' in form.fields:
            form.fields['customer'].widget.attrs.update({
                'style': 'pointer-events: none; background-color: #e9ecef;',
                'tabindex': '-1'
            })
        return form

    def form_valid(self, form):
        try:
            with transaction.atomic():
                form.instance.number = DocumentService.generate_number(CustomerReceipt, 'RCPT')
                form.instance.created_by = self.request.user
                self.object = form.save()
                
                # Process allocations from request.POST
                for key, value in self.request.POST.items():
                    if key.startswith('allocation_') and value:
                        try:
                            invoice_id = int(key.split('_')[1])
                            allocated_amount = Decimal(value)
                            if allocated_amount > 0:
                                # Verify invoice belongs to the customer and is posted
                                invoice = SalesInvoice.objects.select_for_update().get(
                                    pk=invoice_id, 
                                    customer=self.object.customer,
                                    status=SalesInvoice.Status.POSTED
                                )
                                # Create allocation
                                ReceiptAllocation.objects.create(
                                    receipt=self.object,
                                    invoice=invoice,
                                    amount=allocated_amount
                                )
                                # Update invoice paid amount
                                invoice.paid_amount += allocated_amount
                                invoice.save(update_fields=['paid_amount'])
                        except (ValueError, SalesInvoice.DoesNotExist, IndexError):
                            pass

                SalesService.record_receipt(self.object, self.request.user)
                messages.success(self.request, f'تم تسجيل السند {self.object.number} وترحيله بنجاح')
            return redirect(self.get_success_url())
        except Exception as e:
            logger.exception('Error creating customer receipt')
            messages.error(self.request, f'خطأ أثناء الحفظ: {e}')
            return self.form_invalid(form)

class CustomerReceiptDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = CustomerReceipt
    template_name = 'sales/receipts/detail.html'
    context_object_name = 'receipt'
    permission_required = 'sales.view_customerreceipt'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['banks'] = BankAccount.objects.filter(is_active=True).select_related('account')
        ctx['cash_boxes'] = get_available_cash_boxes(self.request.user)
        return ctx

class CustomerReceiptPrintView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = CustomerReceipt
    template_name = 'sales/receipts/print.html'
    context_object_name = 'receipt'
    permission_required = 'sales.view_customerreceipt'

class ChequeCollectionView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'sales.change_customerreceipt'

    def post(self, request, pk):
        receipt = get_object_or_404(CustomerReceipt, pk=pk)
        bank_id = request.POST.get('bank')
        cash_box_id = request.POST.get('cash_box')
        collection_date_str = request.POST.get('date')
        
        if not (bank_id or cash_box_id) or not collection_date_str:
            messages.error(request, "يجب تحديد جهة التحصيل وتاريخ التحصيل")
            return redirect('sales:receipt-detail', pk=pk)
            
        try:
            collection_date = date_type.fromisoformat(collection_date_str)
            if cash_box_id:
                from apps.treasury.models import CashBox
                cash_box = CashBox.objects.get(pk=cash_box_id)
                dest_account = cash_box.account
                entry_type = JournalEntry.EntryType.RECEIPT
                dest_name = cash_box.name
            else:
                bank = BankAccount.objects.get(pk=bank_id)
                dest_account = bank.account
                entry_type = JournalEntry.EntryType.BANK
                dest_name = f"{bank.bank_name} - {bank.name}"
                
            SalesService.collect_cheque(receipt, dest_account, collection_date, request.user, entry_type)
            messages.success(request, f'تم تحصيل الشيك {receipt.cheque_number} بنجاح في {dest_name}')
            return redirect('sales:receipt-list')
        except Exception as e:
            logger.exception("Error collecting cheque")
            messages.error(request, f'خطأ أثناء التحصيل: {e}')
            return redirect('sales:receipt-detail', pk=pk)

class ChequeBounceView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'sales.change_customerreceipt'

    def post(self, request, pk):
        receipt = get_object_or_404(CustomerReceipt, pk=pk)
        bounce_date_str = request.POST.get('date')
        penalty_str = request.POST.get('penalty', '0')
        
        if not bounce_date_str:
            messages.error(request, "يجب تحديد تاريخ الإرجاع")
            return redirect('sales:receipt-detail', pk=pk)
            
        try:
            bounce_date = date_type.fromisoformat(bounce_date_str)
            penalty = Decimal(penalty_str) if penalty_str else Decimal('0')
            SalesService.bounce_cheque(receipt, bounce_date, request.user, penalty)
            messages.success(request, f'تم إرجاع الشيك {receipt.cheque_number} كشيك مرتجع')
        except Exception as e:
            logger.exception("Error bouncing cheque")
            messages.error(request, f'خطأ أثناء إرجاع الشيك: {e}')
            
        return redirect('sales:receipt-detail', pk=pk)

class CustomerStatementView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = Customer
    template_name = 'sales/customers/statement.html'
    context_object_name = 'customer'
    permission_required = 'sales.view_customer'

    def get_context_data(self, **kwargs):
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

class SalesInvoiceDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = SalesInvoice
    template_name = 'sales/invoices/detail.html'
    context_object_name = 'invoice'
    permission_required = 'sales.view_salesinvoice'

    def get_queryset(self):
        return super().get_queryset().select_related('customer', 'sales_rep', 'cash_box').prefetch_related('lines__item', 'lines__unit')

class SalesInvoicePrintView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = SalesInvoice
    template_name = 'sales/invoices/print.html'
    context_object_name = 'invoice'
    permission_required = 'sales.view_salesinvoice'

    def get_queryset(self):
        return super().get_queryset().select_related('customer', 'sales_rep', 'cash_box').prefetch_related('lines__item', 'lines__unit')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.e_invoice.models import CompanySettings
        settings = CompanySettings.objects.filter(is_active=True).first()
        if settings:
            context['company_name'] = settings.company_name_ar
            context['company_address'] = settings.address
            context['company_tax_number'] = settings.tax_id
            context['company_phone'] = settings.phone
        return context

class RepDailySettlementListView(LoginRequiredMixin, PermRequiredMixin, ListView):
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

class RepDailySettlementCreateView(LoginRequiredMixin, PermRequiredMixin, View):
    """
    صفحة إنشاء تسوية المندوب.
    تعرض: المندوب + التاريخ + الفواتير النقدية تلقائياً + حقل النقدية المستلمة.
    """
    template_name = 'sales/settlements/form.html'
    permission_required = 'sales.add_repdailysettlement'

    def get(self, request):
        reps = SalesRepresentative.objects.filter(is_active=True)
        cash_boxes = get_available_cash_boxes(request.user)
        banks = BankAccount.objects.filter(is_active=True)
        wallets = MobileWallet.objects.filter(is_active=True)
        return render(request, self.template_name, {
            'reps': reps,
            'cash_boxes': cash_boxes,
            'banks': banks,
            'wallets': wallets,
            'today': date.today().isoformat(),
        })

    def post(self, request):
        rep_id       = request.POST.get('rep')
        date_val     = request.POST.get('date')
        cash_delivered = Decimal(request.POST.get('cash_delivered', '0'))
        to_cash_box_id = request.POST.get('to_cash_box')
        to_bank_id     = request.POST.get('to_bank')
        to_wallet_id   = request.POST.get('to_wallet')
        invoice_ids    = request.POST.getlist('invoice_ids')  # checkboxes

        if not invoice_ids:
            messages.error(request, 'يجب اختيار فاتورة واحدة على الأقل لإجراء التسوية')
            return redirect('sales:settlement-create')

        try:
            with transaction.atomic():
                rep  = SalesRepresentative.objects.get(pk=rep_id)
                date = date_type.fromisoformat(date_val)

                settlement = RepDailySettlement.objects.create(
                    number=DocumentService.generate_number(RepDailySettlement, 'RS'),
                    date=date,
                    sales_rep=rep,
                    cash_delivered=cash_delivered,
                    to_cash_box_id=to_cash_box_id or None,
                    to_bank_id=to_bank_id or None,
                    to_wallet_id=to_wallet_id or None,
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
            logger.exception("Error creating settlement")
            messages.error(request, f'خطأ: {e}')
            return redirect('sales:settlement-create')

class RepDailySettlementDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = RepDailySettlement
    template_name = 'sales/settlements/detail.html'
    context_object_name = 'settlement'
    permission_required = 'sales.view_repdailysettlement'

    def get_queryset(self):
        return super().get_queryset().select_related('sales_rep', 'to_cash_box', 'to_bank', 'to_wallet', 'journal_entry')

class RepDailySettlementPostView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'sales.change_repdailysettlement'

    def post(self, request, pk):
        settlement = get_object_or_404(RepDailySettlement, pk=pk)
        
        # Verify a destination cashbox or bank is set (POS leaves it as session.station.cash_box by default, but it might need selection)
        if not settlement.to_cash_box and not settlement.to_bank and not settlement.to_wallet:
            messages.error(request, 'يجب تحديد خزينة، بنك أو محفظة استلام لتتمكن من ترحيل التسوية.')
            return redirect('sales:settlement-detail', pk=pk)

        try:
            RepSettlementService.post_settlement(settlement, request.user)
            messages.success(request, f'تم ترحيل التسوية {settlement.number} بنجاح وتم إنشاء القيود المحاسبية.')
        except Exception as e:
            logger.exception("Error posting settlement")
            messages.error(request, f'حدث خطأ أثناء الترحيل: {str(e)}')
            
        return redirect('sales:settlement-detail', pk=pk)

class RepUnsettledInvoicesView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'sales.view_repdailysettlement'
    """
    HTMX endpoint — يجيب الفواتير غير المسواة للمندوب في يوم معين
    يُستدعى عند تغيير المندوب أو التاريخ في الـ form
    """
    def get(self, request):
        rep_id   = request.GET.get('rep')
        date_val = request.GET.get('date')
        if not rep_id or not date_val:
            return HttpResponse('')
        rep  = get_object_or_404(SalesRepresentative, pk=rep_id)
        date = date_type.fromisoformat(date_val)
        invoices = RepSettlementService.get_unsettled_invoices(rep, date)
        total    = sum(inv.total for inv in invoices)
        return render(request, 'sales/settlements/_invoice_table.html', {
            'invoices': invoices,
            'total': total,
            'rep': rep,
        })

class RepReceivableCollectView(LoginRequiredMixin, PermRequiredMixin, View):
    """تحصيل ذمة متراكمة على مندوب"""
    permission_required = 'sales.change_repdailysettlement'
    template_name = 'sales/reps/collect_form.html'

    def get(self, request, rep_pk):
        rep = get_object_or_404(SalesRepresentative, pk=rep_pk)
        cash_boxes = get_available_cash_boxes(request.user)
        banks = BankAccount.objects.filter(is_active=True)
        return render(request, self.template_name, {
            'rep': rep,
            'cash_boxes': cash_boxes,
            'banks': banks,
            'today': date.today().isoformat(),
        })

    def post(self, request, rep_pk):
        rep      = get_object_or_404(SalesRepresentative, pk=rep_pk)
        amount   = Decimal(request.POST.get('amount', '0'))
        date     = date_type.fromisoformat(request.POST.get('date'))
        cash_box_id = request.POST.get('cash_box')
        bank_id     = request.POST.get('bank')

        if amount <= 0:
            messages.error(request, 'يجب أن يكون المبلغ أكبر من صفر')
            return redirect('sales:rep-receivable-collect', rep_pk=rep_pk)

        if not cash_box_id and not bank_id:
            messages.error(request, 'يجب تحديد خزنة أو حساب بنكي لاستلام المبلغ')
            return redirect('sales:rep-receivable-collect', rep_pk=rep_pk)

        if cash_box_id:
            dest = get_object_or_404(CashBox, pk=cash_box_id).account
        else:
            dest = get_object_or_404(BankAccount, pk=bank_id).account

        try:
            RepSettlementService.collect_rep_receivable(
                rep, amount, dest, date, request.user
            )
            messages.success(request, f'تم تحصيل {amount} من ذمة المندوب {rep.name}')
        except Exception as e:
            logger.exception("Error collecting rep receivable")
            messages.error(request, f'خطأ: {e}')

        return redirect('sales:rep-detail', pk=rep_pk)

class SalesReturnListView(LoginRequiredMixin, PermRequiredMixin, ListView):
    model = SalesReturn
    template_name = 'sales/returns/list.html'
    context_object_name = 'returns'
    permission_required = 'sales.view_salesreturn'
    paginate_by = 25
    ordering = ['-date', '-id']

    def get_queryset(self):
        return super().get_queryset().select_related('customer', 'sales_rep')

class SalesReturnCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
    model = SalesReturn
    fields = ['date', 'invoice', 'customer', 'payment_type', 'cash_box', 'sales_rep', 'notes']
    template_name = 'sales/returns/form.html'
    permission_required = 'sales.add_salesreturn'

    def get_success_url(self):
        if hasattr(self.request.user, 'salesrepresentative'):
            return reverse_lazy('reports:rep_dashboard')
        return reverse_lazy('sales:return-list')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Apply premium Bootstrap 5 form classes
        for field_name, field in form.fields.items():
            if not isinstance(field.widget, (forms.CheckboxInput, forms.RadioSelect)):
                if isinstance(field.widget, forms.Select):
                    field.widget.attrs.update({'class': 'form-select'})
                else:
                    field.widget.attrs.update({'class': 'form-control'})
                    
        if hasattr(self.request.user, 'salesrepresentative'):
            rep = self.request.user.salesrepresentative
            if 'sales_rep' in form.fields:
                form.fields['sales_rep'].queryset = SalesRepresentative.objects.filter(id=rep.id)
                form.fields['sales_rep'].initial = rep
                form.fields['sales_rep'].empty_label = None
            if 'cash_box' in form.fields:
                form.fields['cash_box'].queryset = get_available_cash_boxes(self.request.user)
                form.fields['cash_box'].initial = rep.cash_box
                form.fields['cash_box'].empty_label = None
                
        # Lock date field to calendar picker widget
        if 'date' in form.fields:
            form.fields['date'].widget = forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            })
                
        # Dynamically restrict original invoice selection to the chosen customer
        if 'invoice' in form.fields:
            # Customize option label to show invoice payment type, date, and amount
            form.fields['invoice'].label_from_instance = lambda obj: f"{obj.number} ({obj.get_payment_type_display()} - {obj.date} - {obj.total:.2f} ج.م)"

            customer_id = form.data.get('customer') or form.initial.get('customer')
            if customer_id:
                qs = SalesInvoice.objects.filter(customer_id=customer_id, status=SalesInvoice.Status.POSTED)
                form.fields['invoice'].queryset = qs
            else:
                form.fields['invoice'].queryset = SalesInvoice.objects.none()
                
        return form

    def get_initial(self):
        initial = super().get_initial()
        initial['date'] = date.today().isoformat()
        if hasattr(self.request.user, 'salesrepresentative'):
            rep = self.request.user.salesrepresentative
            initial['sales_rep'] = rep
            if rep.cash_box:
                initial['cash_box'] = rep.cash_box
        return initial

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            lines = SalesReturnLineFormSet(self.request.POST)
        else:
            lines = SalesReturnLineFormSet()
            
        # Restrict warehouse to only show the representative's own warehouse
        if hasattr(self.request.user, 'salesrepresentative'):
            rep = self.request.user.salesrepresentative
            warehouse_qs = Warehouse.objects.filter(id=rep.warehouse_id)
            for form in lines.forms:
                if 'warehouse' in form.fields:
                    form.fields['warehouse'].queryset = warehouse_qs
                    form.fields['warehouse'].initial = rep.warehouse
                    form.fields['warehouse'].empty_label = None
                    
        data['lines'] = lines
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        lines = context['lines']
        with transaction.atomic():
            form.instance.created_by = self.request.user
            form.instance.number = DocumentService.generate_number(SalesReturn, 'SRET')
            
            form.instance.subtotal = 0
            form.instance.total = 0
            
            if lines.is_valid():
                # Strict invoice-to-return validation
                if form.instance.invoice_id:
                    invoice_id = form.instance.invoice_id
                    
                    has_error = False
                    for line_form in lines.forms:
                        if line_form.cleaned_data and not line_form.cleaned_data.get('DELETE', False):
                            item = line_form.cleaned_data.get('item')
                            qty = line_form.cleaned_data.get('quantity')
                            unit = line_form.cleaned_data.get('unit')
                            
                            if not item or qty is None:
                                continue
                                
                            try:
                                entered_base_qty = item.convert_to_base(qty, unit)
                            except ValueError as e:
                                line_form.add_error('unit', str(e))
                                has_error = True
                                continue
                                # Validations removed as per user request to allow returning items not in invoice
                                # and quantities exceeding the original invoice amount.
                                pass
                    if has_error:
                        return self.form_invalid(form)

                self.object = form.save()
                default_ret_acc = Account.objects.get(code=getattr(settings, 'DEFAULT_SALES_RETURN_ACCOUNT', '413'))
                default_cogs_acc = Account.objects.get(code=getattr(settings, 'DEFAULT_COGS_ACCOUNT', '511'))

                lines.instance = self.object
                instances = lines.save(commit=False)
                for instance in instances:
                    if not instance.return_account_id:
                        instance.return_account = default_ret_acc
                    if not instance.cogs_account_id:
                        instance.cogs_account = instance.item.cogs_account or default_cogs_acc
                    
                    # Store historical cost if linked return, else current cost
                    if self.object.invoice_id:
                        inv_line = SalesInvoiceLine.objects.filter(invoice_id=self.object.invoice_id, item=instance.item).first()
                        if inv_line:
                            instance.cost = inv_line.cost
                        else:
                            instance.cost = InventoryService.get_item_cost(instance.item, instance.warehouse)
                    else:
                        instance.cost = InventoryService.get_item_cost(instance.item, instance.warehouse)
                    
                    # ✅ Fix: Calculate base quantity
                    if hasattr(instance, 'unit') and instance.unit:
                        instance.base_quantity = instance.item.convert_to_base(instance.quantity, instance.unit)
                    else:
                        instance.base_quantity = instance.quantity
                        
                    instance.save()
                
                for obj in lines.deleted_objects:
                    obj.delete()

                # Calculate totals from lines using unified tax engine
                gross_total = Decimal('0')
                discount_total = Decimal('0')
                tax_total_added = Decimal('0')
                tax_total_deducted = Decimal('0')
                
                for line in self.object.lines.all():
                    gross_line = Decimal(str(line.quantity * line.unit_price))
                    disc_line = gross_line * (Decimal(str(line.discount_percent)) / Decimal('100'))
                    net_line = gross_line - disc_line
                    
                    res = calculate_line_taxes(
                        net_line,
                        line.tax_type,
                        line.tax_percent,
                        line.tax_type2,
                        line.tax_percent2,
                        is_purchase_or_expense=False
                    )
                    
                    # Update line total in DB
                    raw_total = net_line + res['tax1_signed'] + res['tax2_signed']
                    line.total = raw_total.quantize(Decimal('0.01'))
                    line.save()
                    
                    gross_total += gross_line
                    discount_total += disc_line
                    tax_total_added += res['tax_total_added']
                    tax_total_deducted += res['tax_total_deducted']

                q = Decimal('0.01')
                self.object.subtotal = gross_total.quantize(q)
                self.object.discount_amount = discount_total.quantize(q)
                self.object.tax_amount = (tax_total_added - tax_total_deducted).quantize(q)
                self.object.total = (gross_total - discount_total + tax_total_added - tax_total_deducted).quantize(q)
                self.object.save()
                
                messages.success(self.request, f"تم إنشاء مرتجع المبيعات {self.object.number} بنجاح (مسودة)")
            else:
                return self.form_invalid(form)
        return redirect(self.get_success_url())


class SalesReturnDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = SalesReturn
    template_name = 'sales/returns/detail.html'
    context_object_name = 'sales_return'
    permission_required = 'sales.view_salesreturn'

    def get_queryset(self):
        return super().get_queryset().select_related('customer', 'sales_rep', 'cash_box', 'invoice').prefetch_related('lines__item', 'lines__unit')

class SalesReturnPostView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'sales.change_salesreturn'
    
    def has_permission(self):
        if super().has_permission():
            return True
        if hasattr(self.request.user, 'salesrepresentative'):
            sales_return = get_object_or_404(SalesReturn, pk=self.kwargs.get('pk'))
            if sales_return.sales_rep == self.request.user.salesrepresentative and sales_return.status == 'draft':
                return True
        return False
    
    def post(self, request, pk):
        sales_return = get_object_or_404(SalesReturn, pk=pk)
        try:
            SalesService.post_return(sales_return, request.user)
            
            # تنبيه ديناميكي محاسبي عند إرجاع آجل لعميل نقدي
            if sales_return.customer.customer_type == 'cash' and sales_return.payment_type == 'credit':
                title = f"مرتجع مبيعات استثنائي بالآجل لعميل نقدي"
                message = f"قام المستخدم {request.user.username} بترحيل مرتجع مبيعات بالآجل رقم {sales_return.number} للعميل {sales_return.customer.name} بقيمة {sales_return.total:.2f} ج.م رغم أن العميل نقدي."
                url = reverse('sales:return-detail', args=[sales_return.id])
                SystemNotification.notify_accountants(title, message, url)
                messages.warning(request, "⚠️ تنبيه: لقد قمت بترحيل مرتجع (آجل) لعميل (نقدي). تم إرسال إشعار بذلك للإدارة.")

            messages.success(request, f'تم ترحيل المرتجع {sales_return.number} بنجاح')
        except Exception as e:
            logger.exception("Error posting sales return")
            messages.error(request, f'خطأ أثناء الترحيل: {e}')
        if hasattr(request.user, 'salesrepresentative'):
            return redirect('reports:rep_dashboard')
        return redirect('sales:return-detail', pk=pk)

class SalesReturnUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):
    model = SalesReturn
    fields = ['date', 'invoice', 'customer', 'payment_type', 'cash_box', 'sales_rep', 'notes']
    template_name = 'sales/returns/form.html'
    success_url = reverse_lazy('sales:return-list')
    permission_required = 'sales.change_salesreturn'

    def has_permission(self):
        if super().has_permission():
            return True
        if hasattr(self.request.user, 'salesrepresentative'):
            sales_return = get_object_or_404(SalesReturn, pk=self.kwargs.get('pk'))
            if sales_return.sales_rep == self.request.user.salesrepresentative and sales_return.status == 'draft':
                return True
        return False

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        for field_name, field in form.fields.items():
            if not isinstance(field.widget, (forms.CheckboxInput, forms.RadioSelect)):
                if isinstance(field.widget, forms.Select):
                    field.widget.attrs.update({'class': 'form-select'})
                else:
                    field.widget.attrs.update({'class': 'form-control'})
                    
        if hasattr(self.request.user, 'salesrepresentative'):
            rep = self.request.user.salesrepresentative
            if 'sales_rep' in form.fields:
                form.fields['sales_rep'].queryset = SalesRepresentative.objects.filter(id=rep.id)
                form.fields['sales_rep'].initial = rep
                form.fields['sales_rep'].empty_label = None
            if 'cash_box' in form.fields:
                form.fields['cash_box'].queryset = get_available_cash_boxes(self.request.user)
                form.fields['cash_box'].initial = rep.cash_box
                form.fields['cash_box'].empty_label = None
                
        if 'date' in form.fields:
            form.fields['date'].widget = forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
                
        if 'invoice' in form.fields:
            form.fields['invoice'].label_from_instance = lambda obj: f"{obj.number} ({obj.get_payment_type_display()} - {obj.date} - {obj.total:.2f} ج.م)"
            customer_id = form.data.get('customer') or form.initial.get('customer') or (self.object.customer_id if self.object else None)
            if customer_id:
                qs = SalesInvoice.objects.filter(customer_id=customer_id, status=SalesInvoice.Status.POSTED)
                form.fields['invoice'].queryset = qs
            else:
                form.fields['invoice'].queryset = SalesInvoice.objects.none()
                
        return form

    def get_queryset(self):
        return super().get_queryset().filter(status='draft')

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            lines = SalesReturnLineFormSet(self.request.POST, instance=self.object)
        else:
            lines = SalesReturnLineFormSet(instance=self.object)
            
        if hasattr(self.request.user, 'salesrepresentative'):
            rep = self.request.user.salesrepresentative
            warehouse_qs = Warehouse.objects.filter(id=rep.warehouse_id)
            for form in lines.forms:
                if 'warehouse' in form.fields:
                    form.fields['warehouse'].queryset = warehouse_qs
                    form.fields['warehouse'].empty_label = None
                    
        data['lines'] = lines
        return data

    def form_valid(self, form):
        if self.object.status != 'draft':
            messages.error(self.request, "لا يمكن تعديل مرتجع غير مسودة.")
            return redirect('sales:return-detail', pk=self.object.pk)

        context = self.get_context_data()
        lines = context['lines']
        
        with transaction.atomic():
            if lines.is_valid():
                has_error = False
                if form.instance.invoice_id:
                    for line_form in lines.forms:
                        if line_form.cleaned_data and not line_form.cleaned_data.get('DELETE', False):
                            item = line_form.cleaned_data.get('item')
                            qty = line_form.cleaned_data.get('quantity')
                            unit = line_form.cleaned_data.get('unit')
                            if not item or qty is None:
                                continue
                            try:
                                entered_base_qty = item.convert_to_base(qty, unit)
                            except ValueError as e:
                                line_form.add_error('unit', str(e))
                                has_error = True
                                continue
                
                if has_error:
                    return self.form_invalid(form)

                self.object = form.save()
                lines.instance = self.object
                instances = lines.save(commit=False)
                
                try:
                    default_ret_acc = Account.objects.get(code=getattr(settings, 'DEFAULT_SALES_RETURN_ACCOUNT', '413'))
                except Account.DoesNotExist:
                    default_ret_acc = None

                try:
                    default_cogs_acc = Account.objects.get(code=getattr(settings, 'DEFAULT_COGS_ACCOUNT', '511'))
                except Account.DoesNotExist:
                    default_cogs_acc = None

                for instance in instances:
                    if not instance.pk:
                        if not hasattr(instance, 'return_account') or not instance.return_account_id:
                            instance.return_account = instance.item.sales_return_account or default_ret_acc
                        if not hasattr(instance, 'cogs_account') or not instance.cogs_account_id:
                            instance.cogs_account = instance.item.cogs_account or default_cogs_acc
                        if not hasattr(instance, 'cost') or not instance.cost:
                            instance.cost = InventoryService.get_item_cost(instance.item, instance.warehouse)
                            
                    if instance.unit:
                        instance.base_quantity = instance.item.convert_to_base(instance.quantity, instance.unit)
                    else:
                        instance.base_quantity = instance.quantity
                        
                    instance.save()
                    
                for obj in lines.deleted_objects:
                    obj.delete()
                
                gross_total = Decimal('0')
                discount_total = Decimal('0')
                tax_total_added = Decimal('0')
                tax_total_deducted = Decimal('0')
                
                for line in self.object.lines.all():
                    gross_line = Decimal(str(line.quantity * line.unit_price))
                    disc_line = gross_line * (Decimal(str(line.discount_percent)) / Decimal('100'))
                    net_line = gross_line - disc_line
                    
                    res = calculate_line_taxes(
                        net_line,
                        line.tax_type,
                        line.tax_percent,
                        line.tax_type2,
                        line.tax_percent2,
                        is_purchase_or_expense=False
                    )
                    
                    raw_total = net_line + res['tax1_signed'] + res['tax2_signed']
                    line.total = raw_total.quantize(Decimal('0.01'))
                    line.save()
                    
                    gross_total += gross_line
                    discount_total += disc_line
                    tax_total_added += res['tax_total_added']
                    tax_total_deducted += res['tax_total_deducted']

                q = Decimal('0.01')
                self.object.subtotal = gross_total.quantize(q)
                self.object.discount_amount = discount_total.quantize(q)
                self.object.tax_amount = (tax_total_added - tax_total_deducted).quantize(q)
                self.object.total = (gross_total - discount_total + tax_total_added - tax_total_deducted).quantize(q)
                self.object.save()
                
                messages.success(self.request, f"تم تعديل المرتجع {self.object.number} بنجاح")
                if hasattr(self.request.user, 'salesrepresentative'):
                    return redirect('reports:rep_dashboard')
                return redirect('sales:return-list')
            else:
                transaction.set_rollback(True)
                return self.form_invalid(form)

class SalesReturnDeleteView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'sales.delete_salesreturn'
    
    def has_permission(self):
        if super().has_permission():
            return True
        if hasattr(self.request.user, 'salesrepresentative'):
            sales_return = get_object_or_404(SalesReturn, pk=self.kwargs.get('pk'))
            if sales_return.sales_rep == self.request.user.salesrepresentative and sales_return.status == 'draft':
                return True
        return False
        
    def post(self, request, pk):
        sales_return = get_object_or_404(SalesReturn, pk=pk)
        if sales_return.status != 'draft':
            messages.error(request, 'لا يمكن حذف المرتجع لأنه مرحل أو ملغي.')
        else:
            number = sales_return.number
            sales_return.delete()
            messages.success(request, f'تم حذف المرتجع {number} بنجاح.')
            
        if hasattr(request.user, 'salesrepresentative'):
            return redirect('reports:rep_dashboard')
        return redirect('sales:return-list')


class RepDetailsAPIView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'sales.view_salesrepresentative'
    def get(self, request, pk):
        rep = get_object_or_404(SalesRepresentative, pk=pk)
        return JsonResponse({
            'warehouse_id': rep.warehouse_id,
            'cash_box_id': rep.cash_box_id
        })

class CustomerInvoicesAPIView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'sales.view_salesinvoice'
    def get(self, request, customer_id):
        # Fetch posted invoices for this customer that have a remaining balance
        invoices = SalesInvoice.objects.filter(
            customer_id=customer_id,
            status=SalesInvoice.Status.POSTED
        ).annotate(
            remaining_balance=ExpressionWrapper(
                F('total') - F('paid_amount'),
                output_field=DecimalField()
            )
        ).filter(remaining_balance__gt=0).order_by('-date', '-id')
            
        data = [
            {
                'id': inv.id,
                'number': inv.number,
                'date': inv.date.isoformat(),
                'payment_type': inv.payment_type,
                'payment_type_display': inv.get_payment_type_display(),
                'cash_box_id': inv.cash_box_id,
                'total': float(inv.total),
                'remaining_balance': float(inv.remaining_balance)
            }
            for inv in invoices
        ]
        return JsonResponse({'invoices': data})

class CustomerDetailsAPIView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'sales.view_customer'
    def get(self, request, customer_id):
        customer = get_object_or_404(Customer, pk=customer_id)
        return JsonResponse({
            'is_taxable': customer.is_taxable,
            'price_list_id': customer.price_list_id,
            'sector_id': customer.sector_id,
            'default_tax1': customer.default_tax1_id,
            'default_tax2': customer.default_tax2_id,
            'customer_type': customer.customer_type,
            'payment_terms_days': customer.payment_terms_days
        })

class ItemPriceAndDiscountAPIView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'sales.view_salesinvoice'
    def get(self, request, item_id, customer_id):
        item = get_object_or_404(Item, pk=item_id)
        customer = get_object_or_404(Customer, pk=customer_id)
        
        today = date.today()
        discount_percent = Decimal('0')
        unit_price = item.standard_price
        
        # 1. Check Quotations (Promotions) first
        quotation = None
        # Prioritize Customer specific
        customer_quotations = Quotation.objects.filter(
            status=Quotation.Status.ACTIVE,
            is_active=True,
            start_date__lte=today,
            end_date__gte=today,
            customer=customer
        ).order_by('-id')
        
        if customer_quotations.exists():
            quotation = customer_quotations.first()
        elif customer.sector:
            sector_quotations = Quotation.objects.filter(
                status=Quotation.Status.ACTIVE,
                is_active=True,
                start_date__lte=today,
                end_date__gte=today,
                sector=customer.sector
            ).order_by('-id')
            if sector_quotations.exists():
                quotation = sector_quotations.first()
        
        if quotation:
            q_line = quotation.lines.filter(item=item).first()
            if q_line:
                discount_percent = q_line.discount_percent

        # 2. Check Price List
        if customer.price_list and customer.price_list.is_active:
            pl_item = customer.price_list.items.filter(item=item).first()
            if pl_item:
                unit_price = pl_item.unit_price

        return JsonResponse({
            'unit_price': float(unit_price),
            'discount_percent': float(discount_percent)
        })

class SalesInvoiceLinesAPIView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'sales.view_salesinvoice'
    def get(self, request, invoice_id):
        lines = SalesInvoiceLine.objects.filter(invoice_id=invoice_id).select_related('item', 'unit', 'warehouse')

        # Single aggregate query for all returned quantities per item
        returned_qties = SalesReturnLine.objects.filter(
            sales_return__invoice_id=invoice_id,
        ).exclude(sales_return__status='cancelled').values('item_id').annotate(
            total=Coalesce(Sum('base_quantity'), Decimal('0'))
        )
        returned_map = {r['item_id']: r['total'] for r in returned_qties}

        data = []
        for line in lines:
            returned_base_qty = returned_map.get(line.item_id, Decimal('0'))
            max_base_returnable = max(0.0, float(line.base_quantity) - float(returned_base_qty))

            data.append({
                'item_id': line.item_id,
                'item_name': line.item.name,
                'unit_id': line.unit_id,
                'unit_name': line.unit.name if line.unit else '',
                'warehouse_id': line.warehouse_id,
                'warehouse_name': line.warehouse.name if line.warehouse else '',
                'quantity': float(line.quantity),
                'base_quantity': float(line.base_quantity),
                'returned_base_quantity': float(returned_base_qty),
                'max_base_returnable': max_base_returnable,
                'unit_price': float(line.unit_price),
                'discount_percent': float(line.discount_percent),
                'tax_type_id': line.tax_type_id,
                'tax_percent': float(line.tax_percent or 0),
                'tax_type2_id': line.tax_type2_id,
                'tax_percent2': float(line.tax_percent2 or 0),
            })
        return JsonResponse({'lines': data})
class RepStockStatusView(LoginRequiredMixin, PermRequiredMixin, TemplateView):
    """عرض بضاعة المندوب الحالية في مخزنه الخاص"""
    template_name = 'sales/reps/my_stock.html'
    permission_required = 'sales.view_salesrepresentative'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            # التأكد من أن المستخدم مرتبط بملف مندوب
            rep = self.request.user.salesrepresentative
            context['rep'] = rep
            context['report'] = ReportService.stock_status(warehouse_id=rep.warehouse_id)
        except SalesRepresentative.DoesNotExist:
            messages.error(self.request, "عفواً، حسابك غير مرتبط بملف مندوب مبيعات.")
            context['error'] = True
        return context
