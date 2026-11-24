"""Reposición, consumo y solicitudes de carros clínicos (abastecen desde el inventario por FEFO)."""
from django.db import transaction
from django.utils import timezone

from alertas.models import Alerta
from alertas.services import _abrir, evaluar_carro
from inventario.models import MovimientoInventario, Ubicacion
from inventario.services import descontar_fefo, stock_disponible

from .models import (CarroItem, ConsumoCarro, ReposicionCarro, ReposicionDetalle, SolicitudDetalle,
                     SolicitudReposicion)

UBICACIONES_ORIGEN = (Ubicacion.BODEGA, Ubicacion.VITRINA)


def _abastecer(item, cantidad, usuario, referencia):
    """Saca hasta `cantidad` del inventario (FEFO). Devuelve (unidades_repuestas, vencimiento_mas_proximo)."""
    disponible = stock_disponible(item.producto, UBICACIONES_ORIGEN)
    cantidad = min(cantidad, disponible)
    if cantidad <= 0:
        return 0, None
    consumos = descontar_fefo(
        producto=item.producto, cantidad=cantidad, ubicaciones=UBICACIONES_ORIGEN, usuario=usuario,
        tipo=MovimientoInventario.Tipo.REPOSICION_CARRO, referencia=referencia)
    return cantidad, min(lote.fecha_vencimiento for lote, _u, _c in consumos)


def _actualizar_vencimiento(item, nuevo):
    if nuevo is None:
        return
    if item.fecha_vencimiento is None or item.cantidad_actual == 0 or nuevo < item.fecha_vencimiento:
        item.fecha_vencimiento = nuevo


@transaction.atomic
def reponer_carro(carro, conteo, usuario, observacion='', solicitud=None):
    """Reposición con conteo físico. `conteo` = {item_id: cantidad contada en el carro}.

    Registra la diferencia entre lo contado y lo que el sistema creía que había, y completa
    hasta la dotación requerida usando stock del inventario (FEFO).
    """
    reposicion = ReposicionCarro.objects.create(
        carro=carro, realizada_por=usuario, observacion=observacion, solicitud=solicitud)
    for item in CarroItem.objects.select_for_update().filter(carro=carro).select_related('producto'):
        contado = conteo.get(item.pk)
        contado = item.cantidad_actual if contado is None else contado
        diferencia = contado - item.cantidad_actual
        sistema = item.cantidad_actual
        item.cantidad_actual = contado
        if contado == 0:
            item.fecha_vencimiento = None
        repuesto = 0
        faltante = item.cantidad_requerida - contado
        if faltante > 0:
            repuesto, vencimiento = _abastecer(item, faltante, usuario, f'Reposición {carro.nombre} N° {reposicion.pk}')
            item.cantidad_actual += repuesto
            _actualizar_vencimiento(item, vencimiento)
        item.save(update_fields=['cantidad_actual', 'fecha_vencimiento'])
        ReposicionDetalle.objects.create(
            reposicion=reposicion, producto=item.producto, cantidad_sistema=sistema, cantidad_contada=contado,
            diferencia=diferencia, cantidad_repuesta=repuesto)
        if diferencia != 0:
            _abrir(Alerta.Tipo.DIFERENCIA_CARRO, Alerta.Severidad.MEDIA,
                   f'{carro.nombre}: diferencia de {diferencia:+d} en {item.producto.nombre} '
                   f'(contado {contado}, sistema {sistema}).', producto=item.producto, carro=carro)
    evaluar_carro(carro)
    return reposicion


@transaction.atomic
def registrar_consumo(carro, producto, cantidad, usuario, referencia='', observacion=''):
    item = CarroItem.objects.select_for_update().filter(carro=carro, producto=producto).first()
    if item is None:
        raise ValueError('El producto no pertenece a la dotación de este carro.')
    if cantidad > item.cantidad_actual:
        raise ValueError(f'El carro solo tiene {item.cantidad_actual} unidades de {producto.nombre}.')
    item.cantidad_actual -= cantidad
    if item.cantidad_actual == 0:
        item.fecha_vencimiento = None
    item.save(update_fields=['cantidad_actual', 'fecha_vencimiento'])
    consumo = ConsumoCarro.objects.create(
        carro=carro, producto=producto, cantidad=cantidad, registrado_por=usuario,
        referencia=referencia, observacion=observacion)
    evaluar_carro(carro)
    return consumo


@transaction.atomic
def crear_solicitud(carro, solicitante, cantidades, observacion=''):
    """`cantidades` = {producto_id: unidades solicitadas}. Solo se registran cantidades > 0."""
    detalles = {pid: c for pid, c in cantidades.items() if c and c > 0}
    if not detalles:
        raise ValueError('Indique al menos un producto a reponer.')
    solicitud = SolicitudReposicion.objects.create(carro=carro, solicitante=solicitante, observacion=observacion)
    for producto_id, cantidad in detalles.items():
        SolicitudDetalle.objects.create(solicitud=solicitud, producto_id=producto_id, cantidad_solicitada=cantidad)
    return solicitud


@transaction.atomic
def atender_solicitud(solicitud, usuario):
    """Entrega lo solicitado (sin exceder la dotación ni el stock) y actualiza inventario y carro."""
    if solicitud.estado != SolicitudReposicion.Estado.PENDIENTE:
        raise ValueError('La solicitud ya fue procesada.')
    reposicion = ReposicionCarro.objects.create(
        carro=solicitud.carro, realizada_por=usuario, solicitud=solicitud,
        observacion=f'Atención de solicitud N° {solicitud.pk}')
    parcial = False
    for detalle in solicitud.detalles.select_related('producto'):
        item = CarroItem.objects.select_for_update().filter(carro=solicitud.carro, producto=detalle.producto).first()
        entregado = 0
        if item is not None:
            objetivo = min(detalle.cantidad_solicitada, item.faltante)
            entregado, vencimiento = _abastecer(item, objetivo, usuario, f'Solicitud N° {solicitud.pk}')
            if entregado:
                item.cantidad_actual += entregado
                _actualizar_vencimiento(item, vencimiento)
                item.save(update_fields=['cantidad_actual', 'fecha_vencimiento'])
            ReposicionDetalle.objects.create(
                reposicion=reposicion, producto=item.producto, cantidad_sistema=item.cantidad_actual - entregado,
                cantidad_contada=item.cantidad_actual - entregado, diferencia=0, cantidad_repuesta=entregado)
        detalle.cantidad_entregada = entregado
        detalle.save(update_fields=['cantidad_entregada'])
        if entregado < detalle.cantidad_solicitada:
            parcial = True
    solicitud.estado = SolicitudReposicion.Estado.PARCIAL if parcial else SolicitudReposicion.Estado.ATENDIDA
    solicitud.atendida_por = usuario
    solicitud.atendida_en = timezone.now()
    solicitud.save(update_fields=['estado', 'atendida_por', 'atendida_en'])
    evaluar_carro(solicitud.carro)
    return solicitud
