from pathlib import Path
from decouple import config, Csv
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='clave-local-insegura-solo-para-desarrollo')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

LOCAL_APPS = [
    'apps.usuarios',
    'apps.clientes',
    'apps.inventario',
    'apps.ventas',
    'apps.deudores',
    'apps.reportes',
    'apps.proveedores',
    'apps.facturacion',
    'apps.configuracion',
]

INSTALLED_APPS = DJANGO_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

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
                'apps.configuracion.context_processors.config_general',
                'apps.configuracion.context_processors.aviso_pago_proveedor',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

DATABASES = {
    'default': dj_database_url.config(
        default=config('DATABASE_URL', default='sqlite:///db.sqlite3'),
        conn_max_age=600,
    )
}

AUTH_USER_MODEL = 'usuarios.Usuario'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/login/'

# Cierre de sesión por inactividad (30 min). SESSION_SAVE_EVERY_REQUEST hace
# que el contador sea "deslizante": cada request del usuario lo reinicia.
SESSION_INACTIVITY_SECONDS = config('SESSION_INACTIVITY_SECONDS', default=1800, cast=int)
SESSION_COOKIE_AGE = SESSION_INACTIVITY_SECONDS
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# ─────────────────────────────────────────────────────────────
# CACHE — Redis si está configurado, LocMem como fallback (dev)
# Con Redis levantado lo usamos también como backend de sesiones
# (cached_db) para evitar que CADA request escriba en django_session en
# RDS. Eso era un cuello de botella sobre la BD pequeña de t4g.micro,
# especialmente porque SESSION_SAVE_EVERY_REQUEST=True. Ahora los reads
# van a Redis y los writes son perezosos.
# ─────────────────────────────────────────────────────────────
_REDIS_URL = config('REDIS_URL', default='')
if _REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND':  'django.core.cache.backends.redis.RedisCache',
            'LOCATION': _REDIS_URL,
            'TIMEOUT':  300,
        }
    }
    # cached_db: lee de Redis (rápido) y respalda en BD (durable). Si
    # Redis se cae, las sesiones siguen funcionando vía RDS sin perder
    # logins existentes.
    SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'
else:
    # Dev local sin Redis: cache en memoria del proceso.
    CACHES = {
        'default': {
            'BACKEND':  'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'sistema-tienda-dev',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 8},
    },
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
    {'NAME': 'apps.usuarios.password_validators.ComplexityValidator'},
]

LANGUAGE_CODE = 'es-ec'
TIME_ZONE = 'America/Guayaquil'
USE_I18N = True
USE_TZ = True

# ─────────────────────────────────────────────────────────────
# AVISO DE PAGO AL PROVEEDOR DEL SISTEMA (visible solo al dueño)
# Configurable 100% por variables de entorno en Railway.
# Cuando el cliente te paga, actualizas DEV_PAGO_FECHA a la próxima fecha.
# ─────────────────────────────────────────────────────────────
DEV_PAGO_FECHA              = config('DEV_PAGO_FECHA',              default='')   # 'YYYY-MM-DD'
DEV_PAGO_MONTO              = config('DEV_PAGO_MONTO',              default='')   # '15.00'
DEV_PAGO_MONEDA             = config('DEV_PAGO_MONEDA',             default='USD')
DEV_PAGO_CONCEPTO           = config('DEV_PAGO_CONCEPTO',           default='Hosting + soporte mensual del sistema')
DEV_PAGO_CONTACTO_NOMBRE    = config('DEV_PAGO_CONTACTO_NOMBRE',    default='')
DEV_PAGO_CONTACTO_TELEFONO  = config('DEV_PAGO_CONTACTO_TELEFONO',  default='')
DEV_PAGO_CONTACTO_EMAIL     = config('DEV_PAGO_CONTACTO_EMAIL',     default='')
DEV_PAGO_INSTRUCCIONES      = config('DEV_PAGO_INSTRUCCIONES',      default='')   # ej. 'Banco Pichincha · Ahorros · 22XXXXXXX · CI 015XXXXXXX'

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Media / fotos de productos. Django 5.1+ usa STORAGES en lugar de
# DEFAULT_FILE_STORAGE/STATICFILES_STORAGE — las settings viejas se ignoran.
_default_storage = 'django.core.files.storage.FileSystemStorage'
_CLOUDINARY_URL = config('CLOUDINARY_URL', default='')
if _CLOUDINARY_URL:
    import cloudinary
    cloudinary.config(cloudinary_url=_CLOUDINARY_URL)
    INSTALLED_APPS += ['cloudinary_storage', 'cloudinary']
    _default_storage = 'cloudinary_storage.storage.MediaCloudinaryStorage'

STORAGES = {
    'default':     {'BACKEND': _default_storage},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─────────────────────────────────────────────────────────────
# Seguridad en producción (detrás del proxy de Railway)
# Solo se aplican cuando DEBUG=False para no romper desarrollo local.
# ─────────────────────────────────────────────────────────────
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='https://*.up.railway.app,https://*.railway.app',
    cast=Csv(),
)

if not DEBUG:
    # BEHIND_HTTPS=True (default) cuando el sitio se sirve por HTTPS detrás
    # de un proxy/CDN (Railway, nginx+Certbot, CloudFront, etc.). Si todavía
    # no hay SSL configurado (despliegue inicial en EC2 solo por IP HTTP),
    # poner BEHIND_HTTPS=False en el .env para evitar redirects rotos y
    # cookies que no se setean.
    BEHIND_HTTPS = config('BEHIND_HTTPS', default=True, cast=bool)
    if BEHIND_HTTPS:
        SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
        SECURE_SSL_REDIRECT = True
        SESSION_COOKIE_SECURE = True
        CSRF_COOKIE_SECURE = True
        SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30  # 30 días
        SECURE_HSTS_INCLUDE_SUBDOMAINS = True
        SECURE_HSTS_PRELOAD = True
    # Estos no dependen de HTTPS, siempre activos en producción
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'same-origin'
    X_FRAME_OPTIONS = 'DENY'

# ─────────────────────────────────────────────────────────────
# EMAIL — envío de notificaciones (facturas SRI al cliente, etc.)
# Configurable por env vars para soportar varios proveedores:
#   - Resend:  EMAIL_HOST=smtp.resend.com, USER='resend', PASSWORD=<api_key>
#   - Gmail:   EMAIL_HOST=smtp.gmail.com,  USER=<email>,  PASSWORD=<app_password>
#   - Otros SMTP: ajustar host/port/TLS
# Si no se configura EMAIL_HOST_PASSWORD, el backend cae a 'console' (los
# emails se imprimen en consola en vez de enviarse — util en desarrollo).
# ─────────────────────────────────────────────────────────────
_EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_BACKEND = config(
    'EMAIL_BACKEND',
    default=(
        'django.core.mail.backends.smtp.EmailBackend'
        if _EMAIL_HOST_PASSWORD
        else 'django.core.mail.backends.console.EmailBackend'
    ),
)
EMAIL_HOST          = config('EMAIL_HOST',          default='smtp.resend.com')
EMAIL_PORT          = config('EMAIL_PORT',          default=587, cast=int)
EMAIL_USE_TLS       = config('EMAIL_USE_TLS',       default=True, cast=bool)
EMAIL_USE_SSL       = config('EMAIL_USE_SSL',       default=False, cast=bool)
EMAIL_HOST_USER     = config('EMAIL_HOST_USER',     default='resend')
EMAIL_HOST_PASSWORD = _EMAIL_HOST_PASSWORD
EMAIL_TIMEOUT       = config('EMAIL_TIMEOUT',       default=20, cast=int)
DEFAULT_FROM_EMAIL  = config(
    'DEFAULT_FROM_EMAIL',
    default='Sistema Tienda <onboarding@resend.dev>',
)
