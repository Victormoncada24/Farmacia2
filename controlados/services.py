"""Libro digital de controlados: asientos correlativos con saldo, firmas y cuadratura."""
from django.db import transaction
from django.utils import timezone

from inventario.models import Producto
from inventario.services import stock_fisico_total

from .models import ConteoFisico, MovimientoControlado

Tipo = MovimientoControlado.Tipo


def saldo_libro(producto):
    ultimo = MovimientoControlado.objects.filter(producto=producto).order_by('-id').first()
    return ultimo.saldo_resultante if ultimo else 0


@transaction.atomic
def registrar_libro(*, producto, tipo, cantidad, usuario, lote=None, referencia='', observacion='',
                    paciente_documento=''):
    """Crea un asiento en el libro. Se invoca automáticamente desde los movimientos de inventario.

    Si es el primer asiento del producto y ya existía stock físico, se registra antes un
    'Saldo inicial' para que el libro parta cuadrado con el sistema.
    """
    Producto.objects.select_for_update().get(pk=producto.pk)  # serializa asientos del mismo producto
    ultimo = MovimientoControlado.objects.filter(producto=producto).order_by('-id').first()
    positivo = tipo in MovimientoControlado.POSITIVOS
    if ultimo is None:
        # El stock físico ya incluye este movimiento (se llama después de actualizarlo).
        previo = stock_fisico_total(producto) - (cantidad if positivo else -cantidad)
        saldo = 0
        if previo > 0:
            saldo = previo
            MovimientoControlado.objects.create(
                producto=producto, tipo=Tipo.SALDO_INICIAL, cantidad=previo, saldo_resultante=previo,
                referencia='Saldo previo a la digitalización del libro', registrado_por=usuario)
    else:
        saldo = ultimo.saldo_resultante
    saldo += cantidad if positivo else -cantidad
    return MovimientoControlado.objects.create(
        producto=producto, lote=lote, tipo=tipo, cantidad=cantidad, saldo_resultante=saldo,
        referencia=referencia, paciente_documento=paciente_documento, observacion=observacion,
        registrado_por=usuario)


def firmar(movimiento, usuario):
    if movimiento.firmado:
        return False
    movimiento.firmado_por = usuario
    movimiento.firmado_en = timezone.now()
    movimiento.save(update_fields=['firmado_por', 'firmado_en'])
    return True


@transaction.atomic
def registrar_conteo(*, producto, cantidad_contada, usuario, observacion=''):
    """Registra un conteo físico; si difiere del libro genera una alerta de descuadre."""
    from alertas.models import Alerta
    from alertas.services import _abrir

    libro = saldo_libro(producto)
    conteo = ConteoFisico.objects.create(
        producto=producto, cantidad_contada=cantidad_contada, saldo_libro=libro,
        stock_sistema=stock_fisico_total(producto), diferencia=cantidad_contada - libro,
        observacion=observacion, registrado_por=usuario)
    if conteo.diferencia != 0:
        _abrir(Alerta.Tipo.DESCUADRE_CONTEO, Alerta.Severidad.ALTA,
               f'{producto.nombre}: el conteo físico ({cantidad_contada}) difiere del libro ({libro}) en '
               f'{conteo.diferencia:+d}. Requiere regularización por el Químico Farmacéutico.',
               producto=producto)
    return conteo


@transaction.atomic
def resolver_conteo(conteo, usuario, nota):
    from alertas.models import Alerta

    conteo.resuelto = True
    conteo.resuelto_por = usuario
    conteo.resuelto_en = timezone.now()
    conteo.nota_resolucion = nota
    conteo.save(update_fields=['resuelto', 'resuelto_por', 'resuelto_en', 'nota_resolucion'])
    pendientes = ConteoFisico.objects.filter(producto=conteo.producto, resuelto=False).exclude(diferencia=0)
    if not pendientes.exists():
        Alerta.objects.filter(resuelta=False, tipo=Alerta.Tipo.DESCUADRE_CONTEO, producto=conteo.producto).update(
            resuelta=True, resuelta_en=timezone.now(), resuelta_por=usuario)
