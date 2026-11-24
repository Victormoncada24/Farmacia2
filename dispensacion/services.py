"""Dispensación: valida receta, cobertura, cuotas y stock; descuenta por FEFO desde vitrina."""
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from inventario.models import MovimientoInventario, Producto, Ubicacion
from inventario.services import StockInsuficiente, descontar_fefo, stock_disponible
from pacientes.models import CuotaPrograma, InscripcionPrograma

from .models import Dispensacion, DispensacionItem, Receta, RecetaItem


class DispensacionError(Exception):
    """Regla de negocio incumplida; el mensaje se muestra al usuario."""


@transaction.atomic
def dispensar(*, receta, cantidades, usuario, retira_tercero=False, retiro_nombre='', retiro_rut='',
              retiro_parentesco='', observacion='', excepcion_cuota=False):
    """Registra una dispensación. `cantidades` = {receta_item_id: unidades a entregar}."""
    receta = Receta.objects.select_for_update(of=('self',)).select_related('paciente', 'programa').get(pk=receta.pk)
    paciente = receta.paciente

    # 1) Validaciones de la receta y del paciente
    if not receta.dispensable:
        raise DispensacionError(f'La receta no se puede dispensar: está {receta.estado_texto.lower()}.')
    if not paciente.activo:
        raise DispensacionError('El paciente está inactivo.')

    # 2) Cobertura (dispensación sin costo en la red pública)
    inscripcion = None
    if receta.programa_id:
        inscripcion = InscripcionPrograma.objects.filter(
            paciente=paciente, programa=receta.programa, activo=True).first()
        if inscripcion is None:
            raise DispensacionError(
                f'El paciente no tiene inscripción vigente en el programa «{receta.programa.nombre}».')
    elif not paciente.tiene_cobertura_publica:
        raise DispensacionError('El paciente no cuenta con previsión pública (FONASA) para dispensación gratuita.')

    lineas = [(item, int(cantidades.get(item.pk) or 0)) for item in receta.items.select_related('producto')]
    lineas = [(item, cantidad) for item, cantidad in lineas if cantidad > 0]
    if not lineas:
        raise DispensacionError('Indique al menos un medicamento a entregar.')

    if excepcion_cuota and not usuario.puede('autorizar'):
        raise DispensacionError('Solo el Químico Farmacéutico puede autorizar excepciones de cuota.')

    # 3) Validaciones por línea
    for item, cantidad in lineas:
        producto = item.producto
        if receta.control_saldo and cantidad > item.saldo:
            raise DispensacionError(
                f'{producto.nombre}: se intenta entregar {cantidad} pero el saldo de la receta es {item.saldo}.')
        if producto.es_controlado and receta.modalidad != Receta.Modalidad.RETENIDA:
            raise DispensacionError(
                f'{producto.nombre} es un medicamento controlado: requiere receta RETENIDA.')
        if inscripcion is not None:
            cuota = CuotaPrograma.objects.filter(inscripcion=inscripcion, producto=producto).first()
            if cuota is None:
                if not excepcion_cuota:
                    raise DispensacionError(
                        f'{producto.nombre} no está cubierto por el programa «{receta.programa.nombre}».')
            else:
                entregado = cuota.entregado_mes()
                if entregado + cantidad > cuota.cantidad_mensual and not excepcion_cuota:
                    raise DispensacionError(
                        f'{producto.nombre}: excede la cuota mensual ({entregado} entregadas de '
                        f'{cuota.cantidad_mensual}; quedan {max(cuota.cantidad_mensual - entregado, 0)}).')

    # 4) Registro y descuento de stock (FEFO, solo vitrina)
    dispensacion = Dispensacion.objects.create(
        receta=receta, paciente=paciente, programa=receta.programa, dispensado_por=usuario,
        retira_tercero=retira_tercero, retiro_nombre=retiro_nombre if retira_tercero else '',
        retiro_rut=retiro_rut if retira_tercero else '',
        retiro_parentesco=retiro_parentesco if retira_tercero else '',
        observacion=observacion, excepcion_cuota=excepcion_cuota,
        autorizado_por=usuario if excepcion_cuota else None)
    for item, cantidad in lineas:
        try:
            consumos = descontar_fefo(
                producto=item.producto, cantidad=cantidad, ubicaciones=(Ubicacion.VITRINA,), usuario=usuario,
                tipo=MovimientoInventario.Tipo.DISPENSACION, referencia=f'Dispensación N° {dispensacion.pk}',
                paciente_documento=paciente.documento)
        except StockInsuficiente as error:
            en_bodega = stock_disponible(item.producto, (Ubicacion.BODEGA,))
            sugerencia = (f' Hay {en_bodega} en bodega: transfiéralas a vitrina.' if en_bodega else '')
            raise DispensacionError(
                f'{item.producto.nombre}: stock insuficiente en vitrina (disponible {error.disponible}, '
                f'requerido {cantidad}).{sugerencia}')
        for lote, _ubicacion, tomado in consumos:
            DispensacionItem.objects.create(
                dispensacion=dispensacion, receta_item=item, producto=item.producto, lote=lote, cantidad=tomado)
    return dispensacion


@transaction.atomic
def anular_receta(receta, usuario, motivo):
    receta.estado = Receta.Estado.ANULADA
    receta.motivo_anulacion = motivo
    receta.save(update_fields=['estado', 'motivo_anulacion'])
