import os

from django.conf import settings
from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path

ADMIN_URL = os.environ.get('DJANGO_ADMIN_URL', 'admin/')
admin.site.site_header = f'Administración — {settings.APP_NOMBRE}'
admin.site.site_title = settings.APP_NOMBRE


def salud(request):
    """Chequeo de salud para el balanceador / monitoreo (no requiere sesión, no expone datos)."""
    try:
        connection.ensure_connection()
    except Exception:
        return JsonResponse({'estado': 'error'}, status=503)
    return JsonResponse({'estado': 'ok'})


urlpatterns = [
    path('salud/', salud),
    path(ADMIN_URL, admin.site.urls),
    path('cuentas/', include('accounts.urls')),
    path('inventario/', include('inventario.urls')),
    path('pedidos/', include('pedidos.urls')),
    path('pacientes/', include('pacientes.urls')),
    path('dispensacion/', include('dispensacion.urls')),
    path('carros/', include('carros.urls')),
    path('controlados/', include('controlados.urls')),
    path('alertas/', include('alertas.urls')),
    path('analitica/', include('analitica.urls')),
    path('auditoria/', include('auditoria.urls')),
    path('', include('reportes.urls')),
]
