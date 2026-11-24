"""Validadores de archivos subidos (no se permite "cualquier cosa")."""
import os

from django.core.exceptions import ValidationError

EXTENSIONES_PERMITIDAS = {'pdf', 'jpg', 'jpeg', 'png'}
TAMANO_MAXIMO = 5 * 1024 * 1024  # 5 MB
FIRMAS = {
    'pdf': (b'%PDF',),
    'jpg': (b'\xff\xd8\xff',),
    'jpeg': (b'\xff\xd8\xff',),
    'png': (b'\x89PNG\r\n\x1a\n',),
}


def validar_archivo_receta(archivo):
    """Valida extensión, tamaño y contenido real (firma binaria) del archivo."""
    extension = os.path.splitext(archivo.name)[1].lower().lstrip('.')
    if extension not in EXTENSIONES_PERMITIDAS:
        raise ValidationError('Solo se permiten archivos PDF, JPG o PNG.', code='extension')
    if archivo.size > TAMANO_MAXIMO:
        raise ValidationError('El archivo supera el tamaño máximo de 5 MB.', code='tamano')
    archivo.seek(0)
    cabecera = archivo.read(8)
    archivo.seek(0)
    if not any(cabecera.startswith(firma) for firma in FIRMAS[extension]):
        raise ValidationError('El contenido del archivo no corresponde a su extensión.', code='contenido')
