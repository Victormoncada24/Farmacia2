from django.contrib.auth.models import AbstractUser
from django.db import models

from core import roles
from core.fields import RutField


class Usuario(AbstractUser):
    """Usuario del sistema con RUT, teléfono y rol institucional (RF-01 / RF-02)."""
    rut = RutField('RUT', unique=True)
    telefono = models.CharField('Teléfono', max_length=20, blank=True)
    rol = models.CharField('Rol', max_length=10, choices=roles.CHOICES, default=roles.TECNICO)

    REQUIRED_FIELDS = ['rut', 'email']

    class Meta:
        verbose_name = 'usuario'
        verbose_name_plural = 'usuarios'
        ordering = ['first_name', 'last_name', 'username']

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.rol = roles.ADMIN
        super().save(*args, **kwargs)

    def puede(self, clave):
        """¿El rol del usuario posee el permiso `clave` (ver core.roles.PERMISOS)?"""
        return bool(self.is_active and (self.is_superuser or self.rol in roles.roles_de(clave)))

    @property
    def nombre_completo(self):
        return self.get_full_name() or self.username

    def __str__(self):
        return f'{self.nombre_completo} ({self.get_rol_display()})'
