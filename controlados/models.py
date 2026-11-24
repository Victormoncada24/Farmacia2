from django.conf import settings
from django.db import models
from django.utils import timezone


class MovimientoControlado(models.Model):
    """Libro oficial digital de estupefacientes y psicotrópicos (ISP)."""

    class Tipo(models.TextChoices):
        SALDO_INICIAL = 'SALDO_INICIAL', 'Saldo inicial'
        INGRESO = 'INGRESO', 'Ingreso'
        EGRESO = 'EGRESO', 'Egreso (dispensación / traslado)'
        AJUSTE_POSITIVO = 'AJUSTE_POSITIVO', 'Ajuste (+)'
        AJUSTE_NEGATIVO = 'AJUSTE_NEGATIVO', 'Ajuste (−)'
        MERMA = 'MERMA', 'Merma / baja'

    POSITIVOS = ('SALDO_INICIAL', 'INGRESO', 'AJUSTE_POSITIVO')

    producto = models.ForeignKey('inventario.Producto', on_delete=models.PROTECT, related_name='libro')
    lote = models.ForeignKey('inventario.Lote', null=True, blank=True, on_delete=models.PROTECT,
                             related_name='libro')
    fecha = models.DateTimeField('Fecha y hora', default=timezone.now, db_index=True)
    tipo = models.CharField('Movimiento', max_length=16, choices=Tipo.choices)
    cantidad = models.PositiveIntegerField('Cantidad')
    saldo_resultante = models.IntegerField('Saldo del libro')
    referencia = models.CharField('Documento de respaldo', max_length=120, blank=True)
    paciente_documento = models.CharField('Documento del paciente', max_length=20, blank=True)
    observacion = models.TextField('Observación', blank=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                       related_name='libro_registrado')
    firmado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                    related_name='libro_firmado')
    firmado_en = models.DateTimeField('Firmado el', null=True, blank=True)

    class Meta:
        verbose_name = 'movimiento del libro de controlados'
        verbose_name_plural = 'libro de controlados'
        ordering = ['-fecha', '-id']

    def __str__(self):
        return f'{self.get_tipo_display()} {self.cantidad} × {self.producto.nombre} (saldo {self.saldo_resultante})'

    @property
    def es_ingreso(self):
        return self.tipo in self.POSITIVOS

    @property
    def firmado(self):
        return self.firmado_por_id is not None

    @property
    def estado_firma(self):
        return 'Firmado' if self.firmado else 'Pendiente de firma'


class ConteoFisico(models.Model):
    """Conteo físico realizado por el Químico Farmacéutico, contrastado con el libro."""
    producto = models.ForeignKey('inventario.Producto', on_delete=models.PROTECT, related_name='conteos')
    fecha = models.DateTimeField(default=timezone.now)
    cantidad_contada = models.PositiveIntegerField('Cantidad contada')
    saldo_libro = models.IntegerField('Saldo según libro')
    stock_sistema = models.IntegerField('Stock según sistema')
    diferencia = models.IntegerField('Diferencia (contado − libro)')
    observacion = models.TextField('Observación', blank=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='conteos')
    resuelto = models.BooleanField('Resuelto', default=False)
    resuelto_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name='+')
    resuelto_en = models.DateTimeField(null=True, blank=True)
    nota_resolucion = models.TextField('Nota de resolución', blank=True)

    class Meta:
        verbose_name = 'conteo físico'
        verbose_name_plural = 'conteos físicos'
        ordering = ['-fecha']

    def __str__(self):
        return f'Conteo {self.producto.nombre}: {self.cantidad_contada} (dif. {self.diferencia:+d})'

    @property
    def estado_texto(self):
        if self.diferencia == 0:
            return 'Cuadra'
        return 'Resuelto' if self.resuelto else 'Descuadre'
