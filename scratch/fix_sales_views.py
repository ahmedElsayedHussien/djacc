import re

with open('apps/sales/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_logic = """            if lines.is_valid():
                self.object = form.save()
                lines.instance = self.object
                lines.save()"""

new_logic = """            if lines.is_valid():
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
                    obj.delete()"""

content = content.replace(old_logic, new_logic)

# Remove the duplicated base quantity calculation that was in the loop further down
old_calc_loop = """                for line in self.object.lines.all():
                    # ✅ Fix: Calculate base quantity on update
                    if line.unit:
                        line.base_quantity = line.item.convert_to_base(line.quantity, line.unit)
                    else:
                        line.base_quantity = line.quantity

                    gross_line = Decimal(str(line.quantity * line.unit_price))"""

new_calc_loop = """                for line in self.object.lines.all():
                    gross_line = Decimal(str(line.quantity * line.unit_price))"""

content = content.replace(old_calc_loop, new_calc_loop)

with open('apps/sales/views.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done views!")
