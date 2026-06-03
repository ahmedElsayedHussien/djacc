import re

def main():
    file_path = 'apps/purchases/views.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    # 1. SupplierPaymentCreateView.form_valid - Remove double counting of paid_amount and add try/except
    old_sp_fv = """    def form_valid(self, form):
        context = self.get_context_data()
        allocations = context['allocations']
        if not allocations.is_valid():
            return self.form_invalid(form)

        with transaction.atomic():
            self.object = form.save(commit=False)
            self.object.created_by = self.request.user
            self.object.save()
            allocations.instance = self.object
            allocations.save()
            
            # Manual increment
            for alloc in allocations.forms:
                if not alloc.cleaned_data.get('DELETE'):
                    inv = alloc.cleaned_data.get('invoice')
                    alloc_amount = alloc.cleaned_data.get('amount')
                    if inv and alloc_amount:
                        inv.paid_amount += alloc_amount
                        inv.save(update_fields=['paid_amount'])

            PurchaseService.record_payment(self.object, self.request.user)
            messages.success(self.request, f'تم تسجيل سند الصرف {self.object.number} وترحيله')
            
        return super().form_valid(form)"""
        
    new_sp_fv = """    def form_valid(self, form):
        context = self.get_context_data()
        allocations = context['allocations']
        if not allocations.is_valid():
            return self.form_invalid(form)

        try:
            with transaction.atomic():
                self.object = form.save(commit=False)
                self.object.created_by = self.request.user
                self.object.save()
                allocations.instance = self.object
                allocations.save()

                PurchaseService.record_payment(self.object, self.request.user)
                messages.success(self.request, f'تم تسجيل سند الصرف {self.object.number} وترحيله')
        except Exception as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)
            
        return super().form_valid(form)"""
    content = content.replace(old_sp_fv, new_sp_fv)

    # 2. PurchaseReturnCreateView Bypass of return limits
    # The view processes lines in a loop. We need to replace the logic.
    old_pr_cv_loop = """            for line in instances:
                original_line = PurchaseInvoiceLine.objects.filter(
                    invoice=self.object.invoice,
                    item=line.item
                ).first()
                
                if not original_line:
                    line.add_error('item', 'هذا الصنف غير موجود في الفاتورة الأصلية')
                    continue
                    
                previous_returned = PurchaseReturnLine.objects.filter(
                    purchase_return__invoice=self.object.invoice,
                    purchase_return__status='posted',
                    item=line.item
                ).aggregate(total=Sum('quantity'))['total'] or 0
                
                available = original_line.quantity - previous_returned
                if line.quantity > available:
                    raise ValidationError(f'الكمية المرتجعة للصنف {line.item.name} أكبر من المتاح ({available})')"""
                    
    new_pr_cv_loop = """            current_returns = {}
            for line in instances:
                original_line = PurchaseInvoiceLine.objects.filter(
                    invoice=self.object.invoice,
                    item=line.item
                ).first()
                
                if not original_line:
                    raise ValidationError(f'الصنف {line.item.name} غير موجود في الفاتورة الأصلية')
                    
                previous_returned = PurchaseReturnLine.objects.filter(
                    purchase_return__invoice=self.object.invoice,
                    item=line.item
                ).exclude(
                    purchase_return__status='cancelled'
                ).aggregate(total=Sum('quantity'))['total'] or 0
                
                already_in_this_form = current_returns.get(line.item.id, Decimal('0'))
                available = original_line.quantity - previous_returned - already_in_this_form
                if line.quantity > available:
                    raise ValidationError(f'الكمية المرتجعة للصنف {line.item.name} أكبر من المتاح ({available})')
                    
                current_returns[line.item.id] = already_in_this_form + line.quantity
                
                # Prevent forgery
                line.unit_cost = original_line.unit_cost
                line.discount_percent = original_line.discount_percent"""
    content = content.replace(old_pr_cv_loop, new_pr_cv_loop)

    # Move template render out of atomic in PurchaseReturnCreateView
    old_pr_cv = """    def form_valid(self, form):
        context = self.get_context_data()
        lines = context['lines']
        
        with transaction.atomic():
            if not lines.is_valid():
                return self.form_invalid(form)"""
                
    new_pr_cv = """    def form_valid(self, form):
        context = self.get_context_data()
        lines = context['lines']
        
        if not lines.is_valid():
            return self.form_invalid(form)
            
        with transaction.atomic():"""
    content = content.replace(old_pr_cv, new_pr_cv)
    
    # Same for PurchaseInvoiceCreateView
    old_pi_cv = """    def form_valid(self, form):
        context = self.get_context_data()
        lines = context['lines']

        with transaction.atomic():
            if not lines.is_valid():
                return self.form_invalid(form)"""
                
    new_pi_cv = """    def form_valid(self, form):
        context = self.get_context_data()
        lines = context['lines']

        if not lines.is_valid():
            return self.form_invalid(form)

        with transaction.atomic():"""
    content = content.replace(old_pi_cv, new_pi_cv)
    
    # Add try-except to PurchaseInvoiceCreateView
    old_pi_cv_save = """            self.object = form.save(commit=False)
            self.object.created_by = self.request.user
            self.object.save()
            lines.instance = self.object
            
            for line_form in lines.forms:
                if not line_form.cleaned_data.get('DELETE'):
                    line = line_form.save(commit=False)
                    item = line.item
                    # Calculate base quantity
                    if line.unit_id == item.base_unit_id:
                        line.base_quantity = line.quantity
                    elif line.unit_id == item.purchase_unit_id:
                        line.base_quantity = line.quantity * (item.purchase_conversion_factor or 1)
                    else:
                        line.base_quantity = line.quantity * (item.conversion_factor or 1)
                    
                    line.save()
            
            lines.save()
            
            # Post directly if required by settings or logic
            PurchaseService.post_invoice(self.object, self.request.user)
            messages.success(self.request, f'تم حفظ وترحيل الفاتورة {self.object.number}')
            
        return super().form_valid(form)"""
        
    new_pi_cv_save = """            try:
                self.object = form.save(commit=False)
                self.object.created_by = self.request.user
                self.object.save()
                lines.instance = self.object
                
                for line_form in lines.forms:
                    if not line_form.cleaned_data.get('DELETE'):
                        line = line_form.save(commit=False)
                        item = line.item
                        # Calculate base quantity
                        if line.unit_id == item.base_unit_id:
                            line.base_quantity = line.quantity
                        elif line.unit_id == item.purchase_unit_id:
                            line.base_quantity = line.quantity * (item.purchase_conversion_factor or 1)
                        else:
                            line.base_quantity = line.quantity * (item.conversion_factor or 1)
                        
                        line.save()
                
                lines.save()
                
                # Post directly if required by settings or logic
                PurchaseService.post_invoice(self.object, self.request.user)
                messages.success(self.request, f'تم حفظ وترحيل الفاتورة {self.object.number}')
            except Exception as e:
                messages.error(self.request, str(e))
                return self.form_invalid(form)
            
        return super().form_valid(form)"""
    content = content.replace(old_pi_cv_save, new_pi_cv_save)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
    print("Views updated successfully.")

if __name__ == '__main__':
    main()
