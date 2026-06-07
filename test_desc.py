import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.core.models import Account

p1 = Account.objects.get(code='1111')
p2 = Account.objects.get(code='1112')

def get_descendants(p):
    descs = [p]
    for c in p.children.all():
        descs.extend(get_descendants(c))
    return descs

descs = get_descendants(p1) + get_descendants(p2)
leaves = [d for d in descs if d.is_leaf]
print(f'Total leaves via descendants: {len(leaves)}')
print('Codes:', [d.code for d in leaves])
