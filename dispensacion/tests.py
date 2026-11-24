from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Usuario
from alertas.models import Alerta
from core import roles
from dispensacion.models import Dispensacion, Receta, RecetaItem
from dispensacion.services import DispensacionError, dispensar
from inventario.models import Categoria, MovimientoInventario, Producto, Ubicacion
from inventario.services import descontar_fefo, ingresar_lote, stock_disponible
from pacientes.models import CuotaPrograma, InscripcionPrograma, Paciente, Programa

HOY = timezone.localdate()


class BaseTest(TestCase):
    def setUp(self):
        self.tecnico = Usuario.objects.create_user(
            username='tec', password='x', rut='12345678-5', rol=roles.TECNICO)
        self.quimico = Usuario.objects.create_user(
            username='qf', password='x', rut='11111111-1', rol=roles.QUIMICO)
        cat = Categoria.objects.create(nombre='General')
        self.producto = Producto.objects.create(codigo='P1', nombre='Losartán', categoria=cat, stock_minimo=10)
        self.paciente = Paciente.objects.create(
            documento='13456789-9', nombres='Juan', apellidos='Pérez', prevision=Paciente.Prevision.FONASA_A)

    def lote(self, numero, dias, cantidad, ubicacion=Ubicacion.VITRINA, producto=None):
        return ingresar_lote(
            producto=producto or self.producto, numero_lote=numero, fecha_vencimiento=HOY + timedelta(days=dias),
            cantidad=cantidad, ubicacion=ubicacion, usuario=self.tecnico)

    def receta(self, cantidad=100, programa=None, modalidad=Receta.Modalidad.ESTANDAR, producto=None):
        receta = Receta.objects.create(
            paciente=self.paciente, numero='R1', programa=programa, modalidad=modalidad,
            medico_nombre='Dr. X', medico_rut='11111111-1', fecha_emision=HOY, registrada_por=self.tecnico)
        item = RecetaItem.objects.create(receta=receta, producto=producto or self.producto,
                                         cantidad_prescrita=cantidad)
        return receta, item


class FefoTests(BaseTest):
    def test_sale_primero_el_lote_que_vence_antes(self):
        self.lote('B', 120, 50)
        self.lote('A', 60, 20)
        consumos = descontar_fefo(
            producto=self.producto, cantidad=30, ubicaciones=(Ubicacion.VITRINA,), usuario=self.tecnico,
            tipo=MovimientoInventario.Tipo.DISPENSACION)
        self.assertEqual([(l.numero_lote, c) for l, _u, c in consumos], [('A', 20), ('B', 10)])

    def test_no_usa_lotes_vencidos(self):
        self.lote('VENC', -5, 100)
        self.assertEqual(stock_disponible(self.producto), 0)


class DispensacionTests(BaseTest):
    def test_dispensa_y_descuenta_stock(self):
        self.lote('A', 90, 100)
        receta, item = self.receta(40)
        d = dispensar(receta=receta, cantidades={item.pk: 25}, usuario=self.tecnico)
        self.assertEqual(d.items.first().cantidad, 25)
        self.assertEqual(stock_disponible(self.producto), 75)
        self.assertEqual(item.saldo, 15)

    def test_no_permite_exceder_saldo_de_receta(self):
        self.lote('A', 90, 100)
        receta, item = self.receta(10)
        with self.assertRaises(DispensacionError):
            dispensar(receta=receta, cantidades={item.pk: 11}, usuario=self.tecnico)

    def test_cuota_mensual_del_programa(self):
        self.lote('A', 90, 100)
        programa = Programa.objects.create(nombre='HTA', tipo=Programa.Tipo.GES)
        ins = InscripcionPrograma.objects.create(paciente=self.paciente, programa=programa)
        CuotaPrograma.objects.create(inscripcion=ins, producto=self.producto, cantidad_mensual=30)
        receta, item = self.receta(100, programa=programa)
        dispensar(receta=receta, cantidades={item.pk: 30}, usuario=self.tecnico)
        with self.assertRaises(DispensacionError):
            dispensar(receta=receta, cantidades={item.pk: 1}, usuario=self.tecnico)

    def test_excepcion_de_cuota_solo_quimico(self):
        self.lote('A', 90, 100)
        programa = Programa.objects.create(nombre='HTA', tipo=Programa.Tipo.GES)
        ins = InscripcionPrograma.objects.create(paciente=self.paciente, programa=programa)
        CuotaPrograma.objects.create(inscripcion=ins, producto=self.producto, cantidad_mensual=10)
        receta, item = self.receta(100, programa=programa)
        with self.assertRaises(DispensacionError):
            dispensar(receta=receta, cantidades={item.pk: 20}, usuario=self.tecnico, excepcion_cuota=True)
        d = dispensar(receta=receta, cantidades={item.pk: 20}, usuario=self.quimico, excepcion_cuota=True)
        self.assertTrue(d.excepcion_cuota)

    def test_stock_insuficiente_no_deja_registros_a_medias(self):
        self.lote('A', 90, 5)
        receta, item = self.receta(50)
        with self.assertRaises(DispensacionError):
            dispensar(receta=receta, cantidades={item.pk: 20}, usuario=self.tecnico)
        self.assertEqual(Dispensacion.objects.count(), 0)
        self.assertEqual(stock_disponible(self.producto), 5)

    def test_paciente_sin_prevision_publica_no_recibe_gratis(self):
        self.lote('A', 90, 50)
        self.paciente.prevision = Paciente.Prevision.ISAPRE
        self.paciente.save()
        receta, item = self.receta(10)
        with self.assertRaises(DispensacionError):
            dispensar(receta=receta, cantidades={item.pk: 5}, usuario=self.tecnico)

    def test_controlado_exige_receta_retenida_y_queda_en_libro(self):
        controlado = Producto.objects.create(
            codigo='C1', nombre='Clonazepam', categoria=self.producto.categoria,
            control=Producto.Control.PSICOTROPICO, stock_minimo=5)
        self.lote('C', 90, 50, producto=controlado)
        receta, item = self.receta(10, producto=controlado)  # receta estándar
        with self.assertRaises(DispensacionError):
            dispensar(receta=receta, cantidades={item.pk: 5}, usuario=self.tecnico)
        receta.modalidad = Receta.Modalidad.RETENIDA
        receta.save()
        dispensar(receta=receta, cantidades={item.pk: 5}, usuario=self.tecnico)
        ultimo = controlado.libro.order_by('-id').first()
        self.assertEqual(ultimo.tipo, 'EGRESO')
        self.assertEqual(ultimo.saldo_resultante, 45)
        self.assertFalse(ultimo.firmado)


class AlertasTests(BaseTest):
    def test_alerta_de_stock_critico_al_bajar_del_minimo(self):
        self.lote('A', 90, 12)
        receta, item = self.receta(10)
        dispensar(receta=receta, cantidades={item.pk: 5}, usuario=self.tecnico)  # quedan 7 <= 10
        self.assertTrue(Alerta.objects.filter(tipo=Alerta.Tipo.STOCK_CRITICO, resuelta=False).exists())


class PermisosTests(BaseTest):
    def test_tecnico_no_accede_a_usuarios(self):
        self.client.login(username='tec', password='x')
        self.assertEqual(self.client.get(reverse('accounts:usuario_lista')).status_code, 403)

    def test_anonimo_es_redirigido_al_login(self):
        respuesta = self.client.get(reverse('inventario:stock'))
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn('/cuentas/ingresar/', respuesta['Location'])

    def test_tecnico_ve_stock(self):
        self.client.login(username='tec', password='x')
        self.assertEqual(self.client.get(reverse('inventario:stock')).status_code, 200)
