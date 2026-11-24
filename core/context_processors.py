from django.conf import settings

from .roles import PERMISOS


def globales(request):
    contexto = {'APP_NOMBRE': settings.APP_NOMBRE, 'APP_SUBTITULO': settings.APP_SUBTITULO}
    usuario = getattr(request, 'user', None)
    if usuario is not None and usuario.is_authenticated:
        contexto['perm'] = {
            clave: (usuario.is_superuser or usuario.rol in datos[1])
            for clave, datos in PERMISOS.items()
        }
        if contexto['perm']['ver_alertas']:
            from alertas.models import Alerta
            contexto['alertas_abiertas'] = Alerta.objects.filter(resuelta=False).count()
    return contexto
