"""Pruebas de la lógica analítica pura (no requieren base de datos)."""
import unittest
from datetime import date, timedelta

from analitica import calculos as c

HOY = date(2026, 9, 21)


def lote(i, dias, unidades):
    return c.LoteStock(id=i, numero=f'L{i}', vencimiento=HOY + timedelta(days=dias), unidades=unidades)


class CoberturaTests(unittest.TestCase):
    def test_consumo_y_cobertura(self):
        self.assertAlmostEqual(c.consumo_diario(300, 30), 10.0)
        self.assertAlmostEqual(c.dias_cobertura(250, 10.0), 25.0)
        self.assertIsNone(c.dias_cobertura(250, 0))
        self.assertEqual(c.consumo_diario(10, 0), 0.0)


class RiesgoVencimientoTests(unittest.TestCase):
    def test_sin_riesgo_si_el_consumo_alcanza(self):
        riesgo, vencidas, det = c.simular_riesgo_vencimiento([lote(1, 60, 500)], 10.0, HOY)
        self.assertEqual((riesgo, vencidas, det), (0, 0, []))

    def test_riesgo_parcial(self):
        riesgo, _, det = c.simular_riesgo_vencimiento([lote(1, 30, 400)], 5.0, HOY)
        self.assertEqual(riesgo, 250)
        self.assertEqual(det[0][1:], (250, 30))

    def test_sin_consumo_todo_lote_cercano_esta_en_riesgo(self):
        riesgo, _, _ = c.simular_riesgo_vencimiento([lote(1, 40, 100)], 0.0, HOY)
        self.assertEqual(riesgo, 100)

    def test_fefo_el_lote_anterior_absorbe_primero_la_demanda(self):
        riesgo, _, det = c.simular_riesgo_vencimiento([lote(2, 60, 300), lote(1, 20, 100)], 5.0, HOY)
        self.assertEqual(riesgo, 100)
        self.assertEqual([d[0].id for d in det], [2])

    def test_lote_vencido_se_informa_aparte(self):
        riesgo, vencidas, det = c.simular_riesgo_vencimiento([lote(1, -3, 40), lote(2, 90, 10)], 10.0, HOY)
        self.assertEqual((riesgo, vencidas), (0, 40))
        self.assertEqual(det, [])

    def test_lotes_fuera_del_horizonte_se_ignoran(self):
        riesgo, _, _ = c.simular_riesgo_vencimiento([lote(1, 400, 1000)], 0.0, HOY)
        self.assertEqual(riesgo, 0)

    def test_lotes_sin_unidades_no_cuentan(self):
        riesgo, _, _ = c.simular_riesgo_vencimiento([lote(1, 10, 0)], 0.0, HOY)
        self.assertEqual(riesgo, 0)


class PedidoTests(unittest.TestCase):
    def test_pedido_alcanza_objetivo(self):
        self.assertEqual(c.pedido_sugerido(100, 0, 2.0, 300, 60), 200)

    def test_pedido_usa_cobertura_si_es_mayor_al_objetivo(self):
        self.assertEqual(c.pedido_sugerido(50, 0, 10.0, 100, 60), 550)

    def test_pedido_descuenta_lo_que_se_perdera(self):
        self.assertEqual(c.pedido_sugerido(500, 200, 5.0, 300, 60), 0)
        self.assertEqual(c.pedido_sugerido(500, 300, 5.0, 300, 60), 100)

    def test_no_pide_negativos(self):
        self.assertEqual(c.pedido_sugerido(1000, 0, 1.0, 100, 60), 0)


class ClasificacionTests(unittest.TestCase):
    def test_semaforo(self):
        self.assertEqual(c.clasificar_abastecimiento(100, 0, None, 0, 15), 'SIN_CONSUMO')
        self.assertEqual(c.clasificar_abastecimiento(0, 5, 0, 0, 15), 'QUIEBRE')
        self.assertEqual(c.clasificar_abastecimiento(50, 5, 10, 0, 15), 'CRITICO')
        self.assertEqual(c.clasificar_abastecimiento(100, 5, 20, 0, 15), 'ATENCION')
        self.assertEqual(c.clasificar_abastecimiento(1000, 5, 200, 30, 15), 'ATENCION')
        self.assertEqual(c.clasificar_abastecimiento(1000, 5, 200, 0, 15), 'OPTIMO')

    def test_abc(self):
        abc = c.clasificar_abc({1: 800, 2: 120, 3: 50, 4: 20, 5: 10, 6: 0})
        self.assertEqual(abc[1], 'A')
        self.assertEqual(abc[2], 'B')
        self.assertEqual(abc[6], 'C')

    def test_abc_sin_consumo(self):
        self.assertEqual(c.clasificar_abc({1: 0, 2: 0}), {1: 'C', 2: 'C'})


class AdherenciaTests(unittest.TestCase):
    def test_cobertura_tratamiento(self):
        cuotas = {1: 30, 2: 60}
        self.assertAlmostEqual(c.cobertura_tratamiento(cuotas, {1: 90, 2: 180}), 1.0)
        self.assertAlmostEqual(c.cobertura_tratamiento(cuotas, {1: 45, 2: 90}), 0.5)
        self.assertAlmostEqual(c.cobertura_tratamiento(cuotas, {1: 500, 2: 0}), 90 / 270)
        self.assertIsNone(c.cobertura_tratamiento({}, {}))

    def test_clasificar_adherencia(self):
        k = dict(dias_inscrito=200)
        self.assertEqual(c.clasificar_adherencia(pendiente_mes=False, dias_sin_retiro=3, **k), 'AL_DIA')
        self.assertEqual(c.clasificar_adherencia(pendiente_mes=True, dias_sin_retiro=10, **k), 'PENDIENTE')
        self.assertEqual(c.clasificar_adherencia(pendiente_mes=True, dias_sin_retiro=40, **k), 'ATRASADO')
        self.assertEqual(c.clasificar_adherencia(pendiente_mes=True, dias_sin_retiro=75, **k), 'ABANDONO')

    def test_paciente_nuevo_sin_retiros(self):
        self.assertEqual(c.clasificar_adherencia(pendiente_mes=True, dias_sin_retiro=None, dias_inscrito=5), 'PENDIENTE')
        self.assertEqual(c.clasificar_adherencia(pendiente_mes=True, dias_sin_retiro=None, dias_inscrito=90), 'ABANDONO')


if __name__ == '__main__':
    unittest.main()
