"""Reglas puras del ciclo de vida de un pedido a proveedor (sin Django, fáciles de probar).

Flujo:  BORRADOR → ENVIADO → PARCIAL → RECIBIDO
                 ↘ ANULADO        ↘ CERRADO (cierre con faltantes)
"""
from datetime import timedelta

ESTADOS_ABIERTOS = ('ENVIADO', 'PARCIAL')

TRANSICIONES = {
    'BORRADOR': {'ENVIADO', 'ANULADO'},
    'ENVIADO': {'PARCIAL', 'RECIBIDO', 'ANULADO'},
    'PARCIAL': {'PARCIAL', 'RECIBIDO', 'CERRADO'},   # con mercadería recibida ya no se anula: se cierra
    'RECIBIDO': set(),
    'CERRADO': set(),
    'ANULADO': set(),
}


def puede_transitar(origen, destino):
    return destino in TRANSICIONES.get(origen, set())


def numero_pedido(anio, pk):
    return f'PED-{anio}-{pk:05d}'


def estado_segun_recepcion(items):
    """Estado de un pedido abierto según lo recibido. `items` = [(pedida, recibida), ...]."""
    items = list(items)
    if not items:
        return 'ENVIADO'
    if all(recibida >= pedida for pedida, recibida in items):
        return 'RECIBIDO'
    if any(recibida > 0 for _pedida, recibida in items):
        return 'PARCIAL'
    return 'ENVIADO'


def validar_linea_recepcion(pendiente, cantidad):
    """Mensaje de error si la cantidad recibida no es válida; None si es correcta."""
    if cantidad <= 0:
        return 'La cantidad debe ser mayor que cero.'
    if cantidad > pendiente:
        return f'Excede lo pendiente del pedido ({pendiente}).'
    return None


def porcentaje_recibido(items):
    """% recibido del total pedido (la recepción en exceso no cuenta). `items` = [(pedida, recibida)]."""
    items = list(items)
    total = sum(pedida for pedida, _ in items)
    if total <= 0:
        return 0
    return round(100 * sum(min(recibida, pedida) for pedida, recibida in items) / total)


def fecha_entrega_estimada(fecha_envio, plazo_dias):
    return fecha_envio + timedelta(days=plazo_dias)


def dias_atraso(estado, fecha_estimada, hoy):
    """Días de atraso de un pedido abierto; 0 si no aplica o no está atrasado."""
    if estado not in ESTADOS_ABIERTOS or fecha_estimada is None:
        return 0
    return max((hoy - fecha_estimada).days, 0)
