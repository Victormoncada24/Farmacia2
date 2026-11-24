"""Configuración del Simulador de Farmacia Asistencial - INACAP."""
import base64
import hashlib
import os
from importlib.util import find_spec
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Carga opcional de variables desde un archivo .env (si python-dotenv está instalado)
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / '.env')
except ImportError:
    pass


def _bool(nombre, defecto=False):
    valor = os.environ.get(nombre)
    if valor is None:
        return defecto
    return valor.strip().lower() in ('1', 'true', 'yes', 'si', 'sí', 'on')


def _lista(nombre, defecto=''):
    return [x.strip() for x in os.environ.get(nombre, defecto).split(',') if x.strip()]


# --------------------------------------------------------------------------
# Seguridad básica
# --------------------------------------------------------------------------
DEBUG = _bool('DJANGO_DEBUG', True)
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'inseguro-solo-desarrollo-cambiar-en-produccion')
if not DEBUG and SECRET_KEY.startswith('inseguro'):
    raise RuntimeError('Defina DJANGO_SECRET_KEY antes de ejecutar con DJANGO_DEBUG=False.')

ALLOWED_HOSTS = _lista('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')
CSRF_TRUSTED_ORIGINS = _lista('DJANGO_CSRF_TRUSTED_ORIGINS')

# Clave para cifrar datos sensibles (teléfono, dirección, diagnóstico, etc.)
_clave_cifrado = os.environ.get('FIELD_ENCRYPTION_KEY', '').strip()
if not _clave_cifrado:
    _clave_cifrado = base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest()).decode()
FIELD_ENCRYPTION_KEY = _clave_cifrado

# --------------------------------------------------------------------------
# Aplicaciones
# --------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Proyecto
    'core',
    'accounts',
    'auditoria.apps.AuditoriaConfig',
    'inventario',
    'alertas',
    'pacientes',
    'dispensacion',
    'carros',
    'controlados',
    'reportes',
    'analitica',
    'pedidos',
]

AUTH_USER_MODEL = 'accounts.Usuario'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'auditoria.middleware.AuditoriaMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
# WhiteNoise (archivos estáticos en producción) si está instalado
if find_spec('whitenoise'):
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
# Solo si se necesita incrustar el sistema en un <iframe> de otro sitio
if _bool('DJANGO_PERMITIR_IFRAME', False):
    MIDDLEWARE.remove('django.middleware.clickjacking.XFrameOptionsMiddleware')

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.globales',
            ],
        },
    },
]

# --------------------------------------------------------------------------
# Base de datos
# --------------------------------------------------------------------------
if os.environ.get('DB_ENGINE', 'sqlite') == 'postgres':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME', 'farmacia'),
            'USER': os.environ.get('DB_USER', 'farmacia'),
            'PASSWORD': os.environ.get('DB_PASSWORD', ''),
            'HOST': os.environ.get('DB_HOST', 'localhost'),
            'PORT': os.environ.get('DB_PORT', '5432'),
            'CONN_MAX_AGE': 60,           # reutiliza conexiones (menos latencia hacia RDS)
            'CONN_HEALTH_CHECKS': True,
            # RDS: use 'require' (cifra el tráfico) o 'verify-full' con el bundle de CA de AWS
            'OPTIONS': {'sslmode': os.environ.get('DB_SSLMODE', 'prefer')},
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --------------------------------------------------------------------------
# Autenticación y contraseñas
# --------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'reportes:dashboard'
LOGOUT_REDIRECT_URL = 'accounts:login'

# Bloqueo temporal tras intentos fallidos de inicio de sesión
LOGIN_MAX_INTENTOS = 5
LOGIN_BLOQUEO_SEGUNDOS = 15 * 60

# Cierre de sesión por inactividad (30 minutos)
SESSION_COOKIE_AGE = 30 * 60
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'

# ¿Hay un proxy inverso (Nginx / balanceador de AWS) delante de la aplicación?
DETRAS_DE_PROXY = _bool('DJANGO_DETRAS_DE_PROXY', False)
SECURE_REDIRECT_EXEMPT = [r'^salud/$']   # el chequeo de salud del balanceador no se redirige a HTTPS

if not DEBUG:
    _https = _bool('DJANGO_HTTPS', True)
    SESSION_COOKIE_SECURE = _https
    CSRF_COOKIE_SECURE = _https
    SECURE_SSL_REDIRECT = _https and _bool('DJANGO_SSL_REDIRECT', True)
    SECURE_HSTS_SECONDS = 31536000 if _https else 0
    if DETRAS_DE_PROXY:
        SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# --------------------------------------------------------------------------
# Internacionalización
# --------------------------------------------------------------------------
LANGUAGE_CODE = 'es-cl'
TIME_ZONE = 'America/Santiago'
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------
# Archivos estáticos y subidos (los archivos subidos son PRIVADOS)
# --------------------------------------------------------------------------
STATIC_URL = os.environ.get('DJANGO_STATIC_URL', '/static/')
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'   # No se sirve públicamente; se entrega mediante vista autenticada
MEDIA_ROOT = BASE_DIR / 'media'

STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
if find_spec('whitenoise') and not DEBUG:
    STORAGES['staticfiles'] = {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'}

# Recetas escaneadas en Amazon S3 (bucket PRIVADO). Requiere: pip install -r requirements-aws.txt
# En EC2 use un rol IAM (no guarde claves en el servidor).
_bucket = os.environ.get('AWS_STORAGE_BUCKET_NAME', '').strip()
if _bucket:
    STORAGES['default'] = {
        'BACKEND': 'storages.backends.s3.S3Storage',
        'OPTIONS': {
            'bucket_name': _bucket,
            'region_name': os.environ.get('AWS_S3_REGION_NAME', 'sa-east-1'),
            'location': 'media',
            'default_acl': None,
            'querystring_auth': True,
            'file_overwrite': False,
        },
    }
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# Integración detrás de un subdirectorio del sitio institucional
FORCE_SCRIPT_NAME = os.environ.get('DJANGO_SCRIPT_NAME') or None

# --------------------------------------------------------------------------
# Reglas de negocio configurables
# --------------------------------------------------------------------------
ALERTA_VENCIMIENTO_DIAS = 90        # avisar lotes que vencen dentro de N días
ALERTA_VENCIMIENTO_CRITICO_DIAS = 30

# Abastecimiento inteligente (módulo analítico)
ABASTECIMIENTO_PERIODO_DIAS = 30      # ventana para medir el consumo diario
ABASTECIMIENTO_LEAD_TIME_DIAS = 15    # plazo de reposición esperado (CENABAST / Servicio de Salud)
ABASTECIMIENTO_DIAS_OBJETIVO = 60     # cobertura deseada al calcular el pedido sugerido

# Identidad de la plataforma (se puede cambiar con variables de entorno)
APP_NOMBRE = os.environ.get('APP_NOMBRE', 'Simulador de Farmacia Asistencial')
APP_SUBTITULO = os.environ.get('APP_SUBTITULO', 'Plataforma de simulación académica · INACAP')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'WARNING'},
}
