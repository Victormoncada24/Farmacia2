"""Utilidades generales: RUT chileno, IP del cliente."""
import re

from django.core.exceptions import ValidationError


def limpiar_rut(rut):
    return re.sub(r'[^0-9kK]', '', str(rut or '')).upper()


def calcular_dv(cuerpo):
    """Dígito verificador (módulo 11) para el cuerpo numérico de un RUT."""
    suma = 0
    multiplo = 2
    for digito in reversed(str(cuerpo)):
        suma += int(digito) * multiplo
        multiplo = 2 if multiplo == 7 else multiplo + 1
    resto = 11 - (suma % 11)
    if resto == 11:
        return '0'
    if resto == 10:
        return 'K'
    return str(resto)


def normalizar_rut(rut):
    """Devuelve el RUT como '12345678-5'. Si no tiene forma de RUT lo deja igual."""
    texto = str(rut or '').strip()
    if not re.fullmatch(r'[0-9.\s]*[0-9][\-\s]?[0-9kK]', texto):
        return texto.upper()
    limpio = limpiar_rut(texto)
    return f'{limpio[:-1]}-{limpio[-1]}'


def formatear_rut(rut):
    """12345678-5 -> 12.345.678-5"""
    normal = normalizar_rut(rut)
    if '-' not in normal:
        return normal
    cuerpo, dv = normal.split('-')
    if not cuerpo.isdigit():
        return normal
    return f'{int(cuerpo):,}'.replace(',', '.') + f'-{dv}'


def validar_rut(valor):
    limpio = limpiar_rut(valor)
    if not re.fullmatch(r'\d{6,8}[0-9K]', limpio):
        raise ValidationError('Ingrese un RUT válido (ej. 12.345.678-5).', code='rut_invalido')
    if calcular_dv(limpio[:-1]) != limpio[-1]:
        raise ValidationError('RUT inválido: el dígito verificador no corresponde.', code='rut_invalido')


def obtener_ip(request):
    """IP del cliente. Detrás de Nginx se usa X-Real-IP (Nginx lo sobrescribe, el cliente no puede falsearlo)."""
    if request is None:
        return None
    from django.conf import settings
    if getattr(settings, 'DETRAS_DE_PROXY', False):
        real = request.META.get('HTTP_X_REAL_IP')
        if real:
            return real.strip()
    return request.META.get('REMOTE_ADDR') or None
