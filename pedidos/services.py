"""Operaciones del ciclo de vida de un pedido a proveedor. Todas son atómicas (todo o nada)."""
from django.db import transaction
from django.utils import timezone

from analitica.services import analizar_abastecimiento
from inventario.services import ingresar_lote

from .logica import (estado_segun_recepcion, fecha_entrega_estimada, puede_transitar,
                     validar_linea_recepcion)
from .models import Pedido, PedidoItem, Recepcion, RecepcionItem

E = Pedido.Estado


class PedidoError(Exception):
    """Regla de negocio incumplida; el mensaje se muestra al usuario."""


def _bloquear(pedido):
    return Pedido.objects.select_for_update(of=('self',)).select_related('proveedor').get(pk=pedido.pk)


@transaction.atomic
def enviar_pedido(pedido, usuario):
    """Autoriza el borrador y lo deja enviado al proveedor (acción del Químico Farmacéutico)."""
    pedido = _bloquear(pedido)
    if not puede_transitar(pedido.estado, E.ENVIADO):
        raise PedidoError(f'Solo se puede enviar un pedido en borrador (estado actual: {pedido.estado_texto}).')
    if not pedido.proveedor.activo:
        raise PedidoError('El proveedor está inactivo. Cambie el proveedor o reactívelo.')
    if not pedido.items.exists():
        raise PedidoError('El pedido no tiene productos.')
    ahora = timezone.now()
    pedido.estado = E.ENVIADO
    pedido.fecha_envio = ahora
    pedido.aprobado_por = usuario
    pedido.fecha_entrega_estimada = fecha_entrega_estimada(timezone.localtime(ahora).date(),
                                                           pedido.proveedor.plazo_entrega_dias)
    pedido.save(update_fields=['estado', 'fecha_envio', 'aprobado_por', 'fecha_entrega_estimada'])
    return pedido


@transaction.atomic
def anular_pedido(pedido, usuario, motivo):
    pedido = _bloquear(pedido)
    if not puede_transitar(pedido.estado, E.ANULADO):
        raise PedidoError('Solo se puede anular un pedido en borrador o enviado sin recepciones. '
                          'Si ya llegó mercadería, ciérrelo con faltantes.')
    pedido.estado = E.ANULADO
    pedido.motivo_anulacion = motivo
    pedido.save(update_fields=['estado', 'motivo_anulacion'])
    return pedido


@transaction.atomic
def cerrar_pedido(pedido, usuario, motivo):
    """Da por terminado un pedido parcialmente recibido, sin esperar el saldo pendiente."""
    pedido = _bloquear(pedido)
    if not puede_transitar(pedido.estado, E.CERRADO):
        raise PedidoError('Solo se puede cerrar con faltantes un pedido recibido parcialmente.')
    pedido.estado = E.CERRADO
    pedido.motivo_cierre = motivo
    pedido.save(update_fields=['estado', 'motivo_cierre'])
    return pedido


@transaction.atomic
def recibir_pedido(*, pedido, lineas, usuario, ubicacion, documento_ref, observacion=''):
    """Recepciona mercadería contra un pedido y la ingresa al inventario (lote + vencimiento).

    `lineas` = [{'item_id', 'cantidad', 'numero_lote', 'vencimiento'}, ...]. Si algo falla no se
    modifica nada. Los productos controlados quedan además anotados en el libro digital.
    """
    pedido = _bloquear(pedido)
    if pedido.estado not in (E.ENVIADO, E.PARCIAL):
        raise PedidoError(f'El pedido no admite recepciones (estado: {pedido.estado_texto}).')
    if not lineas:
        raise PedidoError('Indique la cantidad recibida de al menos un producto.')
    items = {i.pk: i for i in PedidoItem.objects.select_for_update(of=('self',))
             .select_related('producto').filter(pedido=pedido)}

    recepcion = Recepcion.objects.create(pedido=pedido, recibido_por=usuario, documento_ref=documento_ref,
                                         ubicacion=ubicacion, observacion=observacion)
    for linea in lineas:
        item = items.get(linea['item_id'])
        if item is None:
            raise PedidoError('Una de las líneas no pertenece a este pedido.')
        error = validar_linea_recepcion(item.cantidad_pedida - item.cantidad_recibida, linea['cantidad'])
        if error:
            raise PedidoError(f'{item.producto.nombre}: {error}')
        try:
            lote = ingresar_lote(
                producto=item.producto, numero_lote=linea['numero_lote'], fecha_vencimiento=linea['vencimiento'],
                cantidad=linea['cantidad'], ubicacion=ubicacion, usuario=usuario,
                origen=pedido.proveedor.origen_lote, documento_ref=documento_ref or pedido.numero,
                observacion=f'Recepción del pedido {pedido.numero}')
        except ValueError as error:
            raise PedidoError(f'{item.producto.nombre}: {error}')
        item.cantidad_recibida += linea['cantidad']
        item.save(update_fields=['cantidad_recibida'])
        RecepcionItem.objects.create(recepcion=recepcion, pedido_item=item, producto=item.producto,
                                     lote=lote, cantidad=linea['cantidad'])

    pedido.estado = estado_segun_recepcion((i.cantidad_pedida, i.cantidad_recibida) for i in items.values())
    pedido.save(update_fields=['estado'])
    return recepcion


@transaction.atomic
def pedido_desde_sugerencia(*, proveedor, usuario, dias, lead_time, dias_objetivo, solo_criticos=False):
    """Crea un borrador con los productos que el análisis de abastecimiento recomienda pedir."""
    if not proveedor.activo:
        raise PedidoError('El proveedor está inactivo.')
    filas = [f for f in analizar_abastecimiento(dias, lead_time, dias_objetivo) if f.pedido > 0]
    if solo_criticos:
        filas = [f for f in filas if f.estado in ('QUIEBRE', 'CRITICO')]
    if not filas:
        raise PedidoError('No hay productos con pedido sugerido para los criterios elegidos.')
    pedido = Pedido.objects.create(
        proveedor=proveedor, creado_por=usuario, origen_sugerencia=True,
        prioridad=Pedido.Prioridad.URGENTE if any(f.estado == 'QUIEBRE' for f in filas) else Pedido.Prioridad.NORMAL,
        observacion=(f'Generado desde Abastecimiento inteligente (consumo de {dias} días, plazo de reposición '
                     f'{lead_time} días, cobertura objetivo {dias_objetivo} días). Revise las cantidades antes de enviar.'))
    PedidoItem.objects.bulk_create([PedidoItem(pedido=pedido, producto=f.producto, cantidad_pedida=f.pedido)
                                    for f in filas])
    return pedido
