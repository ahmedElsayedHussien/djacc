import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.core.models import Account

acc_524 = Account.objects.filter(code='524').first()
if acc_524:
    acc_524.name = 'استهلاك داخلي'
    acc_524.is_leaf = False
    acc_524.save()

# But wait, we want the internal consumption to be selectable. If 524 is parent, we must create 5241 as leaf.
# Wait, no, earlier we saw 524 had children. We should just add 5241 to the whitelist instead if we want it.
# Actually, the user just wants "مصروفات الهدايا".

acc_525 = Account.objects.filter(code='525').first()
if acc_525:
    acc_525.name = 'مصروف الهدايا والعينات'
    acc_525.is_leaf = True
    acc_525.save()

print("Names fixed successfully.")
