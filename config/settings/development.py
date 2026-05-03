from .base import *

DEBUG = True

ALLOWED_HOSTS = []

INSTALLED_APPS += [
    'django_extensions',
]

# Database for development is sqlite (as per plan)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
