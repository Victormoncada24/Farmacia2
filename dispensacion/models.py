import os
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from core.fields import EncryptedTextField, RutField


def ruta_receta(instance, filename):
    """Los archivos se guardan con nombre aleatorio (nunca el nombre original)."""
    extension = os.path.splitext(filename)[1].lower()
    return f'recetas/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{extension}'


class Receta(models.Model):
    class Tipo(models.TextChoices):
        FISICA = 'FISICA', 'Física'
        DIGITAL = 'DIGITAL', 'Digital'

    class Modalidad(models.TextChoices):
        ESTANDAR = 'ESTANDAR', 'Estándar'
        RETENIDA = 'RETENIDA', 'Retenida (controlados)'

    class Estado(models.TextChoices):
        VIGENTE = 'VIGENTE', 'Vigente'
        ANULADA = 'ANULADA', 'Anulada'

    paciente = models.ForeignKey('pacientes.Paciente', on_delete=models.PROTECT, related_name='recetas')
    numero = models.CharField('N° / folio de receta', max_length=30)
    tipo = models.CharField('Tipo', max_length=8, choices=Tipo.choices, default=Tipo.FISICA)
    modalidad = models.CharField('Modalidad', max_length=10, choices=Modalidad.choices, default=Modalidad.ESTANDAR)
    control_saldo = models.BooleanField(
        'Con control de saldo', default=True,
        help_text='Si está desmarcado, la receta no limita la cantidad total a entregar.')
    fecha_emision = models.DateField('Fecha de emisión', default=timezone.localdate)
    vigencia_dias = models.PositiveIntegerField('Vigencia (días)', default=30)
    medico_nombre = models.CharField('Médico emisor', max_length=150)
    medico_rut = RutField('RUT del médico')
    establecimiento_emisor = models.CharField('Establecimiento emisor', max_length=150, blank=True)
    programa = models.ForeignKey('pacientes.Programa', null=True, blank=True, on_delete=models.PROTECT,
                                 related_name='recetas', verbose_name='Programa de salud')
    archivo = models.FileField('Archivo de la receta (PDF/JPG/PNG)', upload_to=ruta_receta, blank=True, null=True)
    observaciones = EncryptedTextField('Diagnóstico / observaciones', blank=True)
    estado = models.CharField('Estado', max_length=8, choices=Estado.choices, default=Estado.VIGENTE)
    motivo_anulacion = models.CharField('Motivo de anulación', max_length=200, blank=True)
    registrada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                       related_name='recetas_registradas')
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'receta'
        verbose_name_plural = 'recetas'
        ordering = ['-fecha_emision', '-id']

    def __str__(self):
        return f'Receta {self.numero} — {self.paciente.nombre_completo}'

    @property
    def fecha_vencimiento(self):
        return self.fecha_emision + timedelta(days=self.vigencia_dias)

    @property
    def saldo_total(self):
        return sum(item.saldo for item in self.items.all())

    @property
    def estado_efectivo(self):
        if self.estado == self.Estado.ANULADA:
            return 'ANULADA'
        if timezone.localdate() > self.fecha_vencimiento:
            return 'VENCIDA'
        if self.control_saldo and self.saldo_total <= 0:
            return 'AGOTADA'
        return 'VIGENTE'

    @property
    def estado_texto(self):
        return {'ANULADA': 'Anulada', 'VENCIDA': 'Vencida', 'AGOTADA': 'Agotada', 'VIGENTE': 'Vigente'}[
            self.estado_efectivo]

    @property
    def dispensable(self):
        return self.estado_efectivo == 'VIGENTE'


class RecetaItem(models.Model):
    receta = models.ForeignKey(Receta, on_delete=models.CASCADE, related_name='items')
    producto = models.ForeignKey('inventario.Producto', on_delete=models.PROTECT, related_name='items_receta')
    cantidad_prescrita = models.PositiveIntegerField('Cantidad prescrita (total)')
    indicacion = models.CharField('Indicación / posología', max_length=200, blank=True)

    class Meta:
        verbose_name = 'ítem de receta'
        verbose_name_plural = 'ítems de receta'

    def __str__(self):
        return f'{self.producto.nombre} × {self.cantidad_prescrita}'

    @property
    def cantidad_dispensada(self):
        return self.entregas.aggregate(t=Sum('cantidad'))['t'] or 0

    @property
    def saldo(self):
        return max(self.cantidad_prescrita - self.cantidad_dispensada, 0)


class Dispensacion(models.Model):
    receta = models.ForeignKey(Receta, on_delete=models.PROTECT, related_name='dispensaciones')
    paciente = models.ForeignKey('pacientes.Paciente', on_delete=models.PROTECT, related_name='dispensaciones')
    programa = models.ForeignKey('pacientes.Programa', null=True, blank=True, on_delete=models.PROTECT,
                                 related_name='dispensaciones')
    fecha = models.DateTimeField('Fecha y hora', default=timezone.now, db_index=True)
    dispensado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                       related_name='dispensaciones')
    retira_tercero = models.BooleanField('Retira un tercero', default=False)
    retiro_nombre = models.CharField('Nombre de quien retira', max_length=150, blank=True)
    retiro_rut = RutField('RUT de quien retira', blank=True)
    retiro_parentesco = models.CharField('Relación con el paciente', max_length=60, blank=True)
    observacion = models.TextField('Observación', blank=True)
    excepcion_cuota = models.BooleanField('Excepción de cuota autorizada', default=False)
    autorizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                       related_name='dispensaciones_autorizadas')

    class Meta:
        verbose_name = 'dispensación'
        verbose_name_plural = 'dispensaciones'
        ordering = ['-fecha', '-id']

    def __str__(self):
        return f'Dispensación N° {self.pk} — {self.paciente.nombre_completo}'

    @property
    def quien_retira(self):
        if self.retira_tercero:
            return f'{self.retiro_nombre} ({self.retiro_parentesco}), RUT {self.retiro_rut}'
        return 'El propio paciente'

    @property
    def programa_texto(self):
        return self.programa.nombre if self.programa else 'Atención estándar'

    @property
    def resumen_items(self):
        return ', '.join(f'{i.producto.nombre} × {i.cantidad}' for i in self.items.select_related('producto'))


class DispensacionItem(models.Model):
    dispensacion = models.ForeignKey(Dispensacion, on_delete=models.CASCADE, related_name='items')
    receta_item = models.ForeignKey(RecetaItem, on_delete=models.PROTECT, related_name='entregas')
    producto = models.ForeignKey('inventario.Producto', on_delete=models.PROTECT, related_name='entregas')
    lote = models.ForeignKey('inventario.Lote', on_delete=models.PROTECT, related_name='entregas')
    cantidad = models.PositiveIntegerField('Cantidad')

    class Meta:
        verbose_name = 'ítem dispensado'
        verbose_name_plural = 'ítems dispensados'

    def __str__(self):
        return f'{self.producto.nombre} × {self.cantidad} (lote {self.lote.numero_lote})'
