from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from core.fields import RutField

from .logica import ESTADOS_ABIERTOS, dias_atraso, numero_pedido, porcentaje_recibido


class Proveedor(models.Model):
    """Entidad a la que el establecimiento le solicita medicamentos e insumos."""

    class Tipo(models.TextChoices):
        CENABAST = 'CENABAST', 'CENABAST'
        SERVICIO_SALUD = 'SERVICIO_SALUD', 'Servicio de Salud / bodega central'
        DROGUERIA = 'DROGUERIA', 'Droguería / distribuidor'
        LABORATORIO = 'LABORATORIO', 'Laboratorio'
        OTRO = 'OTRO', 'Otro'

    nombre = models.CharField('Nombre', max_length=150, unique=True)
    tipo = models.CharField('Tipo', max_length=15, choices=Tipo.choices, default=Tipo.CENABAST)
    rut = RutField('RUT', blank=True)
    contacto = models.CharField('Persona de contacto', max_length=120, blank=True)
    telefono = models.CharField('Teléfono', max_length=30, blank=True)
    email = models.EmailField('Correo electrónico', blank=True)
    plazo_entrega_dias = models.PositiveIntegerField('Plazo de entrega (días)', default=7,
                                                     validators=[MinValueValidator(1)])
    observaciones = models.TextField('Observaciones', blank=True)
    activo = models.BooleanField('Activo', default=True)

    class Meta:
        verbose_name = 'proveedor'
        verbose_name_plural = 'proveedores'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    @property
    def origen_lote(self):
        """Valor de Lote.Origen que corresponde a la mercadería recibida de este proveedor."""
        return {'CENABAST': 'CENABAST', 'SERVICIO_SALUD': 'SERVICIO', 'DROGUERIA': 'COMPRA',
                'LABORATORIO': 'COMPRA'}.get(self.tipo, 'OTRO')


class Pedido(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = 'BORRADOR', 'Borrador'
        ENVIADO = 'ENVIADO', 'Enviado'
        PARCIAL = 'PARCIAL', 'Recibido parcial'
        RECIBIDO = 'RECIBIDO', 'Recibido'
        CERRADO = 'CERRADO', 'Cerrado con faltantes'
        ANULADO = 'ANULADO', 'Anulado'

    class Prioridad(models.TextChoices):
        NORMAL = 'NORMAL', 'Normal'
        URGENTE = 'URGENTE', 'Urgente'

    numero = models.CharField('N° de pedido', max_length=20, unique=True, null=True, blank=True, editable=False)
    proveedor = models.ForeignKey(Proveedor, verbose_name='Proveedor', on_delete=models.PROTECT,
                                  related_name='pedidos')
    estado = models.CharField('Estado', max_length=10, choices=Estado.choices, default=Estado.BORRADOR,
                              db_index=True)
    prioridad = models.CharField('Prioridad', max_length=8, choices=Prioridad.choices, default=Prioridad.NORMAL)
    fecha = models.DateTimeField('Fecha de creación', default=timezone.now, db_index=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='pedidos_creados')
    observacion = models.TextField('Observaciones', blank=True)
    origen_sugerencia = models.BooleanField('Generado desde el abastecimiento inteligente', default=False)
    fecha_envio = models.DateTimeField('Fecha de envío', null=True, blank=True)
    aprobado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                     related_name='pedidos_autorizados')
    fecha_entrega_estimada = models.DateField('Entrega estimada', null=True, blank=True)
    motivo_cierre = models.CharField('Motivo de cierre', max_length=250, blank=True)
    motivo_anulacion = models.CharField('Motivo de anulación', max_length=250, blank=True)

    class Meta:
        verbose_name = 'pedido a proveedor'
        verbose_name_plural = 'pedidos a proveedores'
        ordering = ['-fecha', '-id']

    def save(self, *args, **kwargs):
        creando = self._state.adding
        super().save(*args, **kwargs)
        if creando and not self.numero:
            self.numero = numero_pedido(timezone.localdate().year, self.pk)
            type(self).objects.filter(pk=self.pk).update(numero=self.numero)

    def __str__(self):
        return f'Pedido {self.numero or self.pk} — {self.proveedor.nombre}'

    # ---- estado
    @property
    def estado_texto(self):
        return self.get_estado_display()

    @property
    def editable(self):
        return self.estado == self.Estado.BORRADOR

    @property
    def abierto(self):
        return self.estado in ESTADOS_ABIERTOS

    # ---- avance (usan items.all() para aprovechar prefetch_related)
    @property
    def total_items(self):
        return len(self.items.all())

    @property
    def unidades_pedidas(self):
        return sum(i.cantidad_pedida for i in self.items.all())

    @property
    def unidades_recibidas(self):
        return sum(i.cantidad_recibida for i in self.items.all())

    @property
    def porcentaje_recibido(self):
        return porcentaje_recibido((i.cantidad_pedida, i.cantidad_recibida) for i in self.items.all())

    @property
    def avance_texto(self):
        return '—' if self.estado in ('BORRADOR', 'ANULADO') else f'{self.porcentaje_recibido}%'

    @property
    def atraso_dias(self):
        return dias_atraso(self.estado, self.fecha_entrega_estimada, timezone.localdate())

    @property
    def atraso_texto(self):
        dias = self.atraso_dias
        return f'{dias} d' if dias else ''


class PedidoItem(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='items')
    producto = models.ForeignKey('inventario.Producto', verbose_name='Producto', on_delete=models.PROTECT,
                                 related_name='items_pedido')
    cantidad_pedida = models.PositiveIntegerField('Cantidad pedida', validators=[MinValueValidator(1)])
    cantidad_recibida = models.PositiveIntegerField('Cantidad recibida', default=0)

    class Meta:
        verbose_name = 'ítem de pedido'
        verbose_name_plural = 'ítems de pedido'
        ordering = ['producto__nombre']
        constraints = [models.UniqueConstraint(fields=['pedido', 'producto'], name='producto_unico_por_pedido')]

    def __str__(self):
        return f'{self.producto.nombre} × {self.cantidad_pedida}'

    @property
    def pendiente(self):
        return max(self.cantidad_pedida - self.cantidad_recibida, 0)


class Recepcion(models.Model):
    """Una entrega (total o parcial) del proveedor contra un pedido."""
    pedido = models.ForeignKey(Pedido, on_delete=models.PROTECT, related_name='recepciones')
    fecha = models.DateTimeField('Fecha y hora', default=timezone.now)
    recibido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                     related_name='recepciones_pedido')
    documento_ref = models.CharField('N° de guía de despacho / factura', max_length=60)
    ubicacion = models.CharField('Ubicación de ingreso', max_length=10)
    observacion = models.TextField('Observación', blank=True)

    class Meta:
        verbose_name = 'recepción de pedido'
        verbose_name_plural = 'recepciones de pedidos'
        ordering = ['-fecha']

    def __str__(self):
        return f'Recepción {self.documento_ref} ({self.pedido.numero})'


class RecepcionItem(models.Model):
    recepcion = models.ForeignKey(Recepcion, on_delete=models.CASCADE, related_name='items')
    pedido_item = models.ForeignKey(PedidoItem, on_delete=models.PROTECT, related_name='recepciones')
    producto = models.ForeignKey('inventario.Producto', on_delete=models.PROTECT, related_name='+')
    lote = models.ForeignKey('inventario.Lote', on_delete=models.PROTECT, related_name='recepciones_pedido')
    cantidad = models.PositiveIntegerField('Cantidad recibida')

    class Meta:
        verbose_name = 'ítem recibido'
        verbose_name_plural = 'ítems recibidos'

    def __str__(self):
        return f'{self.producto.nombre} × {self.cantidad} (lote {self.lote.numero_lote})'
