from django.db import models
from django.views.generic import ListView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from apps.core.mixins import PermRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.urls import reverse
from ..models import JournalEntry, FiscalYear, SystemNotification
from ..services import JournalService, DocumentService, AuditService
from django.utils import timezone
from datetime import date
from decimal import Decimal

class JournalEntryListView(LoginRequiredMixin, PermRequiredMixin, ListView):
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

class JournalEntryDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):
    model = JournalEntry
    template_name = 'core/journal/detail.html'
    context_object_name = 'entry'
    permission_required = 'core.view_journalentry'

class JournalEntryReverseView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_superuser

    def post(self, request, pk):
        entry = get_object_or_404(JournalEntry, pk=pk)
        
        if entry.entry_type in [JournalEntry.EntryType.OPENING, JournalEntry.EntryType.CLOSING]:
            messages.error(request, "لا يمكن عكس قيود الافتتاح أو الإقفال.")
            return redirect('core:journal-detail', pk=pk)
            
        if entry.is_reversed:
            messages.error(request, "هذا القيد معكوس بالفعل.")
            return redirect('core:journal-detail', pk=pk)

        if entry.is_reversal:
            messages.error(request, "لا يمكن عكس قيد هو في الأصل قيد إلغاء/عكس.")
            return redirect('core:journal-detail', pk=pk)
        
        try:
            new_entry = JournalService.reverse_entry(entry, date.today(), request.user)
            
            # Trigger notification for reversed journal entry
            title = f"عكس قيد يومية"
            message = f"قام المستخدم {request.user.username} بعكس قيد اليومية رقم {entry.number} وإنشاء قيد عكسي جديد رقم {new_entry.number}."
            url = reverse('core:journal-detail', args=[new_entry.id])
            SystemNotification.notify_accountants(title, message, url)
            
            messages.success(request, f"تم عكس القيد بنجاح. رقم القيد الجديد: {new_entry.number}")
            return redirect('core:journal-detail', pk=pk)
        except Exception as e:
            messages.error(request, f"خطأ أثناء عكس القيد: {e}")
            return redirect('core:journal-detail', pk=pk)

from django.views.generic import CreateView
from ..forms import JournalEntryForm, JournalLineFormSet
from django.db import transaction

class JournalEntryCreateView(LoginRequiredMixin, PermRequiredMixin, CreateView):
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
            form.instance.number = DocumentService.generate_number(JournalEntry, 'JE')
            form.instance.is_posted = True  # Manual journal entries are posted immediately
            form.instance.posted_by = self.request.user
            form.instance.posted_at = timezone.now()
            
            # Find Fiscal Year
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
            
            AuditService.log(self.request.user, 'Create & Post', self.object,
                             f'إنشاء قيد يدوي رقم {self.object.number} - {self.object.description}')
                
        messages.success(self.request, f'تم إنشاء قيد اليومية رقم {self.object.number} بنجاح.')
        return redirect('core:journal-detail', pk=self.object.pk)

class JournalEntryPostView(LoginRequiredMixin, PermRequiredMixin, View):
    permission_required = 'core.change_journalentry'

    def post(self, request, pk):
        entry = get_object_or_404(JournalEntry, pk=pk)
        if entry.is_posted:
            messages.error(request, "هذا القيد مرحل بالفعل.")
        elif entry.fiscal_year and entry.fiscal_year.is_closed:
            messages.error(request, "لا يمكن ترحيل قيد في سنة مالية مقفلة.")
        else:
            total_debit = sum(line.debit for line in entry.lines.all())
            total_credit = sum(line.credit for line in entry.lines.all())
            if total_debit != total_credit:
                messages.error(request, f"القيد غير متزن. إجمالي المدين: {total_debit}، إجمالي الدائن: {total_credit}")
                return redirect('core:journal-detail', pk=pk)
                
            entry.is_posted = True
            entry.posted_by = request.user
            entry.posted_at = timezone.now()
            entry.save()
            AuditService.log(request.user, 'Post', entry, f'ترحيل يدوي للقيد {entry.number}')
            messages.success(request, f"تم ترحيل القيد {entry.number} بنجاح.")
        return redirect('core:journal-detail', pk=pk)
