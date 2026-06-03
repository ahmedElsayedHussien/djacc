import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')
django.setup()

from django.contrib.auth.models import User
admin = User.objects.get(username='admin')
admin.set_password('admin123')
admin.save()
print("Admin password updated successfully!")
