"""Pruebas de las reglas puras de pedidos (no requieren base de datos)."""
import unittest
from datetime import date

from pedidos import logica as l


class EstadoTests(unittest.TestCase):
    def test_nada_recibido_sigue_enviado(self):
        self.assertEqual(l.estado_segun_recepcion([(100, 0), (50, 0)]), 'ENVIADO')

    def test_recepcion_parcial(self):
        self.assertEqual(l.estado_segun_recepcion([(100, 100), (50, 0)]), 'PARCIAL')
        self.assertEqual(l.estado_segun_recepcion([(100, 40), (50, 0)]), 'PARCIAL')

    def test_recepcion_completa(self):
        self.assertEqual(l.estado_segun_recepcion([(100, 100), (50, 50)]), 'RECIBIDO')

    def test_sin_items(self):
        self.assertEqual(l.estado_segun_recepcion([]), 'ENVIADO')


class TransicionTests(unittest.TestCase):
    def test_flujo_normal(self):
        self.assertTrue(l.puede_transitar('BORRADOR', 'ENVIADO'))
        self.assertTrue(l.puede_transitar('ENVIADO', 'PARCIAL'))
        self.assertTrue(l.puede_transitar('PARCIAL', 'RECIBIDO'))
        self.assertTrue(l.puede_transitar('PARCIAL', 'CERRADO'))

    def test_transiciones_prohibidas(self):
        self.assertFalse(l.puede_transitar('BORRADOR', 'RECIBIDO'))   # no se recibe lo que no se envió
        self.assertFalse(l.puede_transitar('PARCIAL', 'ANULADO'))     # ya hay mercadería: se cierra, no se anula
        for final in ('RECIBIDO', 'CERRADO', 'ANULADO'):
            for destino in ('BORRADOR', 'ENVIADO', 'PARCIAL', 'RECIBIDO', 'CERRADO', 'ANULADO'):
                self.assertFalse(l.puede_transitar(final, destino))


class RecepcionTests(unittest.TestCase):
    def test_validar_linea(self):
        self.assertIsNone(l.validar_linea_recepcion(100, 100))
        self.assertIsNone(l.validar_linea_recepcion(100, 1))
        self.assertIn('mayor que cero', l.validar_linea_recepcion(100, 0))
        self.assertIn('Excede', l.validar_linea_recepcion(100, 101))
        self.assertIn('(40)', l.validar_linea_recepcion(40, 50))

    def test_porcentaje(self):
        self.assertEqual(l.porcentaje_recibido([(100, 50), (100, 0)]), 25)
        self.assertEqual(l.porcentaje_recibido([(100, 100)]), 100)
        self.assertEqual(l.porcentaje_recibido([(100, 150)]), 100)   # el exceso no suma
        self.assertEqual(l.porcentaje_recibido([]), 0)


class PlazosTests(unittest.TestCase):
    def test_fecha_entrega(self):
        self.assertEqual(l.fecha_entrega_estimada(date(2026, 9, 1), 20), date(2026, 9, 21))

    def test_atraso_solo_en_pedidos_abiertos(self):
        hoy = date(2026, 9, 21)
        self.assertEqual(l.dias_atraso('ENVIADO', date(2026, 9, 11), hoy), 10)
        self.assertEqual(l.dias_atraso('PARCIAL', date(2026, 9, 20), hoy), 1)
        self.assertEqual(l.dias_atraso('ENVIADO', date(2026, 9, 30), hoy), 0)   # aún en plazo
        self.assertEqual(l.dias_atraso('RECIBIDO', date(2026, 9, 1), hoy), 0)
        self.assertEqual(l.dias_atraso('BORRADOR', None, hoy), 0)

    def test_numero(self):
        self.assertEqual(l.numero_pedido(2026, 7), 'PED-2026-00007')


if __name__ == '__main__':
    unittest.main()
