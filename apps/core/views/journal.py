from django.db import models
from django.views.generic import ListView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.urls import reverse
from ..models import JournalEntry
from ..services import JournalService
from django.utils import timezone
from datetime import date
from decimal import Decimal

class JournalEntryListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = JournalEntry
    template_name = 'core/journal/list.html'
    context_object_name = 'entries'
    permission_required = 'core.view_journalentry'
    paginate_by = 50
    ordering = ['-date', '-id']

    def get_queryset(self):
        queryset = super().get_queryset()
        q = self.request.GET.get('q')
        date_filter = self.request.GET.get('date')
        
        if q:
            queryset = queryset.filter(
                models.Q(number__icontains=q) | 
                models.Q(description__icontains=q)
            )
        if date_filter:
            queryset = queryset.filter(date=date_filter)
            
        return queryset

class JournalEntryDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = JournalEntry
    template_name = 'core/journal/detail.html'
    context_object_name = 'entry'
    permission_required = 'core.view_journalentry'

class JournalEntryReverseView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'core.change_journalentry'

    def post(self, request, pk):
        entry = get_object_or_404(JournalEntry, pk=pk)
        
        if entry.entry_type in [JournalEntry.EntryType.OPENING, JournalEntry.EntryType.CLOSING]:
            messages.error(request, "لا يمكن عكس قيود الافتتاح أو الإقفال.")
            return redirect('core:journal-detail', pk=pk)
            
        if entry.is_reversed:
            messages.error(request, "هذا القيد معكوس بالفعل.")
            return redirect('core:journal-detail', pk=pk)
        
        try:
            new_entry = JournalService.reverse_entry(entry, date.today(), request.user)
            messages.success(request, f"تم عكس القيد بنجاح. رقم القيد الجديد: {new_entry.number}")
            return redirect('core:journal-detail', pk=new_entry.pk)
        except Exception as e:
            messages.error(request, f"خطأ أثناء عكس القيد: {e}")
            return redirect('core:journal-detail', pk=pk)

from django.views.generic import CreateView
from ..forms import JournalEntryForm, JournalLineFormSet
from django.db import transaction

class JournalEntryCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = JournalEntry
    form_class = JournalEntryForm
    template_name = 'core/journal/form.html'
    permission_required = 'core.add_journalentry'

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['lines'] = JournalLineFormSet(self.request.POST)
        else:
            data['lines'] = JournalLineFormSet()
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        lines = context['lines']
        with transaction.atomic():
            form.instance.created_by = self.request.user
            
            # Generate Number
            from ..services import DocumentService
            form.instance.number = DocumentService.generate_number(JournalEntry, 'JE')
            form.instance.is_posted = True  # Manual journal entries are posted immediately
            form.instance.posted_by = self.request.user
            form.instance.posted_at = timezone.now()
            
            # Find Fiscal Year
            from ..models import FiscalYear
            fiscal_year = FiscalYear.objects.filter(
                start_date__lte=form.instance.date,
                end_date__gte=form.instance.date,
                is_closed=False
            ).first()
            
            if not fiscal_year:
                messages.error(self.request, 'لا توجد سنة مالية مفتوحة تتوافق مع تاريخ القيد')
                return self.form_invalid(form)
                
            form.instance.fiscal_year = fiscal_year
            
            if lines.is_valid():
                # Validate balances
                total_debit = sum(Decimal(str(l.cleaned_data.get('debit') or 0)) for l in lines.forms if not l.cleaned_data.get('DELETE'))
                total_credit = sum(Decimal(str(l.cleaned_data.get('credit') or 0)) for l in lines.forms if not l.cleaned_data.get('DELETE'))
                
                if total_debit != total_credit:
                    messages.error(self.request, f'القيد غير متزن. إجمالي المدين: {total_debit}، إجمالي الدائن: {total_credit}')
                    return self.form_invalid(form)
                if total_debit == 0:
                    messages.error(self.request, 'القيد صفري ولا يحتوي على مبالغ')
                    return self.form_invalid(form)

                self.object = form.save()
                lines.instance = self.object
                lines.save()
            else:
                return self.form_invalid(form)
                
        messages.success(self.request, f'تم إنشاء قيد اليومية رقم {self.object.number} بنجاح.')
        return redirect('core:journal-detail', pk=self.object.pk)

class JournalEntryPostView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'core.change_journalentry'

    def post(self, request, pk):
        entry = get_object_or_404(JournalEntry, pk=pk)
        if entry.is_posted:
            messages.error(request, "هذا القيد مرحل بالفعل.")
        else:
            entry.is_posted = True
            entry.posted_by = request.user
            entry.posted_at = timezone.now()
            entry.save()
            from ..services import AuditService
            AuditService.log(request.user, 'Post', entry, f'ترحيل يدوي للقيد {entry.number}')
            messages.success(request, f"تم ترحيل القيد {entry.number} بنجاح.")
        return redirect('core:journal-detail', pk=pk)
