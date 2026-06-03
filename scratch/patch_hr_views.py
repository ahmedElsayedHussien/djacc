import re

def main():
    file_path = 'apps/hr/views.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    # GeneratePayslipsView
    old_gen_pay = """    def post(self, request, pk):
        try:
            with transaction.atomic():
                period = get_object_or_404(PayrollPeriod.objects.select_for_update(), pk=pk)"""
    new_gen_pay = """    def post(self, request, pk):
        period = get_object_or_404(PayrollPeriod, pk=pk)
        if period.status != PayrollPeriod.Status.DRAFT:
            messages.error(request, 'لا يمكن توليد قسائم الراتب لفترة ليست مسودة.')
            return redirect('hr:payroll-detail', pk=pk)
        try:
            with transaction.atomic():
                period = PayrollPeriod.objects.select_for_update().get(pk=pk)"""
    content = content.replace(old_gen_pay, new_gen_pay)

    # PostPayrollView
    old_post_pay = """    def post(self, request, pk):
        try:
            with transaction.atomic():
                period = get_object_or_404(PayrollPeriod.objects.select_for_update(), pk=pk)"""
    new_post_pay = """    def post(self, request, pk):
        period = get_object_or_404(PayrollPeriod, pk=pk)
        if period.status != PayrollPeriod.Status.APPROVED:
            messages.error(request, 'يجب اعتماد مسير الرواتب قبل الترحيل المحاسبي.')
            return redirect('hr:payroll-detail', pk=pk)
        try:
            with transaction.atomic():
                period = PayrollPeriod.objects.select_for_update().get(pk=pk)"""
    content = content.replace(old_post_pay, new_post_pay)

    # PostPaymentView
    old_paym = """    def post(self, request, pk):
        try:
            with transaction.atomic():
                period = get_object_or_404(PayrollPeriod.objects.select_for_update(), pk=pk)"""
    new_paym = """    def post(self, request, pk):
        period = get_object_or_404(PayrollPeriod, pk=pk)
        if period.payment_entry:
            messages.error(request, 'تم صرف الرواتب مسبقاً.')
            return redirect('hr:payroll-detail', pk=pk)
        try:
            with transaction.atomic():
                period = PayrollPeriod.objects.select_for_update().get(pk=pk)"""
    content = content.replace(old_paym, new_paym)

    # PostEOSView
    old_eos_post = """    def post(self, request, pk):
        try:
            with transaction.atomic():
                record = get_object_or_404(EndOfService.objects.select_for_update(), pk=pk)"""
    new_eos_post = """    def post(self, request, pk):
        record = get_object_or_404(EndOfService, pk=pk)
        if record.is_processed:
            messages.error(request, 'تم تسوية نهاية الخدمة مسبقاً.')
            return redirect('hr:eos-list')
        try:
            with transaction.atomic():
                record = EndOfService.objects.select_for_update().get(pk=pk)"""
    content = content.replace(old_eos_post, new_eos_post)

    # ApproveLeaveView Race condition
    old_leave_app = """        leave = get_object_or_404(LeaveRequest, pk=pk)
        if leave.status != LeaveRequest.Status.PENDING:
            messages.error(request, 'لا يمكن تغيير حالة طلب ليس قيد الانتظار.')
            return redirect('hr:leave-list')

        try:
            with transaction.atomic():
                balance = LeaveBalance.objects.select_for_update().filter(
                    employee=leave.employee,
                    leave_type=leave.leave_type,
                    year=leave.start_date.year
                ).first()"""
    new_leave_app = """        try:
            with transaction.atomic():
                leave = LeaveRequest.objects.select_for_update().get(pk=pk)
                if leave.status != LeaveRequest.Status.PENDING:
                    messages.error(request, 'لا يمكن تغيير حالة طلب ليس قيد الانتظار.')
                    return redirect('hr:leave-list')

                balance = LeaveBalance.objects.select_for_update().filter(
                    employee=leave.employee,
                    leave_type=leave.leave_type,
                    year=leave.start_date.year
                ).first()"""
    content = content.replace(old_leave_app, new_leave_app)

    # PostGovPaymentView negative amounts
    old_gov_post = """        ins_amount = safe_decimal(request.POST.get('ins_amount'))
        tax_amount = safe_decimal(request.POST.get('tax_amount'))"""
    new_gov_post = """        ins_amount = safe_decimal(request.POST.get('ins_amount'))
        tax_amount = safe_decimal(request.POST.get('tax_amount'))
        
        if ins_amount < 0 or tax_amount < 0:
            messages.error(request, 'لا يمكن إدخال قيم سالبة.')
            return redirect('hr:payroll-detail', pk=pk)"""
    content = content.replace(old_gov_post, new_gov_post)

    # employee_reset_password privilege escalation
    old_pwd = """    employee = get_object_or_404(Employee, pk=pk)
    if not employee.user:
        return JsonResponse({'success': False, 'error': 'هذا الموظف غير مرتبط بمستخدم نظام.'}, status=400)"""
    new_pwd = """    employee = get_object_or_404(Employee, pk=pk)
    if not employee.user:
        return JsonResponse({'success': False, 'error': 'هذا الموظف غير مرتبط بمستخدم نظام.'}, status=400)
    if employee.user.is_superuser and not request.user.is_superuser:
        return JsonResponse({'success': False, 'error': 'غير مصرح لك بتغيير كلمة مرور مدير النظام.'}, status=403)"""
    content = content.replace(old_pwd, new_pwd)

    # LeaveBalanceCreateView exception handling
    old_bal_fv = """    def form_valid(self, form):
        employee = get_object_or_404(Employee, pk=self.kwargs.get('emp_pk'))
        form.instance.employee = employee
        messages.success(self.request, 'تم إضافة رصيد إجازات بنجاح')
        return super().form_valid(form)"""
    new_bal_fv = """    def form_valid(self, form):
        employee = get_object_or_404(Employee, pk=self.kwargs.get('emp_pk'))
        form.instance.employee = employee
        try:
            form.instance.validate_unique()
        except ValidationError as e:
            form.add_error(None, e)
            return self.form_invalid(form)
        messages.success(self.request, 'تم إضافة رصيد إجازات بنجاح')
        return super().form_valid(form)"""
    content = content.replace(old_bal_fv, new_bal_fv)

    # DailyAttendanceView isoformat
    old_att_get = """    def get(self, request):
        date_str = request.GET.get('date', date.today().isoformat())
        target_date = date.fromisoformat(date_str)"""
    new_att_get = """    def get(self, request):
        date_str = request.GET.get('date', date.today().isoformat())
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            target_date = date.today()"""
    content = content.replace(old_att_get, new_att_get)
    
    old_att_post = """    def post(self, request):
        date_str = request.POST.get('date')
        target_date = date.fromisoformat(date_str)"""
    new_att_post = """    def post(self, request):
        date_str = request.POST.get('date')
        try:
            target_date = date.fromisoformat(date_str)
        except (ValueError, TypeError):
            messages.error(request, 'تنسيق التاريخ غير صحيح.')
            return redirect('hr:attendance-daily')"""
    content = content.replace(old_att_post, new_att_post)

    # PayslipUpdateView
    old_pay_upd = """class PayslipUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):
    model = Payslip
    form_class = PayslipForm
    template_name = 'hr/payslip_form.html'
    permission_required = 'hr.change_payslip'

    def get_success_url(self):"""
    new_pay_upd = """class PayslipUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):
    model = Payslip
    form_class = PayslipForm
    template_name = 'hr/payslip_form.html'
    permission_required = 'hr.change_payslip'

    def dispatch(self, request, *args, **kwargs):
        payslip = self.get_object()
        if payslip.period.status != PayrollPeriod.Status.DRAFT:
            messages.error(request, 'لا يمكن تعديل قسيمة الراتب لفترة مغلقة.')
            return redirect('hr:payroll-detail', pk=payslip.period.pk)
        return super().dispatch(request, *args, **kwargs)

    @transaction.atomic
    def form_valid(self, form):
        return super().form_valid(form)

    def get_success_url(self):"""
    content = content.replace(old_pay_upd, new_pay_upd)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Views patched.")

if __name__ == '__main__':
    main()
