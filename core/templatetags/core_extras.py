from datetime import date, datetime

from django import template
from django.utils.html import format_html
from django.utils import timezone

from core.utils import formatear_rut

register = template.Library()


@register.filter
def valor(objeto, ruta):
    """Obtiene un atributo (o ruta a.b.c, llamando métodos) y formatea fechas."""
    actual = objeto
    for parte in str(ruta).split('.'):
        if actual is None:
            return None
        actual = getattr(actual, parte, None)
        if callable(actual):
            actual = actual()
    if isinstance(actual, datetime):
        if timezone.is_aware(actual):
            actual = timezone.localtime(actual)
        return actual.strftime('%d/%m/%Y %H:%M')
    if isinstance(actual, date):
        return actual.strftime('%d/%m/%Y')
    return actual


@register.filter
def rut(valor_rut):
    return formatear_rut(valor_rut) if valor_rut else ''


@register.filter
def clave(diccionario, llave):
    try:
        return diccionario.get(llave)
    except AttributeError:
        return None


INSIGNIAS = {
    'Crítico': 'danger', 'Sin stock': 'dark', 'Normal': 'success', 'Vencido': 'danger',
    'Vence en < 30 días': 'danger', 'Próximo a vencer': 'warning', 'Vigente': 'success',
    'Firmado': 'success', 'Pendiente de firma': 'warning', 'Anulada': 'secondary', 'Vencida': 'secondary',
    'Agotada': 'secondary', 'Pendiente': 'warning', 'Atendida': 'success', 'Atendida parcialmente': 'info',
    'Rechazada': 'secondary', 'Alta': 'danger', 'Media': 'warning', 'Baja': 'info',
    'Paro': 'danger', 'Unidosis': 'primary', 'Quiebre': 'dark', 'Atención': 'warning', 'Óptimo': 'success',
    'Sin consumo': 'secondary', 'Al día': 'success', 'Atrasado': 'warning', 'Riesgo de abandono': 'danger',
    'Borrador': 'secondary', 'Enviado': 'primary', 'Recibido': 'success', 'Recibido parcial': 'info',
    'Cerrado con faltantes': 'warning', 'Anulado': 'secondary', 'Urgente': 'danger',
}


@register.filter
def insignia(valor_texto):
    """Muestra estados conocidos como insignias de color; el resto como texto."""
    if valor_texto is None or valor_texto == '':
        return '—'
    texto = str(valor_texto)
    color = INSIGNIAS.get(texto)
    if color:
        return format_html('<span class="badge text-bg-{}">{}</span>', color, texto)
    return texto


@register.filter
def celda(dato):
    """Formatea cualquier valor de una celda de reporte (fechas, booleanos, estados)."""
    if isinstance(dato, bool):
        return 'Sí' if dato else 'No'
    if isinstance(dato, datetime):
        if timezone.is_aware(dato):
            dato = timezone.localtime(dato)
        return dato.strftime('%d/%m/%Y %H:%M')
    if isinstance(dato, date):
        return dato.strftime('%d/%m/%Y')
    return insignia(dato)
