from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase

from core.utils import calcular_dv, formatear_rut, normalizar_rut, validar_rut
from pacientes.models import Paciente


class RutTests(TestCase):
    def test_digito_verificador(self):
        self.assertEqual(calcular_dv('12345678'), '5')
        self.assertEqual(calcular_dv('11111111'), '1')

    def test_normaliza_y_formatea(self):
        self.assertEqual(normalizar_rut('12.345.678-5'), '12345678-5')
        self.assertEqual(formatear_rut('12345678-5'), '12.345.678-5')

    def test_valida(self):
        validar_rut('12.345.678-5')
        with self.assertRaises(ValidationError):
            validar_rut('12.345.678-9')
        with self.assertRaises(ValidationError):
            validar_rut('abc')


class CifradoTests(TestCase):
    def test_datos_sensibles_se_guardan_cifrados(self):
        paciente = Paciente.objects.create(
            documento='12345678-5', nombres='Ana', apellidos='Prueba', telefono='+56911112222')
        with connection.cursor() as cursor:
            cursor.execute('SELECT telefono FROM pacientes_paciente WHERE id = %s', [paciente.pk])
            crudo = cursor.fetchone()[0]
        self.assertNotIn('56911112222', crudo)
        self.assertEqual(Paciente.objects.get(pk=paciente.pk).telefono, '+56911112222')
