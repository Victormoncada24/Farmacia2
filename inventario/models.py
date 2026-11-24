from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, IntegerField, Min, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone


class Ubicacion(models.TextChoices):
    BODEGA = 'BODEGA', 'Bodega'
    VITRINA = 'VITRINA', 'Vitrina'


class Categoria(models.Model):
    nombre = models.CharField('Nombre', max_length=80, unique=True)
    descripcion = models.CharField('Descripción', max_length=200, blank=True)

    class Meta:
        verbose_name = 'categoría'
        verbose_name_plural = 'categorías'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class ProductoQuerySet(models.QuerySet):
    def con_stock(self):
        """Anota stock UTILIZABLE (lotes activos y no vencidos) por ubicación y total."""
        hoy = timezone.localdate()
        util = Q(lotes__activo=True, lotes__fecha_vencimiento__gte=hoy)
        entero = IntegerField()
        return self.annotate(
            stock_bodega=Coalesce(
                Sum('lotes__stocks__cantidad', filter=util & Q(lotes__stocks__ubicacion=Ubicacion.BODEGA)),
                0, output_field=entero),
            stock_vitrina=Coalesce(
                Sum('lotes__stocks__cantidad', filter=util & Q(lotes__stocks__ubicacion=Ubicacion.VITRINA)),
                0, output_field=entero),
            proximo_vencimiento=Min(
                'lotes__fecha_vencimiento',
                filter=util & Q(lotes__stocks__cantidad__gt=0)),
        ).annotate(stock_total=F('stock_bodega') + F('stock_vitrina'))


class Producto(models.Model):
    class Tipo(models.TextChoices):
        MEDICAMENTO = 'MEDICAMENTO', 'Medicamento'
        INSUMO = 'INSUMO', 'Insumo clínico'

    class Control(models.TextChoices):
        NINGUNO = 'NINGUNO', 'No controlado'
        ESTUPEFACIENTE = 'ESTUPEFACIENTE', 'Estupefaciente'
        PSICOTROPICO = 'PSICOTROPICO', 'Psicotrópico'

    codigo = models.CharField('Código', max_length=30, unique=True)
    codigo_barras = models.CharField('Código de barras', max_length=50, blank=True)
    nombre = models.CharField('Nombre', max_length=150)
    principio_activo = models.CharField('Principio activo', max_length=150, blank=True)
    presentacion = models.CharField('Presentación', max_length=100, blank=True,
                                    help_text='Ej.: Comprimidos 50 mg, caja x 30')
    tipo = models.CharField('Tipo', max_length=12, choices=Tipo.choices, default=Tipo.MEDICAMENTO)
    categoria = models.ForeignKey(Categoria, verbose_name='Categoría', on_delete=models.PROTECT,
                                  related_name='productos')
    control = models.CharField('Control especial (ISP)', max_length=15, choices=Control.choices,
                               default=Control.NINGUNO)
    stock_minimo = models.PositiveIntegerField('Stock mínimo (crítico)', default=0,
                                               help_text='Bajo este nivel se genera una alerta.')
    stock_objetivo = models.PositiveIntegerField('Stock objetivo', default=0,
                                                 help_text='Nivel deseado al reponer. Si es 0 se usa el doble del mínimo.')
    activo = models.BooleanField('Activo', default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    objects = ProductoQuerySet.as_manager()

    class Meta:
        verbose_name = 'producto'
        verbose_name_plural = 'productos'
        ordering = ['nombre']

    def __str__(self):
        return f'{self.nombre} {self.presentacion}'.strip()

    @property
    def es_controlado(self):
        return self.control != self.Control.NINGUNO

    @property
    def objetivo_efectivo(self):
        return self.stock_objetivo or self.stock_minimo * 2

    @property
    def estado_stock(self):
        total = getattr(self, 'stock_total', None)
        if total is None:
            hoy = timezone.localdate()
            total = StockLote.objects.filter(
                lote__producto=self, lote__activo=True, lote__fecha_vencimiento__gte=hoy
            ).aggregate(t=Sum('cantidad'))['t'] or 0
        if total <= 0:
            return 'SIN_STOCK'
        if self.stock_minimo and total <= self.stock_minimo:
            return 'CRITICO'
        return 'NORMAL'

    @property
    def estado_stock_texto(self):
        return {'SIN_STOCK': 'Sin stock', 'CRITICO': 'Crítico', 'NORMAL': 'Normal'}[self.estado_stock]


class Lote(models.Model):
    class Origen(models.TextChoices):
        CENABAST = 'CENABAST', 'CENABAST / remesa pública'
        SERVICIO = 'SERVICIO', 'Servicio de Salud'
        COMPRA = 'COMPRA', 'Compra local'
        DONACION = 'DONACION', 'Donación / traslado'
        OTRO = 'OTRO', 'Otro'

    producto = models.ForeignKey(Producto, verbose_name='Producto', on_delete=models.PROTECT, related_name='lotes')
    numero_lote = models.CharField('N° de lote', max_length=50)
    fecha_vencimiento = models.DateField('Fecha de vencimiento')
    fecha_ingreso = models.DateField('Fecha de ingreso', default=timezone.localdate)
    origen = models.CharField('Origen', max_length=10, choices=Origen.choices, default=Origen.CENABAST)
    documento_ref = models.CharField('N° de guía / remesa', max_length=60, blank=True)
    activo = models.BooleanField('Activo', default=True)

    class Meta:
        verbose_name = 'lote'
        verbose_name_plural = 'lotes'
        ordering = ['fecha_vencimiento', 'id']
        constraints = [models.UniqueConstraint(fields=['producto', 'numero_lote'], name='lote_unico_por_producto')]

    def __str__(self):
        return f'{self.producto.nombre} · lote {self.numero_lote} (vence {self.fecha_vencimiento:%d/%m/%Y})'

    @property
    def dias_para_vencer(self):
        return (self.fecha_vencimiento - timezone.localdate()).days

    @property
    def estado_vencimiento(self):
        dias = self.dias_para_vencer
        if dias < 0:
            return 'VENCIDO'
        if dias <= settings.ALERTA_VENCIMIENTO_CRITICO_DIAS:
            return 'CRITICO'
        if dias <= settings.ALERTA_VENCIMIENTO_DIAS:
            return 'PROXIMO'
        return 'VIGENTE'

    @property
    def estado_vencimiento_texto(self):
        return {'VENCIDO': 'Vencido', 'CRITICO': 'Vence en < 30 días', 'PROXIMO': 'Próximo a vencer',
                'VIGENTE': 'Vigente'}[self.estado_vencimiento]

    @property
    def stock_total(self):
        return self.stocks.aggregate(t=Sum('cantidad'))['t'] or 0

    def stock_en(self, ubicacion):
        return self.stocks.filter(ubicacion=ubicacion).aggregate(t=Sum('cantidad'))['t'] or 0

    @property
    def stock_bodega(self):
        return self.stock_en(Ubicacion.BODEGA)

    @property
    def stock_vitrina(self):
        return self.stock_en(Ubicacion.VITRINA)


class StockLote(models.Model):
    """Existencias de un lote en una ubicación física (bodega o vitrina)."""
    lote = models.ForeignKey(Lote, on_delete=models.CASCADE, related_name='stocks')
    ubicacion = models.CharField('Ubicación', max_length=10, choices=Ubicacion.choices)
    cantidad = models.PositiveIntegerField('Cantidad', default=0)

    class Meta:
        verbose_name = 'stock por lote'
        verbose_name_plural = 'stock por lote'
        constraints = [models.UniqueConstraint(fields=['lote', 'ubicacion'], name='stock_unico_lote_ubicacion')]

    def __str__(self):
        return f'{self.lote} · {self.get_ubicacion_display()}: {self.cantidad}'


class MovimientoInventario(models.Model):
    """Historial completo de movimientos (RF-17)."""

    class Tipo(models.TextChoices):
        INGRESO = 'INGRESO', 'Ingreso de lote'
        TRANSFERENCIA = 'TRANSFERENCIA', 'Transferencia bodega/vitrina'
        DISPENSACION = 'DISPENSACION', 'Dispensación a paciente'
        REPOSICION_CARRO = 'REPOSICION_CARRO', 'Reposición de carro clínico'
        AJUSTE_POSITIVO = 'AJUSTE_POSITIVO', 'Ajuste (+)'
        AJUSTE_NEGATIVO = 'AJUSTE_NEGATIVO', 'Ajuste (−)'
        MERMA = 'MERMA', 'Merma / pérdida'
        BAJA_VENCIDO = 'BAJA_VENCIDO', 'Baja por vencimiento'

    fecha = models.DateTimeField('Fecha y hora', default=timezone.now, db_index=True)
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='movimientos')
    lote = models.ForeignKey(Lote, on_delete=models.PROTECT, related_name='movimientos')
    tipo = models.CharField('Tipo', max_length=20, choices=Tipo.choices)
    ubicacion_origen = models.CharField('Origen', max_length=10, choices=Ubicacion.choices, blank=True)
    ubicacion_destino = models.CharField('Destino', max_length=10, choices=Ubicacion.choices, blank=True)
    cantidad = models.PositiveIntegerField('Cantidad', validators=[MinValueValidator(1)])
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='movimientos_inventario')
    referencia = models.CharField('Referencia', max_length=120, blank=True)
    observacion = models.TextField('Observación', blank=True)

    class Meta:
        verbose_name = 'movimiento de inventario'
        verbose_name_plural = 'movimientos de inventario'
        ordering = ['-fecha', '-id']

    def __str__(self):
        return f'{self.get_tipo_display()} {self.cantidad} × {self.producto.nombre}'
