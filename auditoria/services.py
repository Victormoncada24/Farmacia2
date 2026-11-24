from core.utils import obtener_ip

from .middleware import request_actual
from .models import RegistroAuditoria


def registrar(accion, *, modelo='', objeto_id='', descripcion='', usuario=None, request=None, usuario_texto=''):
    """Crea un registro de auditoría. Toma usuario e IP del request en curso si no se indican."""
    request = request or request_actual()
    if usuario is None and request is not None:
        candidato = getattr(request, 'user', None)
        if candidato is not None and candidato.is_authenticated:
            usuario = candidato
    RegistroAuditoria.objects.create(
        usuario=usuario,
        usuario_texto=usuario_texto or (usuario.get_username() if usuario else ''),
        accion=accion,
        modelo=str(modelo)[:100],
        objeto_id=str(objeto_id)[:50],
        descripcion=str(descripcion)[:255],
        ip=obtener_ip(request),
    )
