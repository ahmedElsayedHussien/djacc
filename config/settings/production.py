from django.core.exceptions import ImproperlyConfigured
from .base import *

DEBUG = False

ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=lambda v: [s.strip() for s in v.split(',')])

# Production SECRET_KEY must be set via environment variable
SECRET_KEY = config('SECRET_KEY')
if not SECRET_KEY or SECRET_KEY.startswith('django-insecure-'):
    raise ImproperlyConfigured('SECRET_KEY must be a strong, unique key set via environment variable in production')

# Production uses mysql as per plan
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='3306'),
    }
}

MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ==============================================================================
# PRODUCTION SECURITY SETTINGS (HTTPS Enforcement)
# ==============================================================================
# 1. Force SSL redirect
SECURE_SSL_REDIRECT = True

# 2. HTTP Strict Transport Security (1 year)
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# 3. Ensure CSRF cookies are only sent over HTTPS
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'

# 4. Ensure Session cookies are only sent over HTTPS
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# 5. Prevent MIME sniffing
SECURE_CONTENT_TYPE_NOSNIFF = True

# 6. Enable browser XSS filter
SECURE_BROWSER_XSS_FILTER = True

# 7. Prevent the site from being embedded in an iframe (Clickjacking protection)
X_FRAME_OPTIONS = 'DENY'

# 8. Referrer policy
SECURE_REFERRER_POLICY = 'same-origin'

# 9. Trusted origins for CSRF
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='https://' + ALLOWED_HOSTS[0], cast=lambda v: [s.strip() for s in v.split(',')]) if ALLOWED_HOSTS else []
