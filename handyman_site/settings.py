# handyman_site/settings.py
from pathlib import Path
import os
import unicodedata
from django.utils.translation import gettext_lazy as _
from dotenv import load_dotenv

# === БАЗА ===
BASE_DIR = Path(__file__).resolve().parent.parent
# Разрешаем .env переопределять уже существующие переменные окружения
load_dotenv(BASE_DIR / ".env", override=True)

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'dev-secret-key-change-me')
DEBUG = os.environ.get('DEBUG', 'true').strip().lower() == 'true'
ALLOWED_HOSTS = [h.strip() for h in os.environ.get('ALLOWED_HOSTS', '*').split(',') if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()]

# === ПРИЛОЖЕНИЯ ===
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'crispy_forms',
    'phonenumber_field',
    'core.apps.CoreConfig',
]

# === MIDDLEWARE ===
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'handyman_site.urls'

# === ШАБЛОНЫ ===
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'templates',
            BASE_DIR / 'core' / 'templates',
        ],
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

WSGI_APPLICATION = 'handyman_site.wsgi.application'

# === БАЗА ДАННЫХ ===
_db_engine = os.environ.get('DB_ENGINE', 'django.db.backends.sqlite3')
if _db_engine == 'django.db.backends.sqlite3':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.environ.get('DB_NAME', BASE_DIR / 'db.sqlite3'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': _db_engine,
            'NAME': os.environ.get('DB_NAME', ''),
            'USER': os.environ.get('DB_USER', ''),
            'PASSWORD': os.environ.get('DB_PASSWORD', ''),
            'HOST': os.environ.get('DB_HOST', 'localhost'),
            'PORT': os.environ.get('DB_PORT', ''),
            'OPTIONS': {},
        }
    }

# === ПАРОЛИ ===
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# === ЛОКАЛИ ===
LANGUAGE_CODE = 'de'
TIME_ZONE = 'Europe/Berlin'
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ('de', _('Deutsch')),
    ('en', _('Englisch')),
]
LOCALE_PATHS = [BASE_DIR / 'locale']

# === STATIC / MEDIA ===
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# === AUTH BACKENDS ===
AUTHENTICATION_BACKENDS = [
    'core.backends.CaseInsensitiveModelBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# === ДАННЫЕ БАНКА (для PDF/счёта) ===
BANK_ACCOUNT_HOLDER = os.environ.get("BANK_ACCOUNT_HOLDER", "Aleksandr Sakilev")
BANK_NAME = os.environ.get("BANK_NAME", "DKB")
BANK_IBAN = os.environ.get("BANK_IBAN", "DE12 3456 7890 1234 5678 90")
BANK_BIC = os.environ.get("BANK_BIC", "BYLADEM1001")

# === LOGIN/LOGOUT ===
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'home'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# === БИЗНЕС-ПАРАМЕТРЫ ===
HOURLY_RATE_EUR = float(os.environ.get('HOURLY_RATE_EUR', '18'))
TAX_RATE_PERCENT = float(os.environ.get('TAX_RATE_PERCENT', '19'))
TAX_MODE = os.environ.get('TAX_MODE', 'add').lower()  # 'add' | 'deduct'

MIN_BILLABLE_HOURS = float(os.environ.get('MIN_BILLABLE_HOURS', '1.0'))
BILLING_ROUNDING_MINUTES = int(os.environ.get('BILLING_ROUNDING_MINUTES', '30'))
BILL_TRAVEL_TIME = os.environ.get('BILL_TRAVEL_TIME', 'true').strip().lower() == 'true'
ANFAHRT_PAUSCHALE_EUR = float(os.environ.get('ANFAHRT_PAUSCHALE_EUR', '10'))
PER_KM_EUR = float(os.environ.get('PER_KM_EUR', '0.5'))
INCLUDED_KM = float(os.environ.get('INCLUDED_KM', '5'))

# === ПОЧТА (SMTP) ===
# Поддержим «очистку» логина и пароля от невидимых не-ASCII символов
def _s(v: str) -> str:
    return (v or "").strip()

def _clean_ascii(s: str) -> str:
    s = s or ""
    # удаляем управляющие символы и любые > ASCII
    s = "".join(ch for ch in s if ord(ch) < 128 and not unicodedata.category(ch).startswith("C"))
    return s.strip()

EMAIL_BACKEND = _s(os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend'))

EMAIL_HOST = _s(os.getenv('EMAIL_HOST', 'smtp.gmail.com'))
EMAIL_PORT = int(_s(os.getenv('EMAIL_PORT', '587')) or 587)

# В .env можно переключаться между режимами:
#  - STARTTLS: EMAIL_USE_TLS=true, EMAIL_USE_SSL=false, EMAIL_PORT=587
#  - SSL:      EMAIL_USE_SSL=true, EMAIL_USE_TLS=false, EMAIL_PORT=465
EMAIL_USE_TLS = _s(os.getenv('EMAIL_USE_TLS', 'true')).lower() in ('1', 'true', 'yes')
EMAIL_USE_SSL = _s(os.getenv('EMAIL_USE_SSL', 'false')).lower() in ('1', 'true', 'yes')

# Чистим от невидимых юникод-символов, чтобы не ловить UnicodeEncodeError в smtplib
EMAIL_HOST_USER = _clean_ascii(os.getenv('EMAIL_HOST_USER', ''))
EMAIL_HOST_PASSWORD = _clean_ascii(os.getenv('EMAIL_HOST_PASSWORD', ''))

DEFAULT_FROM_EMAIL = _s(os.getenv('DEFAULT_FROM_EMAIL', 'no-reply@example.com'))
SERVER_EMAIL = _s(os.getenv('SERVER_EMAIL', DEFAULT_FROM_EMAIL))
OWNER_NOTIFICATION_EMAIL = _s(os.getenv('OWNER_NOTIFICATION_EMAIL', ''))

# === УВЕДОМЛЕНИЯ ===
NOTIFY_TELEGRAM = os.environ.get('NOTIFY_TELEGRAM', 'false').strip().lower() == 'true'
NOTIFY_WHATSAPP = os.environ.get('NOTIFY_WHATSAPP', 'false').strip().lower() == 'true'

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

WHATSAPP_TOKEN = os.environ.get('WHATSAPP_TOKEN', '')
WHATSAPP_PHONE_ID = os.environ.get('WHATSAPP_PHONE_ID', '')
WHATSAPP_TO = os.environ.get('WHATSAPP_TO', '')

# Какая модель шлёт уведомления
APPLICATION_MODEL = os.environ.get('APPLICATION_MODEL', 'core.Booking')

# === CRISPY / PHONE NUMBER ===
CRISPY_TEMPLATE_PACK = os.environ.get('CRISPY_TEMPLATE_PACK', 'bootstrap4')
PHONENUMBER_DEFAULT_REGION = os.environ.get('PHONENUMBER_DEFAULT_REGION', 'DE')

# === ЛОГИ (в консоль) ===
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "core": {"handlers": ["console"], "level": "INFO"},  # можно "DEBUG" на время
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
