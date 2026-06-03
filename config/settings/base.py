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
    'apps.e_invoice',
    'apps.pos',
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
    'apps.core.middleware.BruteForceProtectionMiddleware', # درع الحماية المخصص من محاولات الاختراق
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
                'apps.core.context_processors.notifications_processor',
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
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
}

# SimpleJWT configuration
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'AUTH_HEADER_TYPES': ('Bearer', 'JWT'),
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
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
MOBILE_WALLET_PARENT_ACCOUNT  = '1115'   # المحافظ الإلكترونية
SALES_REP_RECEIVABLE_PARENT   = '1141'   # ذمم مناديب
SALES_REP_INVENTORY_PARENT    = '1134'   # بضاعة المندوبين
DEFAULT_SALES_ACCOUNT         = '411'    # مبيعات بضاعة
DEFAULT_SALES_RETURN_ACCOUNT  = '413'    # مردودات المبيعات
DEFAULT_COGS_ACCOUNT          = '511'    # تكلفة البضاعة المباعة
CHEQUES_ISSUED_ACCOUNT        = '2141'   # شيكات مسحوبة
RETAINED_EARNINGS_ACCOUNT     = '34'     # أرباح مرحلة
OPENING_BALANCES_ACCOUNT      = '35'     # الأرصدة الافتتاحية
BANK_CHARGES_ACCOUNT          = '531'    # عمولات بنكية
INTEREST_REVENUE_ACCOUNT      = '421'    # فوائد بنكية
CUSTODY_ACCOUNTS_PARENT       = '1142'   # عهد الموظفين
SALES_DISCOUNT_ACCOUNT        = '414'    # خصم مبيعات ممنوح
DEFAULT_INVENTORY_ACCOUNT     = '1131'   # مخزون البضاعة
ALLOW_NEGATIVE_STOCK          = False    # السماح بالسحب بالسالب
PENALTY_INCOME_ACCOUNT        = '42'     # إيرادات غرامات (شيكات مرتجعة)
CASH_PARENT_ACCOUNT           = '1111'   # الأب لحسابات الصناديق
CASH_SHORTAGE_ACCOUNT         = '544'    # مصروف عجز خزينة (نقدية)
CASH_EXCESS_ACCOUNT           = '425'    # إيراد زيادة خزينة (نقدية)

# Inventory Voucher Offset Accounts
INVENTORY_OPENING_BALANCE_ACCOUNT = '35'
INVENTORY_ADJUSTMENT_IN_ACCOUNT  = '424'
INVENTORY_ADJUSTMENT_OUT_ACCOUNT = '542'
INVENTORY_INTERNAL_CONSUMPTION_ACCOUNT = '524'
INVENTORY_GIFTS_ACCOUNT = '525'  # مصروف الهدايا والعينات

# Payroll & HR Accounts
SALARY_ACCOUNT                = '5210'   # الرواتب والأجور الأساسية
ALLOWANCES_ACCOUNT            = '5213'   # مصروف بدلات وإضافات أخرى
SALARIES_PAYABLE_ACCOUNT      = '2132'   # رواتب وأجور مستحقة
INSURANCE_PAYABLE_ACCOUNT     = '2133'   # تأمينات اجتماعية مستحقة
LOANS_RECEIVABLE_ACCOUNT      = '1143'   # سلف الموظفين والقروض
OTHER_DEDUCTIONS_ACCOUNT      = '2126'   # استقطاعات أخرى من الموظفين
INCOME_TAX_PAYABLE_ACCOUNT    = '2125'   # مصلحة الضرائب - كسب عمل
INSURANCE_EXPENSE_ACCOUNT     = '5214'   # حصة المنشأة في التأمينات الاجتماعية
EOS_EXPENSE_ACCOUNT           = '5215'   # مصروف تعويضات ومكافآت نهاية الخدمة

# Fixed Assets Accounts
LOSS_ON_DISPOSAL_ACCOUNT      = '5261'   # خسائر استبعاد أصول ثابتة
GAIN_ON_DISPOSAL_ACCOUNT      = '4210'   # أرباح رأسمالية (بيع أصول)
FIXED_ASSETS_PARENT           = '12'     # الأصول الثابتة
ACCUMULATED_DEPRECIATION_PARENT = '129'  # مجمع إهلاك الأصول

# Treasury Accounts
CASH_IN_TRANSIT_ACCOUNT       = '1114'   # نقدية بالطريق

# Allauth settings
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

SITE_ID = 1
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
LOGIN_REDIRECT_URL = 'core:login-redirect'
ACCOUNT_LOGOUT_REDIRECT_URL = '/'
ACCOUNT_LOGIN_METHODS = {'email', 'username'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'none'

# ==============================================================================
# SECURITY & SESSION SETTINGS (Added for ERP Security)
# ==============================================================================
# 1. إنهاء الجلسة فور إغلاق المستخدم للمتصفح بالكامل
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# 2. مدة صلاحية الجلسة في حالة الخمول التام: 60 دقيقة (3600 ثانية)
SESSION_COOKIE_AGE = 3600

# 3. تجديد الـ 60 دقيقة مع كل نقرة أو تفاعل للمستخدم لكي لا يخرج أثناء العمل
SESSION_SAVE_EVERY_REQUEST = True
