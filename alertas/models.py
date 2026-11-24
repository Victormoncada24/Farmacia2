from django.conf import settings
from django.db import models
from django.utils import timezone


class Alerta(models.Model):
    class Tipo(models.TextChoices):
        STOCK_CRITICO = 'STOCK_CRITICO', 'Stock crítico'
        PROXIMO_VENCER = 'PROXIMO_VENCER', 'Próximo a vencer'
        VENCIDO = 'VENCIDO', 'Lote vencido con stock'
        CARRO_FALTANTE = 'CARRO_FALTANTE', 'Faltante en carro clínico'
        CARRO_VENCIMIENTO = 'CARRO_VENCIMIENTO', 'Vencimiento en carro clínico'
        DIFERENCIA_CARRO = 'DIFERENCIA_CARRO', 'Diferencia de stock en carro'
        DESCUADRE_LIBRO = 'DESCUADRE_LIBRO', 'Descuadre libro vs. stock (controlado)'
        DESCUADRE_CONTEO = 'DESCUADRE_CONTEO', 'Descuadre en conteo físico (controlado)'
        QUIEBRE_PROYECTADO = 'QUIEBRE_PROYECTADO', 'Quiebre de stock proyectado'
        RIESGO_MERMA = 'RIESGO_MERMA', 'Riesgo de pérdida por vencimiento'
        PEDIDO_ATRASADO = 'PEDIDO_ATRASADO', 'Pedido a proveedor atrasado'

    class Severidad(models.TextChoices):
        ALTA = 'ALTA', 'Alta'
        MEDIA = 'MEDIA', 'Media'
        BAJA = 'BAJA', 'Baja'

    # Alertas que el sistema abre y cierra solo según el estado real
    AUTOMATICAS = ('STOCK_CRITICO', 'PROXIMO_VENCER', 'VENCIDO', 'CARRO_FALTANTE',
                   'CARRO_VENCIMIENTO', 'DESCUADRE_LIBRO', 'QUIEBRE_PROYECTADO', 'RIESGO_MERMA', 'PEDIDO_ATRASADO')

    tipo = models.CharField('Tipo', max_length=20, choices=Tipo.choices)
    severidad = models.CharField('Severidad', max_length=6, choices=Severidad.choices, default=Severidad.MEDIA)
    producto = models.ForeignKey('inventario.Producto', null=True, blank=True, on_delete=models.CASCADE,
                                 related_name='alertas')
    lote = models.ForeignKey('inventario.Lote', null=True, blank=True, on_delete=models.CASCADE,
                             related_name='alertas')
    carro = models.ForeignKey('carros.CarroClinico', null=True, blank=True, on_delete=models.CASCADE,
                              related_name='alertas')
    pedido = models.ForeignKey('pedidos.Pedido', null=True, blank=True, on_delete=models.CASCADE,
                               related_name='alertas')
    mensaje = models.CharField('Mensaje', max_length=255)
    creada_en = models.DateTimeField('Generada', default=timezone.now, db_index=True)
    resuelta = models.BooleanField('Resuelta', default=False, db_index=True)
    resuelta_en = models.DateTimeField('Resuelta el', null=True, blank=True)
    resuelta_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name='+')

    class Meta:
        verbose_name = 'alerta'
        verbose_name_plural = 'alertas'
        ordering = ['resuelta', '-creada_en']

    def __str__(self):
        return f'[{self.get_severidad_display()}] {self.mensaje}'

    @property
    def es_automatica(self):
        return self.tipo in self.AUTOMATICAS

    @property
    def severidad_texto(self):
        return self.get_severidad_display()
