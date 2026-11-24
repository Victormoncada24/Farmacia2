from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.fields import EncryptedCharField, EncryptedTextField
from core.utils import normalizar_rut, validar_rut


class Paciente(models.Model):
    class TipoDocumento(models.TextChoices):
        RUT = 'RUT', 'RUT'
        DNI = 'DNI', 'DNI / Pasaporte'

    class Prevision(models.TextChoices):
        FONASA_A = 'FONASA_A', 'FONASA tramo A'
        FONASA_B = 'FONASA_B', 'FONASA tramo B'
        FONASA_C = 'FONASA_C', 'FONASA tramo C'
        FONASA_D = 'FONASA_D', 'FONASA tramo D'
        ISAPRE = 'ISAPRE', 'Isapre'
        FFAA = 'FFAA', 'Capredena / Dipreca'
        SIN = 'SIN', 'Sin previsión'

    PREVISION_PUBLICA = ('FONASA_A', 'FONASA_B', 'FONASA_C', 'FONASA_D')

    tipo_documento = models.CharField('Tipo de documento', max_length=3, choices=TipoDocumento.choices,
                                      default=TipoDocumento.RUT)
    documento = models.CharField('RUT / DNI', max_length=20, unique=True)
    nombres = models.CharField('Nombres', max_length=100)
    apellidos = models.CharField('Apellidos', max_length=100)
    fecha_nacimiento = models.DateField('Fecha de nacimiento', null=True, blank=True)
    prevision = models.CharField('Previsión', max_length=10, choices=Prevision.choices, default=Prevision.FONASA_A)
    # Datos sensibles: se almacenan cifrados
    telefono = EncryptedCharField('Teléfono', blank=True)
    direccion = EncryptedCharField('Dirección', blank=True)
    email = EncryptedCharField('Correo electrónico', blank=True)
    activo = models.BooleanField('Activo', default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'paciente'
        verbose_name_plural = 'pacientes'
        ordering = ['apellidos', 'nombres']

    def clean(self):
        super().clean()
        if self.tipo_documento == self.TipoDocumento.RUT:
            try:
                validar_rut(self.documento)
            except ValidationError as error:
                raise ValidationError({'documento': error.messages})
            self.documento = normalizar_rut(self.documento)
        else:
            self.documento = (self.documento or '').strip().upper()

    @property
    def nombre_completo(self):
        return f'{self.nombres} {self.apellidos}'

    @property
    def edad(self):
        if not self.fecha_nacimiento:
            return None
        hoy = timezone.localdate()
        n = self.fecha_nacimiento
        return hoy.year - n.year - ((hoy.month, hoy.day) < (n.month, n.day))

    @property
    def tiene_cobertura_publica(self):
        return self.prevision in self.PREVISION_PUBLICA

    def __str__(self):
        return f'{self.nombre_completo} ({self.documento})'


class Programa(models.Model):
    class Tipo(models.TextChoices):
        GES = 'GES', 'GES / AUGE'
        CRONICO = 'CRONICO', 'Paciente crónico'

    nombre = models.CharField('Nombre', max_length=120, unique=True)
    tipo = models.CharField('Tipo', max_length=8, choices=Tipo.choices)
    descripcion = models.CharField('Descripción', max_length=250, blank=True)
    activo = models.BooleanField('Activo', default=True)

    class Meta:
        verbose_name = 'programa de salud'
        verbose_name_plural = 'programas de salud'
        ordering = ['nombre']

    def __str__(self):
        return f'{self.nombre} [{self.get_tipo_display()}]'


class InscripcionPrograma(models.Model):
    paciente = models.ForeignKey(Paciente, on_delete=models.PROTECT, related_name='inscripciones')
    programa = models.ForeignKey(Programa, on_delete=models.PROTECT, related_name='inscripciones')
    fecha_inicio = models.DateField('Fecha de inicio', default=timezone.localdate)
    fecha_termino = models.DateField('Fecha de término', null=True, blank=True)
    diagnostico = EncryptedTextField('Diagnóstico / observaciones clínicas', blank=True)
    activo = models.BooleanField('Vigente', default=True)

    class Meta:
        verbose_name = 'inscripción a programa'
        verbose_name_plural = 'inscripciones a programas'
        ordering = ['-activo', '-fecha_inicio']

    def __str__(self):
        return f'{self.paciente.nombre_completo} — {self.programa.nombre}'


class CuotaPrograma(models.Model):
    """Cantidad mensual de un producto cubierta gratuitamente por la inscripción."""
    inscripcion = models.ForeignKey(InscripcionPrograma, on_delete=models.CASCADE, related_name='cuotas')
    producto = models.ForeignKey('inventario.Producto', on_delete=models.PROTECT, related_name='cuotas')
    cantidad_mensual = models.PositiveIntegerField('Cuota mensual (unidades)')

    class Meta:
        verbose_name = 'cuota de programa'
        verbose_name_plural = 'cuotas de programa'
        constraints = [models.UniqueConstraint(fields=['inscripcion', 'producto'], name='cuota_unica_producto')]

    def __str__(self):
        return f'{self.producto.nombre}: {self.cantidad_mensual}/mes'

    def entregado_mes(self):
        from django.db.models import Sum
        from dispensacion.models import DispensacionItem
        hoy = timezone.localdate()
        return DispensacionItem.objects.filter(
            dispensacion__paciente=self.inscripcion.paciente, dispensacion__programa=self.inscripcion.programa,
            producto=self.producto, dispensacion__fecha__year=hoy.year, dispensacion__fecha__month=hoy.month,
        ).aggregate(t=Sum('cantidad'))['t'] or 0

    def saldo_mes(self):
        return max(self.cantidad_mensual - self.entregado_mes(), 0)
