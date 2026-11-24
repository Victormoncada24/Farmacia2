from django.conf import settings
from django.db import models
from django.utils import timezone


class RegistroAuditoria(models.Model):
    """Bitácora inmutable: quién hizo qué, cuándo y desde dónde."""

    class Accion(models.TextChoices):
        LOGIN = 'LOGIN', 'Inicio de sesión'
        LOGOUT = 'LOGOUT', 'Cierre de sesión'
        LOGIN_FALLIDO = 'LOGIN_FALLIDO', 'Intento de acceso fallido'
        CREAR = 'CREAR', 'Creación'
        EDITAR = 'EDITAR', 'Modificación'
        ELIMINAR = 'ELIMINAR', 'Eliminación'
        EXPORTAR = 'EXPORTAR', 'Exportación de reporte'
        ACCESO = 'ACCESO', 'Acceso a archivo'

    fecha = models.DateTimeField('Fecha y hora', default=timezone.now, db_index=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                on_delete=models.SET_NULL, related_name='+')
    usuario_texto = models.CharField('Usuario', max_length=150, blank=True)
    accion = models.CharField('Acción', max_length=15, choices=Accion.choices)
    modelo = models.CharField('Entidad', max_length=100, blank=True)
    objeto_id = models.CharField('ID', max_length=50, blank=True)
    descripcion = models.CharField('Detalle', max_length=255, blank=True)
    ip = models.GenericIPAddressField('IP', null=True, blank=True)

    class Meta:
        verbose_name = 'registro de auditoría'
        verbose_name_plural = 'registros de auditoría'
        ordering = ['-fecha', '-id']

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionError('Los registros de auditoría son inmutables.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('Los registros de auditoría no pueden eliminarse.')

    def __str__(self):
        return f'{self.fecha:%d/%m/%Y %H:%M} {self.usuario_texto} {self.accion} {self.modelo}'
