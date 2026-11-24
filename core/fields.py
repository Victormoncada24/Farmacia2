"""Campos de modelo personalizados: RUT y texto cifrado (Fernet / AES-128-CBC + HMAC)."""
from cryptography.fernet import Fernet, InvalidToken
from django import forms
from django.conf import settings
from django.db import models

from .utils import normalizar_rut, validar_rut


class RutField(models.CharField):
    """RUT chileno validado (módulo 11) y almacenado normalizado: 12345678-5."""
    default_validators = [validar_rut]

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 12)
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        value = super().to_python(value)
        if value:
            return normalizar_rut(value)
        return value

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value:
            return normalizar_rut(value)
        return value


def _fernet():
    clave = settings.FIELD_ENCRYPTION_KEY
    return Fernet(clave.encode() if isinstance(clave, str) else clave)


class EncryptedTextField(models.TextField):
    """Texto cifrado en la base de datos. NO permite búsquedas por su contenido."""

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value in (None, ''):
            return value
        return _fernet().encrypt(str(value).encode('utf-8')).decode('ascii')

    def from_db_value(self, value, expression, connection):
        if value in (None, ''):
            return value
        try:
            return _fernet().decrypt(value.encode('ascii')).decode('utf-8')
        except (InvalidToken, ValueError):
            return value


class EncryptedCharField(EncryptedTextField):
    """Igual que EncryptedTextField pero se edita con un <input> de una línea."""

    def formfield(self, **kwargs):
        kwargs.setdefault('widget', forms.TextInput)
        return super().formfield(**kwargs)
