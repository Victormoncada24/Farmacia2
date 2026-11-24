"""Auditoría automática de altas, cambios y bajas de las entidades sensibles + accesos."""
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import RegistroAuditoria
from .services import registrar

AUDITADOS = {
    'accounts.usuario', 'inventario.categoria', 'inventario.producto', 'inventario.lote',
    'pacientes.paciente', 'pacientes.programa', 'pacientes.inscripcionprograma', 'pacientes.cuotaprograma',
    'dispensacion.receta', 'dispensacion.dispensacion',
    'carros.carroclinico', 'carros.carroitem', 'carros.reposicioncarro', 'carros.solicitudreposicion',
    'carros.consumocarro',
    'controlados.movimientocontrolado', 'controlados.conteofisico',
    'pedidos.proveedor', 'pedidos.pedido', 'pedidos.recepcion',
}


@receiver(post_save)
def auditar_guardado(sender, instance, created, raw=False, update_fields=None, **kwargs):
    if raw or sender._meta.label_lower not in AUDITADOS:
        return
    if update_fields and set(update_fields) == {'last_login'}:
        return
    registrar(
        RegistroAuditoria.Accion.CREAR if created else RegistroAuditoria.Accion.EDITAR,
        modelo=sender._meta.verbose_name.capitalize(), objeto_id=instance.pk, descripcion=str(instance),
    )


@receiver(post_delete)
def auditar_eliminacion(sender, instance, **kwargs):
    if sender._meta.label_lower not in AUDITADOS:
        return
    registrar(
        RegistroAuditoria.Accion.ELIMINAR,
        modelo=sender._meta.verbose_name.capitalize(), objeto_id=instance.pk, descripcion=str(instance),
    )


@receiver(user_logged_in)
def auditar_login(sender, request, user, **kwargs):
    registrar(RegistroAuditoria.Accion.LOGIN, usuario=user, request=request, descripcion='Inicio de sesión')


@receiver(user_logged_out)
def auditar_logout(sender, request, user, **kwargs):
    if user is not None:
        registrar(RegistroAuditoria.Accion.LOGOUT, usuario=user, request=request, descripcion='Cierre de sesión')


@receiver(user_login_failed)
def auditar_login_fallido(sender, credentials, request=None, **kwargs):
    registrar(
        RegistroAuditoria.Accion.LOGIN_FALLIDO, request=request,
        usuario_texto=str(credentials.get('username', ''))[:150],
        descripcion='Credenciales inválidas',
    )
