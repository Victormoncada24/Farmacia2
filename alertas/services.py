"""Generación y cierre de alertas (stock crítico, vencimientos, carros, controlados)."""
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import IntegerField, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from carros.models import CarroClinico, CarroItem
from controlados.services import saldo_libro
from analitica.services import analizar_abastecimiento
from inventario.models import Lote, Producto
from inventario.services import stock_disponible, stock_fisico_total
from pedidos.logica import dias_atraso
from pedidos.models import Pedido

from .models import Alerta

Tipo = Alerta.Tipo
Sev = Alerta.Severidad


def _abrir(tipo, severidad, mensaje, producto=None, lote=None, carro=None, pedido=None):
    """Abre la alerta si no existe una igual abierta; si existe, actualiza su texto/severidad."""
    existente = Alerta.objects.filter(resuelta=False, tipo=tipo, producto=producto, lote=lote,
                                     carro=carro, pedido=pedido).first()
    if existente:
        if existente.mensaje != mensaje or existente.severidad != severidad:
            existente.mensaje = mensaje
            existente.severidad = severidad
            existente.save(update_fields=['mensaje', 'severidad'])
        return existente
    return Alerta.objects.create(tipo=tipo, severidad=severidad, mensaje=mensaje,
                                 producto=producto, lote=lote, carro=carro, pedido=pedido)


def _cerrar(qs):
    qs.update(resuelta=True, resuelta_en=timezone.now())


def evaluar_stock(producto):
    """Evalúa de inmediato el nivel de stock de un producto (se llama tras cada movimiento)."""
    abiertas = Alerta.objects.filter(resuelta=False, tipo=Tipo.STOCK_CRITICO, producto=producto)
    if not producto.activo or producto.stock_minimo <= 0:
        _cerrar(abiertas)
        return
    total = stock_disponible(producto)
    if total <= producto.stock_minimo:
        estado = 'SIN STOCK' if total == 0 else 'stock crítico'
        _abrir(Tipo.STOCK_CRITICO, Sev.ALTA if total == 0 else Sev.MEDIA,
               f'{producto.nombre}: {estado} — disponible {total}, mínimo {producto.stock_minimo}.',
               producto=producto)
    else:
        _cerrar(abiertas)


def _evaluar_items_carro(items):
    hoy = timezone.localdate()
    limite = hoy + timedelta(days=settings.ALERTA_VENCIMIENTO_DIAS)
    vivas = set()
    for item in items:
        carro, producto = item.carro, item.producto
        faltante = item.cantidad_requerida - item.cantidad_actual
        if faltante > 0:
            sev = Sev.ALTA if carro.tipo == CarroClinico.Tipo.PARO else Sev.MEDIA
            alerta = _abrir(Tipo.CARRO_FALTANTE, sev,
                            f'{carro.nombre}: faltan {faltante} de {producto.nombre} '
                            f'({item.cantidad_actual}/{item.cantidad_requerida}).',
                            producto=producto, carro=carro)
            vivas.add(alerta.pk)
        if item.cantidad_actual > 0 and item.fecha_vencimiento and item.fecha_vencimiento <= limite:
            vencido = item.fecha_vencimiento < hoy
            alerta = _abrir(Tipo.CARRO_VENCIMIENTO, Sev.ALTA if vencido else Sev.MEDIA,
                            f'{carro.nombre}: {producto.nombre} '
                            f'{"VENCIDO" if vencido else "vence"} el {item.fecha_vencimiento:%d/%m/%Y}.',
                            producto=producto, carro=carro)
            vivas.add(alerta.pk)
    return vivas


def evaluar_carro(carro):
    """Reevalúa faltantes y vencimientos de un carro clínico."""
    items = CarroItem.objects.filter(carro=carro).select_related('carro', 'producto')
    vivas = _evaluar_items_carro(items) if carro.activo else set()
    _cerrar(Alerta.objects.filter(
        resuelta=False, carro=carro, tipo__in=(Tipo.CARRO_FALTANTE, Tipo.CARRO_VENCIMIENTO)
    ).exclude(pk__in=vivas))


@transaction.atomic
def sincronizar():
    """Recalcula TODAS las alertas automáticas. Abre las nuevas y cierra las que ya no aplican."""
    hoy = timezone.localdate()
    vivas = set()

    # 1) Stock crítico / sin stock
    for producto in Producto.objects.filter(activo=True, stock_minimo__gt=0).con_stock():
        if producto.stock_total <= producto.stock_minimo:
            estado = 'SIN STOCK' if producto.stock_total == 0 else 'stock crítico'
            alerta = _abrir(Tipo.STOCK_CRITICO, Sev.ALTA if producto.stock_total == 0 else Sev.MEDIA,
                            f'{producto.nombre}: {estado} — disponible {producto.stock_total}, '
                            f'mínimo {producto.stock_minimo}.', producto=producto)
            vivas.add(alerta.pk)

    # 2) Lotes vencidos / próximos a vencer con existencias
    limite = hoy + timedelta(days=settings.ALERTA_VENCIMIENTO_DIAS)
    lotes = (Lote.objects.filter(activo=True, fecha_vencimiento__lte=limite).select_related('producto')
             .annotate(existencias=Coalesce(Sum('stocks__cantidad'), 0, output_field=IntegerField()))
             .filter(existencias__gt=0))
    for lote in lotes:
        dias = (lote.fecha_vencimiento - hoy).days
        if dias < 0:
            alerta = _abrir(Tipo.VENCIDO, Sev.ALTA,
                            f'{lote.producto.nombre}, lote {lote.numero_lote}: VENCIDO el '
                            f'{lote.fecha_vencimiento:%d/%m/%Y} con {lote.existencias} unidades. Requiere baja.',
                            producto=lote.producto, lote=lote)
        else:
            sev = Sev.ALTA if dias <= settings.ALERTA_VENCIMIENTO_CRITICO_DIAS else Sev.MEDIA
            alerta = _abrir(Tipo.PROXIMO_VENCER, sev,
                            f'{lote.producto.nombre}, lote {lote.numero_lote}: vence en {dias} días '
                            f'({lote.fecha_vencimiento:%d/%m/%Y}), {lote.existencias} unidades.',
                            producto=lote.producto, lote=lote)
        vivas.add(alerta.pk)

    # 3) Carros clínicos
    vivas |= _evaluar_items_carro(
        CarroItem.objects.filter(carro__activo=True).select_related('carro', 'producto'))

    # 4) Controlados: libro digital vs. stock físico
    for producto in Producto.objects.filter(activo=True).exclude(control=Producto.Control.NINGUNO):
        libro, fisico = saldo_libro(producto), stock_fisico_total(producto)
        if libro != fisico:
            alerta = _abrir(Tipo.DESCUADRE_LIBRO, Sev.ALTA,
                            f'{producto.nombre} ({producto.get_control_display()}): el libro indica {libro} '
                            f'y el stock del sistema es {fisico} (diferencia {fisico - libro:+d}).',
                            producto=producto)
            vivas.add(alerta.pk)

    # 5) Predictivas: quiebre proyectado y riesgo de pérdida por vencimiento (módulo analítico)
    for fila in analizar_abastecimiento(hoy=hoy):
        if fila.estado in ('QUIEBRE', 'CRITICO'):
            cuando = f' — quiebre estimado el {fila.fecha_quiebre:%d/%m/%Y}' if fila.fecha_quiebre else ''
            transito = f' En tránsito: {fila.en_transito} u.' if fila.en_transito else ''
            alerta = _abrir(
                Tipo.QUIEBRE_PROYECTADO, Sev.ALTA if fila.estado == 'QUIEBRE' else Sev.MEDIA,
                f'{fila.producto.nombre}: consumo {fila.consumo_diario:.1f} u./día, cobertura '
                f'{fila.cobertura_texto} días{cuando}. Pedido sugerido: {fila.pedido} u.{transito}',
                producto=fila.producto)
            vivas.add(alerta.pk)
        if fila.en_riesgo > 0:
            alerta = _abrir(
                Tipo.RIESGO_MERMA, Sev.MEDIA,
                f'{fila.producto.nombre}: ~{fila.en_riesgo} unidades no alcanzarán a consumirse antes de vencer '
                f'al ritmo actual. Evalúe redistribución o priorización.', producto=fila.producto)
            vivas.add(alerta.pk)

    # 6) Pedidos a proveedores atrasados (entrega estimada vencida y mercadería sin recibir)
    atrasados = Pedido.objects.filter(estado__in=['ENVIADO', 'PARCIAL'],
                                      fecha_entrega_estimada__lt=hoy).select_related('proveedor')
    for pedido in atrasados:
        atraso = dias_atraso(pedido.estado, pedido.fecha_entrega_estimada, hoy)
        alerta = _abrir(
            Tipo.PEDIDO_ATRASADO, Sev.ALTA if (pedido.prioridad == 'URGENTE' or atraso > 7) else Sev.MEDIA,
            f'Pedido {pedido.numero} a {pedido.proveedor.nombre}: {atraso} días de atraso '
            f'(entrega estimada {pedido.fecha_entrega_estimada:%d/%m/%Y}).', pedido=pedido)
        vivas.add(alerta.pk)

    _cerrar(Alerta.objects.filter(resuelta=False, tipo__in=Alerta.AUTOMATICAS).exclude(pk__in=vivas))
