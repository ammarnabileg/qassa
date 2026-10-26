"""Django settings. Every secret and environment-specific value comes from the environment."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def env_bool(name, default=False):
    return str(os.environ.get(name, default)).lower() in {"1", "true", "yes", "on"}


ENVIRONMENT = env("QASSA_ENV", "development")  # development | test | staging | production
DEBUG = env_bool("DJANGO_DEBUG", ENVIRONMENT == "development")
SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-insecure-key" if ENVIRONMENT in {"development", "test"} else None,
                 required=ENVIRONMENT not in {"development", "test"})
# Static hosts (platform back-office). Company PWA hosts live in platform.TenantDomain and are checked by
# apps.platform.middleware.HostMiddleware, which replaces Django's static ALLOWED_HOSTS check.
PLATFORM_HOSTS = [h for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if h]
ALLOWED_HOSTS = ["*"]
TENANT_BASE_DOMAIN = env("QASSA_TENANT_BASE_DOMAIN", "localhost")  # company subdomains: <slug>.<base>
CSRF_TRUSTED_ORIGINS = [o for o in env("DJANGO_CSRF_TRUSTED_ORIGINS", "http://localhost:5173").split(",") if o]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "drf_spectacular",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "apps.core",
    "apps.identity",
    "apps.tenancy",
    "apps.audit",
    "apps.accounting",
    "apps.catalog",
    "apps.staff",
    "apps.customers",
    "apps.booking",
    "apps.pos",
    "apps.platform",
]

MIDDLEWARE = [
    "apps.platform.middleware.HostMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.tenancy.middleware.TenantContextResetMiddleware",
]

ROOT_URLCONF = "qassa.urls"
WSGI_APPLICATION = "qassa.wsgi.application"
AUTH_USER_MODEL = "identity.User"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "qassa"),
        "USER": env("POSTGRES_USER", "qassa"),
        "PASSWORD": env("POSTGRES_PASSWORD", "qassa_dev" if ENVIRONMENT in {"development", "test"} else None,
                        required=ENVIRONMENT not in {"development", "test"}),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "ATOMIC_REQUESTS": False,  # transactions are explicit in services
        "CONN_MAX_AGE": 60,
    }
}

CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache",
                      "LOCATION": env("REDIS_URL", "redis://localhost:6379/1")}}
if ENVIRONMENT == "test":
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
if ENVIRONMENT == "test":
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # speed only in tests
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_AGE = 60 * 60 * 12
SECURE_CONTENT_TYPE_NOSNIFF = True
if env_bool("DJANGO_BEHIND_TLS_PROXY", False):  # TLS terminated by the platform proxy (Coolify/Traefik)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
X_FRAME_OPTIONS = "DENY"

LANGUAGE_CODE = "ar"
LANGUAGES = [("ar", "العربية"), ("en", "English")]
TIME_ZONE = "Asia/Kuwait"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.CursorPagination",
    "PAGE_SIZE": 50,
    "EXCEPTION_HANDLER": "apps.core.errors.exception_handler",
    "COERCE_DECIMAL_TO_STRING": True,
    "DEFAULT_THROTTLE_RATES": {"login": env("THROTTLE_LOGIN", "10/min"), "mfa": "10/min", "public": env("THROTTLE_PUBLIC", "60/min")},
}

SPECTACULAR_SETTINGS = {
    "ENUM_NAME_OVERRIDES": {"TenantStatusEnum": "apps.tenancy.models.Tenant.Status",
                            "BusinessTypeEnum": "apps.tenancy.models.BusinessType",
                            "AppointmentStatusEnum": "apps.booking.models.Appointment.Status",
                            "CashSessionStatusEnum": "apps.pos.models.CashSession.Status"},
    "TITLE": "Qassa POS API",
    "VERSION": "0.1.0",
    "DESCRIPTION": "Multi-tenant salon POS & accounting API. Tenant-scoped endpoints require the X-Tenant header.",
}

CELERY_BROKER_URL = env("REDIS_URL", "redis://localhost:6379/0")
CELERY_TASK_ALWAYS_EAGER = ENVIRONMENT == "test"

QASSA = {
    "BUSINESS_DAY_START_HOUR": 4,  # shifts crossing midnight belong to the previous business day
    "MFA_REQUIRED_ROLES": ["owner", "finance_manager", "accountant"],
    "WHATSAPP_ADAPTER": env("QASSA_WHATSAPP_ADAPTER", "console" if ENVIRONMENT in {"development", "test"} else "disabled"),
    "WHATSAPP_URL": env("QASSA_WHATSAPP_URL", ""),
    "WHATSAPP_TOKEN": env("QASSA_WHATSAPP_TOKEN", ""),
    "WHATSAPP_INSTANCE": env("QASSA_WHATSAPP_INSTANCE", ""),
    # Show the login code in the API response — ONLY for testing environments without a WhatsApp channel.
    "OTP_ECHO": env_bool("QASSA_OTP_ECHO", ENVIRONMENT in {"development", "test"}) and ENVIRONMENT != "production",
    "OTP_TTL_SECONDS": 300,
    "CUSTOMER_TOKEN_DAYS": 30,
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}


def _version():
    """QASSA_VERSION is stamped by the build; otherwise computed from VERSION + git (debug builds)."""
    if os.environ.get("QASSA_VERSION"):
        return os.environ["QASSA_VERSION"], os.environ.get("QASSA_CHANNEL", "release")
    import importlib.util
    spec = importlib.util.spec_from_file_location("qassa_version", BASE_DIR.parent / "scripts" / "version.py")
    if spec is None or not (BASE_DIR.parent / "scripts" / "version.py").exists():
        return "unknown", "debug"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.compute()


QASSA_VERSION, QASSA_CHANNEL = _version()
