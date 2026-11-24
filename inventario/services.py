"""Lógica de inventario: ingresos, transferencias, FEFO, ajustes.

Todas las operaciones son atómicas: si algo falla, no se modifica el stock.
"""
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import Lote, MovimientoInventario, Producto, StockLote, Ubicacion

T = MovimientoInventario.Tipo


class StockInsuficiente(Exception):
    def __init__(self, producto, solicitado, disponible):
        self.producto = producto
        self.solicitado = solicitado
        self.disponible = disponible
        super().__init__(
            f'Stock insuficiente de {producto.nombre}: se requieren {solicitado} y hay {disponible} disponibles.'
        )


# --------------------------------------------------------------------------
# Consultas
# --------------------------------------------------------------------------
def stock_disponible(producto, ubicaciones=(Ubicacion.BODEGA, Ubicacion.VITRINA)):
    """Unidades utilizables (lotes activos y NO vencidos) en las ubicaciones indicadas."""
    return StockLote.objects.filter(
        lote__producto=producto, lote__activo=True,
        lote__fecha_vencimiento__gte=timezone.localdate(), ubicacion__in=ubicaciones,
    ).aggregate(t=Sum('cantidad'))['t'] or 0


def stock_fisico_total(producto):
    """Todas las unidades físicas del producto (incluye lotes vencidos)."""
    return StockLote.objects.filter(lote__producto=producto).aggregate(t=Sum('cantidad'))['t'] or 0


# --------------------------------------------------------------------------
# Integraciones posteriores al movimiento (libro de controlados y alertas)
# --------------------------------------------------------------------------
_TIPO_LIBRO = {
    T.INGRESO: 'INGRESO',
    T.DISPENSACION: 'EGRESO',
    T.REPOSICION_CARRO: 'EGRESO',
    T.AJUSTE_POSITIVO: 'AJUSTE_POSITIVO',
    T.AJUSTE_NEGATIVO: 'AJUSTE_NEGATIVO',
    T.MERMA: 'MERMA',
    T.BAJA_VENCIDO: 'MERMA',
}


def _libro(producto, tipo, cantidad, usuario, lote, referencia, observacion, paciente_doc=''):
    if not producto.es_controlado or tipo not in _TIPO_LIBRO:
        return
    from controlados.services import registrar_libro
    registrar_libro(
        producto=producto, tipo=_TIPO_LIBRO[tipo], cantidad=cantidad, usuario=usuario, lote=lote,
        referencia=referencia, observacion=observacion, paciente_documento=paciente_doc,
    )


def _alertas(producto):
    from alertas.services import evaluar_stock
    evaluar_stock(producto)


def _crear_movimiento(*, lote, tipo, cantidad, usuario, origen='', destino='', referencia='', observacion=''):
    return MovimientoInventario.objects.create(
        producto=lote.producto, lote=lote, tipo=tipo, cantidad=cantidad, usuario=usuario,
        ubicacion_origen=origen, ubicacion_destino=destino, referencia=referencia, observacion=observacion,
    )


# --------------------------------------------------------------------------
# Operaciones
# --------------------------------------------------------------------------
@transaction.atomic
def ingresar_lote(*, producto, numero_lote, fecha_vencimiento, cantidad, ubicacion, usuario,
                  origen=Lote.Origen.CENABAST, documento_ref='', observacion=''):
    """Recepción de mercadería (p. ej. remesa CENABAST): crea el lote y suma stock."""
    lote, creado = Lote.objects.get_or_create(
        producto=producto, numero_lote=numero_lote,
        defaults={'fecha_vencimiento': fecha_vencimiento, 'origen': origen, 'documento_ref': documento_ref},
    )
    if not creado and lote.fecha_vencimiento != fecha_vencimiento:
        raise ValueError(
            f'El lote {numero_lote} ya existe con vencimiento {lote.fecha_vencimiento:%d/%m/%Y}. '
            'Verifique la fecha ingresada.'
        )
    stock, _ = StockLote.objects.select_for_update().get_or_create(lote=lote, ubicacion=ubicacion)
    stock.cantidad += cantidad
    stock.save(update_fields=['cantidad'])
    ref = documento_ref or 'Ingreso de lote'
    _crear_movimiento(lote=lote, tipo=T.INGRESO, cantidad=cantidad, usuario=usuario,
                      destino=ubicacion, referencia=ref, observacion=observacion)
    _libro(producto, T.INGRESO, cantidad, usuario, lote, ref, observacion)
    _alertas(producto)
    return lote


@transaction.atomic
def transferir(*, lote, origen, destino, cantidad, usuario, observacion=''):
    """Mueve unidades de un lote entre bodega y vitrina."""
    if origen == destino:
        raise ValueError('El origen y el destino deben ser distintos.')
    stock_origen = StockLote.objects.select_for_update().filter(lote=lote, ubicacion=origen).first()
    if stock_origen is None or stock_origen.cantidad < cantidad:
        disponible = stock_origen.cantidad if stock_origen else 0
        raise ValueError(f'Solo hay {disponible} unidades del lote en {Ubicacion(origen).label}.')
    stock_destino, _ = StockLote.objects.select_for_update().get_or_create(lote=lote, ubicacion=destino)
    stock_origen.cantidad -= cantidad
    stock_origen.save(update_fields=['cantidad'])
    stock_destino.cantidad += cantidad
    stock_destino.save(update_fields=['cantidad'])
    _crear_movimiento(lote=lote, tipo=T.TRANSFERENCIA, cantidad=cantidad, usuario=usuario,
                      origen=origen, destino=destino, observacion=observacion,
                      referencia=f'{Ubicacion(origen).label} → {Ubicacion(destino).label}')
    _alertas(lote.producto)


@transaction.atomic
def descontar_fefo(*, producto, cantidad, ubicaciones, usuario, tipo, referencia='',
                   observacion='', paciente_documento=''):
    """Descuenta `cantidad` aplicando FEFO (First Expired, First Out).

    Solo considera lotes activos y NO vencidos. Devuelve [(lote, ubicacion, cantidad), ...].
    Lanza StockInsuficiente (y no modifica nada) si no alcanza.
    """
    hoy = timezone.localdate()
    stocks = list(
        StockLote.objects.select_for_update().select_related('lote').filter(
            lote__producto=producto, lote__activo=True, lote__fecha_vencimiento__gte=hoy,
            ubicacion__in=ubicaciones, cantidad__gt=0,
        ).order_by('lote__fecha_vencimiento', 'lote_id', 'ubicacion')
    )
    disponible = sum(s.cantidad for s in stocks)
    if disponible < cantidad:
        raise StockInsuficiente(producto, cantidad, disponible)

    restante = cantidad
    consumos = []
    for stock in stocks:
        if restante == 0:
            break
        tomar = min(stock.cantidad, restante)
        stock.cantidad -= tomar
        stock.save(update_fields=['cantidad'])
        _crear_movimiento(lote=stock.lote, tipo=tipo, cantidad=tomar, usuario=usuario,
                          origen=stock.ubicacion, referencia=referencia, observacion=observacion)
        _libro(producto, tipo, tomar, usuario, stock.lote, referencia, observacion, paciente_documento)
        consumos.append((stock.lote, stock.ubicacion, tomar))
        restante -= tomar
    _alertas(producto)
    return consumos


@transaction.atomic
def ajustar_stock(*, lote, ubicacion, tipo, cantidad, usuario, motivo):
    """Ajustes, mermas y bajas por vencimiento (requiere autorización del Químico Farmacéutico)."""
    if tipo not in (T.AJUSTE_POSITIVO, T.AJUSTE_NEGATIVO, T.MERMA, T.BAJA_VENCIDO):
        raise ValueError('Tipo de ajuste no válido.')
    stock, _ = StockLote.objects.select_for_update().get_or_create(lote=lote, ubicacion=ubicacion)
    if tipo == T.AJUSTE_POSITIVO:
        stock.cantidad += cantidad
        origen, destino = '', ubicacion
    else:
        if stock.cantidad < cantidad:
            raise ValueError(f'Solo hay {stock.cantidad} unidades del lote en {Ubicacion(ubicacion).label}.')
        stock.cantidad -= cantidad
        origen, destino = ubicacion, ''
    stock.save(update_fields=['cantidad'])
    _crear_movimiento(lote=lote, tipo=tipo, cantidad=cantidad, usuario=usuario, origen=origen,
                      destino=destino, referencia='Ajuste autorizado', observacion=motivo)
    _libro(lote.producto, tipo, cantidad, usuario, lote, 'Ajuste autorizado', motivo)
    _alertas(lote.producto)
