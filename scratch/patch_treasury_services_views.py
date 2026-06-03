import re

def main():
    # 1. services.py
    file_path = 'apps/treasury/services.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    # 1.a. Account DoesNotExist catch
    old_account = """        transit_account = Account.objects.select_for_update().get(
            code=getattr(settings, 'CASH_IN_TRANSIT_ACCOUNT', '1114')
        )"""
    new_account = """        try:
            transit_account = Account.objects.select_for_update().get(
                code=getattr(settings, 'CASH_IN_TRANSIT_ACCOUNT', '1114')
            )
        except Account.DoesNotExist:
            raise ValueError("حساب نقدية بالطريق (1114) غير معرف، يرجى مراجعة الدليل المحاسبي")"""
    content = content.replace(old_account, new_account)

    # Need to do the same for BANK_CHARGES_ACCOUNT (usually 5...) - let's see if it's there
    old_bank_charge = """        bank_charges_account = Account.objects.select_for_update().get(
            code=getattr(settings, 'BANK_CHARGES_ACCOUNT', '512')
        )"""
    new_bank_charge = """        try:
            bank_charges_account = Account.objects.select_for_update().get(
                code=getattr(settings, 'BANK_CHARGES_ACCOUNT', '512')
            )
        except Account.DoesNotExist:
            raise ValueError("حساب عمولات بنكية (512) غير معرف، يرجى مراجعة الدليل المحاسبي")"""
    content = content.replace(old_bank_charge, new_bank_charge)
    
    # And CHEQUES_UNDER_COLLECTION
    old_cheque_coll = """        cheques_account = Account.objects.select_for_update().get(
            code=getattr(settings, 'CHEQUES_UNDER_COLLECTION_ACCOUNT', '1125')
        )"""
    new_cheque_coll = """        try:
            cheques_account = Account.objects.select_for_update().get(
                code=getattr(settings, 'CHEQUES_UNDER_COLLECTION_ACCOUNT', '1125')
            )
        except Account.DoesNotExist:
            raise ValueError("حساب شيكات تحت التحصيل (1125) غير معرف")"""
    content = content.replace(old_cheque_coll, new_cheque_coll)

    # 1.b. create_mobile_wallet Race condition
    old_create_mobile = """        try:
            parent = Account.objects.select_for_update().get(code=TreasuryService.MOBILE_WALLET_PARENT_CODE)
        except Account.DoesNotExist:
            grandparent = Account.objects.select_for_update().get(code='111')
            parent = Account.objects.create(
                code=TreasuryService.MOBILE_WALLET_PARENT_CODE,
                name='المحافظ الإلكترونية',
                account_type=grandparent.account_type,
                parent=grandparent,
                is_leaf=False
            )"""
    new_create_mobile = """        try:
            parent = Account.objects.select_for_update().get(code=TreasuryService.MOBILE_WALLET_PARENT_CODE)
        except Account.DoesNotExist:
            grandparent = Account.objects.select_for_update().get(code='111')
            parent, created = Account.objects.get_or_create(
                code=TreasuryService.MOBILE_WALLET_PARENT_CODE,
                defaults={
                    'name': 'المحافظ الإلكترونية',
                    'account_type': grandparent.account_type,
                    'parent': grandparent,
                    'is_leaf': False
                }
            )"""
    content = content.replace(old_create_mobile, new_create_mobile)

    # 1.c. BankReconciliationService Deadlock
    old_recon_lock = "        for trans in BankTransaction.objects.filter(pk__in=trans_ids).select_for_update():"
    new_recon_lock = "        for trans in BankTransaction.objects.filter(pk__in=trans_ids).select_for_update().order_by('pk'):"
    content = content.replace(old_recon_lock, new_recon_lock)

    # 1.d. process_receive and reverse_transfer Dates
    old_proc_rec = "    def process_receive(transfer, received_by) -> JournalEntry:"
    new_proc_rec = "    def process_receive(transfer, received_by, receive_date=None) -> JournalEntry:"
    content = content.replace(old_proc_rec, new_proc_rec)
    content = content.replace("            date_val=timezone.now().date(),\n            entry_type=JournalEntry.EntryType.BANK,", "            date_val=receive_date or timezone.now().date(),\n            entry_type=JournalEntry.EntryType.BANK,")
    
    old_rev_trans = "    def reverse_transfer(transfer, reversed_by, reason) -> list[JournalEntry]:"
    new_rev_trans = "    def reverse_transfer(transfer, reversed_by, reason, reversal_date=None) -> list[JournalEntry]:"
    content = content.replace(old_rev_trans, new_rev_trans)
    content = content.replace("            reversal_date = timezone.now().date()", "            reversal_date = reversal_date or timezone.now().date()")

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Services patched.")


    # 2. views.py
    file_path = 'apps/treasury/views.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    # 2.a. CashBoxMovementReportView Opening Balance and permissions
    old_movement_qs = """        # Optional filtering by specific cash box
        selected_box = self.request.GET.get('cash_box')
        if selected_box:
            box = get_object_or_404(CashBox, pk=selected_box)
            movements_qs = movements_qs.filter(account=box.account)
        else:
            box = None

        if start_date:
            movements_qs = movements_qs.filter(entry__date__gte=start_date)
        if end_date:
            movements_qs = movements_qs.filter(entry__date__lte=end_date)

        movements = movements_qs.order_by('entry__date', 'entry__number')

        # Calculate opening balance
        opening_balance = Decimal('0')
        if box:
            if start_date:
                prev_date = date.fromisoformat(start_date) - timedelta(days=1)
                opening_balance = get_account_balance(box.account, as_of_date=prev_date)
            else:
                opening_balance = box.account.initial_balance if box.account.initial_balance_type == 'debit' else -box.account.initial_balance

        running_balance = opening_balance
        for mv in movements:
            running_balance += (mv.debit - mv.credit)
            mv.running_balance = running_balance"""
            
    new_movement_qs = """        # Security: restrict to authorized boxes
        available_boxes = get_available_cash_boxes(self.request.user)
        selected_box = self.request.GET.get('cash_box')
        if selected_box:
            box = get_object_or_404(available_boxes, pk=selected_box)
            movements_qs = movements_qs.filter(account=box.account)
        else:
            box = None
            box_accounts = available_boxes.values_list('account_id', flat=True)
            movements_qs = movements_qs.filter(account_id__in=box_accounts)

        if start_date:
            movements_qs = movements_qs.filter(entry__date__gte=start_date)
        if end_date:
            movements_qs = movements_qs.filter(entry__date__lte=end_date)

        movements = movements_qs.order_by('entry__date', 'entry__number')

        # Calculate opening balance correctly without duplicating initial balance
        opening_balance = Decimal('0')
        if box:
            if start_date:
                prev_date = date.fromisoformat(start_date) - timedelta(days=1)
                opening_balance = get_account_balance(box.account, as_of_date=prev_date)
            else:
                has_opening = JournalLine.objects.filter(
                    account=box.account, entry__entry_type='opening', entry__is_posted=True
                ).exists()
                if not has_opening:
                    opening_balance = box.account.initial_balance if box.account.initial_balance_type == 'debit' else -box.account.initial_balance

        running_balance = opening_balance
        for mv in movements:
            if box:
                running_balance += (mv.debit - mv.credit)
                mv.running_balance = running_balance
            else:
                mv.running_balance = None"""
    content = content.replace(old_movement_qs, new_movement_qs)

    # 2.b. Adding get_queryset to CashBox Detail/Update, BankAccount, MobileWallet
    # Just inject them using simple replaces
    
    cb_detail = "class CashBoxDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):\n    model = CashBox\n    template_name = 'treasury/cashbox_detail.html'\n    permission_required = 'treasury.view_cashbox'"
    cb_detail_new = cb_detail + "\n    def get_queryset(self):\n        return get_available_cash_boxes(self.request.user)"
    content = content.replace(cb_detail, cb_detail_new)
    
    cb_update = "class CashBoxUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):\n    model = CashBox\n    form_class = CashBoxForm\n    template_name = 'treasury/cashbox_form.html'\n    success_url = reverse_lazy('treasury:cashbox-list')\n    permission_required = 'treasury.change_cashbox'"
    cb_update_new = cb_update + "\n    def get_queryset(self):\n        return get_available_cash_boxes(self.request.user)"
    content = content.replace(cb_update, cb_update_new)
    
    ba_detail = "class BankAccountDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):\n    model = BankAccount\n    template_name = 'treasury/bank_detail.html'\n    permission_required = 'treasury.view_bankaccount'"
    ba_detail_new = ba_detail + "\n    def get_queryset(self):\n        return super().get_queryset().filter(is_active=True)"
    content = content.replace(ba_detail, ba_detail_new)

    ba_update = "class BankAccountUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):\n    model = BankAccount\n    form_class = BankAccountForm\n    template_name = 'treasury/bank_form.html'\n    success_url = reverse_lazy('treasury:bank-list')\n    permission_required = 'treasury.change_bankaccount'"
    ba_update_new = ba_update + "\n    def get_queryset(self):\n        return super().get_queryset().filter(is_active=True)"
    content = content.replace(ba_update, ba_update_new)
    
    mw_detail = "class MobileWalletDetailView(LoginRequiredMixin, PermRequiredMixin, DetailView):\n    model = MobileWallet\n    template_name = 'treasury/wallet_detail.html'\n    permission_required = 'treasury.view_mobilewallet'"
    mw_detail_new = mw_detail + "\n    def get_queryset(self):\n        return super().get_queryset().filter(is_active=True)"
    content = content.replace(mw_detail, mw_detail_new)

    mw_update = "class MobileWalletUpdateView(LoginRequiredMixin, PermRequiredMixin, UpdateView):\n    model = MobileWallet\n    form_class = MobileWalletForm\n    template_name = 'treasury/wallet_form.html'\n    success_url = reverse_lazy('treasury:wallet-list')\n    permission_required = 'treasury.change_mobilewallet'"
    mw_update_new = mw_update + "\n    def get_queryset(self):\n        return super().get_queryset().filter(is_active=True)"
    content = content.replace(mw_update, mw_update_new)

    # 2.c. CashTransferCreateView Exception block
    old_xfer_create = """    def form_valid(self, form):
        with transaction.atomic():
            form.instance.number = DocumentService.generate_number(CashTransfer, 'XFER')
            form.instance.status = CashTransfer.Status.DRAFT
            self.object = form.save()
            
            # Process the issue side of the transfer
            TreasuryService.process_issue(self.object, self.request.user)
            
        messages.success(self.request, f'تم إنشاء التحويل {self.object.number} وصرفه من المصدر (قيد الانتظار)')
        return redirect('treasury:transfer-detail', pk=self.object.pk)"""
    new_xfer_create = """    def form_valid(self, form):
        try:
            with transaction.atomic():
                form.instance.number = DocumentService.generate_number(CashTransfer, 'XFER')
                form.instance.status = CashTransfer.Status.DRAFT
                self.object = form.save()
                
                # Process the issue side of the transfer
                TreasuryService.process_issue(self.object, self.request.user)
                
            messages.success(self.request, f'تم إنشاء التحويل {self.object.number} وصرفه من المصدر (قيد الانتظار)')
            return redirect('treasury:transfer-detail', pk=self.object.pk)
        except Exception as e:
            messages.error(self.request, f'خطأ أثناء إنشاء التحويل: {e}')
            return self.form_invalid(form)"""
    content = content.replace(old_xfer_create, new_xfer_create)

    # 2.d. Http404 swallows in POST views
    # CashTransferReceiveView
    old_xfer_receive = """    def post(self, request, pk):
        try:
            with transaction.atomic():
                transfer = get_object_or_404(CashTransfer.objects.select_for_update(), pk=pk)
                TreasuryService.process_receive(transfer, request.user)
            messages.success(request, f'تم تأكيد استلام التحويل {transfer.number} بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ أثناء التأكيد: {e}')
        return redirect('treasury:transfer-detail', pk=pk)"""
    new_xfer_receive = """    def post(self, request, pk):
        transfer = get_object_or_404(CashTransfer, pk=pk)
        try:
            with transaction.atomic():
                transfer = CashTransfer.objects.select_for_update().get(pk=pk)
                TreasuryService.process_receive(transfer, request.user)
            messages.success(request, f'تم تأكيد استلام التحويل {transfer.number} بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ أثناء التأكيد: {e}')
        return redirect('treasury:transfer-detail', pk=pk)"""
    content = content.replace(old_xfer_receive, new_xfer_receive)

    # CashTransferReverseView
    old_xfer_reverse = """    def post(self, request, pk):
        try:
            with transaction.atomic():
                transfer = get_object_or_404(CashTransfer.objects.select_for_update(), pk=pk)
                reason = request.POST.get('reason', 'تم الإلغاء بواسطة المستخدم')
                TreasuryService.reverse_transfer(transfer, request.user, reason)
            messages.success(request, f'تم إلغاء التحويل {transfer.number} بنجاح وعكس القيود')
        except Exception as e:
            messages.error(request, f'خطأ أثناء الإلغاء: {e}')
        return redirect('treasury:transfer-detail', pk=pk)"""
    new_xfer_reverse = """    def post(self, request, pk):
        transfer = get_object_or_404(CashTransfer, pk=pk)
        try:
            with transaction.atomic():
                transfer = CashTransfer.objects.select_for_update().get(pk=pk)
                reason = request.POST.get('reason', 'تم الإلغاء بواسطة المستخدم')
                TreasuryService.reverse_transfer(transfer, request.user, reason)
            messages.success(request, f'تم إلغاء التحويل {transfer.number} بنجاح وعكس القيود')
        except Exception as e:
            messages.error(request, f'خطأ أثناء الإلغاء: {e}')
        return redirect('treasury:transfer-detail', pk=pk)"""
    content = content.replace(old_xfer_reverse, new_xfer_reverse)

    # BankTransactionPostView
    old_btrans_post = """    def post(self, request, pk):
        try:
            with transaction.atomic():
                trans = get_object_or_404(BankTransaction.objects.select_for_update(), pk=pk)
                TreasuryService.process_bank_transaction(trans, request.user)
            messages.success(request, f'تم ترحيل الحركة رقم {trans.id} بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ أثناء الترحيل: {e}')
        return redirect('treasury:bank-transaction-list')"""
    new_btrans_post = """    def post(self, request, pk):
        trans = get_object_or_404(BankTransaction, pk=pk)
        try:
            with transaction.atomic():
                trans = BankTransaction.objects.select_for_update().get(pk=pk)
                TreasuryService.process_bank_transaction(trans, request.user)
            messages.success(request, f'تم ترحيل الحركة رقم {trans.id} بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ أثناء الترحيل: {e}')
        return redirect('treasury:bank-transaction-list')"""
    content = content.replace(old_btrans_post, new_btrans_post)

    # BankReconciliationMatchView
    old_recon_match = """    def post(self, request, pk):
        try:
            with transaction.atomic():
                recon = get_object_or_404(BankReconciliation.objects.select_for_update(), pk=pk)
                BankReconciliationService.match_transactions(recon, request.user)
            messages.success(request, f'تم معالجة تسوية كشف البنك بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ أثناء التسوية: {e}')
        return redirect('treasury:bankreconciliation-detail', pk=pk)"""
    new_recon_match = """    def post(self, request, pk):
        recon = get_object_or_404(BankReconciliation, pk=pk)
        try:
            with transaction.atomic():
                recon = BankReconciliation.objects.select_for_update().get(pk=pk)
                BankReconciliationService.match_transactions(recon, request.user)
            messages.success(request, f'تم معالجة تسوية كشف البنك بنجاح')
        except Exception as e:
            messages.error(request, f'خطأ أثناء التسوية: {e}')
        return redirect('treasury:bankreconciliation-detail', pk=pk)"""
    content = content.replace(old_recon_match, new_recon_match)

    # 2.e. BankReconciliationUpdateView Partial save & Lock
    old_recon_upd = """    def dispatch(self, request, *args, **kwargs):
        # Prevent editing if reconciled
        with transaction.atomic():
            obj = get_object_or_404(BankReconciliation.objects.select_for_update(), pk=kwargs.get('pk'))
            if obj.is_reconciled:
                messages.error(request, "لا يمكن تعديل تسوية بنكية منتهية.")
                return redirect('treasury:bankreconciliation-detail', pk=obj.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        with transaction.atomic():
            obj = form.save(commit=False)
            obj.difference = obj.statement_balance - obj.book_balance
            obj.save(update_fields=['statement_balance', 'book_balance', 'difference', 'notes', 'attachment'])
        messages.success(self.request, f'تم تحديث تسوية بنكية للبيان {obj.statement_date}')
        return redirect(self.success_url)"""
        
    new_recon_upd = """    def dispatch(self, request, *args, **kwargs):
        obj = get_object_or_404(BankReconciliation, pk=kwargs.get('pk'))
        if obj.is_reconciled:
            messages.error(request, "لا يمكن تعديل تسوية بنكية منتهية.")
            return redirect('treasury:bankreconciliation-detail', pk=obj.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        with transaction.atomic():
            obj = form.save(commit=False)
            obj.difference = obj.statement_balance - obj.book_balance
            obj.save()
        messages.success(self.request, f'تم تحديث تسوية بنكية للبيان {obj.statement_date}')
        return redirect(self.success_url)"""
    content = content.replace(old_recon_upd, new_recon_upd)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Views patched.")

if __name__ == '__main__':
    main()
