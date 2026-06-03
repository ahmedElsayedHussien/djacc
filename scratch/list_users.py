import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from django.contrib.auth.models import User

users = User.objects.all()
for u in users:
    print(f"Username: {u.username}, IsSuperuser: {u.is_superuser}, IsStaff: {u.is_staff}, Groups: {[g.name for g in u.groups.all()]}")
