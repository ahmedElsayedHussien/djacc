import os
from pathlib import Path
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-key-for-dev-only')

DEBUG = True

ALLOWED_HOSTS = []

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django.contrib.humanize',
    
    # Third party
    'rest_framework',
    'django_htmx',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'crispy_forms',
    'crispy_bootstrap5',
    
    # Local apps
    'apps.core',
    'apps.sales',
    'apps.purchases',
    'apps.inventory',
    'apps.expenses',
    'apps.treasury',
    'apps.reports',
    'apps.hr',
    'apps.assets',
    'apps.users',
]

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'ar-eg'
TIME_ZONE = 'Africa/Cairo'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# REST Framework configuration
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
}

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom settings for accounting
TAX_PAYABLE_ACCOUNT           = '2121'   # ضريبة القيمة المضافة
TAX_DEDUCTIBLE_ACCOUNT        = '2122'   # ضريبة خصم من المنبع
CHEQUES_UNDER_COLLECTION_ACCOUNT = '1151' # شيكات تحت التحصيل
CUSTOMERS_PARENT_ACCOUNT      = '1121'
SUPPLIERS_PARENT_ACCOUNT      = '2111'
CASHBOX_PARENT_ACCOUNT        = '1111'
BANK_PARENT_ACCOUNT           = '1112'
SALES_REP_RECEIVABLE_PARENT   = '1141'   # ذمم مناديب
DEFAULT_SALES_ACCOUNT         = '411'    # مبيعات بضاعة
DEFAULT_SALES_RETURN_ACCOUNT  = '413'    # مردودات المبيعات
DEFAULT_COGS_ACCOUNT          = '511'    # تكلفة البضاعة المباعة
CHEQUES_ISSUED_ACCOUNT        = '2132'   # شيكات مسحوبة
RETAINED_EARNINGS_ACCOUNT     = '34'     # أرباح مرحلة
BANK_CHARGES_ACCOUNT          = '5161'   # عمولات بنكية
INTEREST_REVENUE_ACCOUNT      = '4141'   # فوائد بنكية
CUSTODY_ACCOUNTS_PARENT       = '1142'   # عهد الموظفين
SALES_DISCOUNT_ACCOUNT        = '413'    # مردودات وخصم مبيعات (Fix #1: توافق مع شجرة الحسابات)
DEFAULT_INVENTORY_ACCOUNT     = '1131'   # مخزون البضاعة
ALLOW_NEGATIVE_STOCK          = False    # السماح بالسحب بالسالب
CASH_PARENT_ACCOUNT           = '1111'   # الأب لحسابات الصناديق

# Allauth settings
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

SITE_ID = 1
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
LOGIN_REDIRECT_URL = '/'
ACCOUNT_LOGOUT_REDIRECT_URL = '/'
ACCOUNT_LOGIN_METHODS = {'email', 'username'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'none'
