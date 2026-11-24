from django.conf import settings
from django.db import models
from django.utils import timezone


class CarroClinico(models.Model):
    class Tipo(models.TextChoices):
        PARO = 'PARO', 'Carro de Paro'
        UNIDOSIS = 'UNIDOSIS', 'Carro Unidosis (tratamiento)'

    nombre = models.CharField('Nombre', max_length=100, unique=True)
    tipo = models.CharField('Tipo', max_length=10, choices=Tipo.choices)
    ubicacion = models.CharField('Servicio / ubicación', max_length=120, blank=True)
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name='carros_a_cargo', verbose_name='Responsable')
    precinto = models.CharField('N° de precinto', max_length=40, blank=True,
                                help_text='Precinto de seguridad vigente (Carro de Paro).')
    activo = models.BooleanField('Activo', default=True)

    class Meta:
        verbose_name = 'carro clínico'
        verbose_name_plural = 'carros clínicos'
        ordering = ['tipo', 'nombre']

    def __str__(self):
        return self.nombre

    @property
    def tipo_texto(self):
        return 'Paro' if self.tipo == self.Tipo.PARO else 'Unidosis'

    @property
    def total_items(self):
        return self.items.count()

    @property
    def items_con_faltante(self):
        return sum(1 for i in self.items.all() if i.cantidad_actual < i.cantidad_requerida)

    @property
    def estado_texto(self):
        if not self.total_items:
            return 'Pendiente'
        return 'Crítico' if self.items_con_faltante else 'Normal'


class CarroItem(models.Model):
    """Dotación de un carro: qué debe contener y qué contiene actualmente."""
    carro = models.ForeignKey(CarroClinico, on_delete=models.CASCADE, related_name='items')
    producto = models.ForeignKey('inventario.Producto', on_delete=models.PROTECT, related_name='en_carros')
    cantidad_requerida = models.PositiveIntegerField('Dotación requerida')
    cantidad_actual = models.PositiveIntegerField('Cantidad actual', default=0)
    fecha_vencimiento = models.DateField('Vencimiento más próximo', null=True, blank=True)

    class Meta:
        verbose_name = 'ítem de carro'
        verbose_name_plural = 'ítems de carro'
        ordering = ['producto__nombre']
        constraints = [models.UniqueConstraint(fields=['carro', 'producto'], name='item_unico_por_carro')]

    def __str__(self):
        return f'{self.carro.nombre}: {self.producto.nombre} ({self.cantidad_actual}/{self.cantidad_requerida})'

    @property
    def faltante(self):
        return max(self.cantidad_requerida - self.cantidad_actual, 0)

    @property
    def estado(self):
        hoy = timezone.localdate()
        if self.cantidad_actual > 0 and self.fecha_vencimiento and self.fecha_vencimiento < hoy:
            return 'Vencido'
        if self.cantidad_actual < self.cantidad_requerida:
            return 'Crítico' if self.cantidad_actual == 0 else 'Pendiente'
        if self.fecha_vencimiento and (self.fecha_vencimiento - hoy).days <= settings.ALERTA_VENCIMIENTO_DIAS:
            return 'Próximo a vencer'
        return 'Normal'


class ReposicionCarro(models.Model):
    carro = models.ForeignKey(CarroClinico, on_delete=models.PROTECT, related_name='reposiciones')
    fecha = models.DateTimeField(default=timezone.now, db_index=True)
    realizada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                      related_name='reposiciones_carro')
    solicitud = models.ForeignKey('SolicitudReposicion', null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name='reposiciones')
    observacion = models.TextField('Observación', blank=True)

    class Meta:
        verbose_name = 'reposición de carro'
        verbose_name_plural = 'reposiciones de carros'
        ordering = ['-fecha']

    def __str__(self):
        return f'Reposición {self.carro.nombre} {self.fecha:%d/%m/%Y %H:%M}'


class ReposicionDetalle(models.Model):
    reposicion = models.ForeignKey(ReposicionCarro, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey('inventario.Producto', on_delete=models.PROTECT, related_name='+')
    cantidad_sistema = models.IntegerField('Según sistema')
    cantidad_contada = models.IntegerField('Contada')
    diferencia = models.IntegerField('Diferencia (contada − sistema)')
    cantidad_repuesta = models.PositiveIntegerField('Repuesta', default=0)

    class Meta:
        verbose_name = 'detalle de reposición'
        verbose_name_plural = 'detalles de reposición'

    def __str__(self):
        return f'{self.producto.nombre}: +{self.cantidad_repuesta}'


class ConsumoCarro(models.Model):
    carro = models.ForeignKey(CarroClinico, on_delete=models.PROTECT, related_name='consumos')
    producto = models.ForeignKey('inventario.Producto', on_delete=models.PROTECT, related_name='+')
    cantidad = models.PositiveIntegerField('Cantidad consumida')
    fecha = models.DateTimeField(default=timezone.now, db_index=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='consumos_carro')
    referencia = models.CharField('Paciente / cama / referencia', max_length=120, blank=True)
    observacion = models.CharField('Observación', max_length=200, blank=True)

    class Meta:
        verbose_name = 'consumo de carro'
        verbose_name_plural = 'consumos de carros'
        ordering = ['-fecha']

    def __str__(self):
        return f'{self.carro.nombre}: {self.producto.nombre} × {self.cantidad}'


class SolicitudReposicion(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente'
        ATENDIDA = 'ATENDIDA', 'Atendida'
        PARCIAL = 'PARCIAL', 'Atendida parcialmente'
        RECHAZADA = 'RECHAZADA', 'Rechazada'

    carro = models.ForeignKey(CarroClinico, on_delete=models.PROTECT, related_name='solicitudes')
    solicitante = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='solicitudes_carro')
    creada_en = models.DateTimeField(default=timezone.now, db_index=True)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)
    observacion = models.CharField('Observación', max_length=250, blank=True)
    atendida_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name='solicitudes_atendidas')
    atendida_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'solicitud de reposición'
        verbose_name_plural = 'solicitudes de reposición'
        ordering = ['-creada_en']

    def __str__(self):
        return f'Solicitud N° {self.pk} — {self.carro.nombre}'

    @property
    def estado_texto(self):
        return self.get_estado_display()


class SolicitudDetalle(models.Model):
    solicitud = models.ForeignKey(SolicitudReposicion, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey('inventario.Producto', on_delete=models.PROTECT, related_name='+')
    cantidad_solicitada = models.PositiveIntegerField('Solicitada')
    cantidad_entregada = models.PositiveIntegerField('Entregada', default=0)

    class Meta:
        verbose_name = 'detalle de solicitud'
        verbose_name_plural = 'detalles de solicitud'

    def __str__(self):
        return f'{self.producto.nombre}: {self.cantidad_solicitada}'
