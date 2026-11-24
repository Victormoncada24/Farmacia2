from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Usuario
from alertas.models import Alerta
from alertas.services import sincronizar
from analitica.services import unidades_en_transito
from core import roles
from inventario.models import Categoria, Lote, Producto
from inventario.services import stock_disponible
from pedidos import services
from pedidos.models import Pedido, PedidoItem, Proveedor
from pedidos.services import PedidoError

HOY = timezone.localdate()


class PedidosBase(TestCase):
    def setUp(self):
        self.tecnico = Usuario.objects.create_user(
            username='tec', password='x', rut='12345678-5', rol=roles.TECNICO)
        self.quimico = Usuario.objects.create_user(
            username='qf', password='x', rut='11111111-1', rol=roles.QUIMICO)
        categoria = Categoria.objects.create(nombre='General')
        self.producto = Producto.objects.create(codigo='P1', nombre='Losartán', categoria=categoria, stock_minimo=10)
        self.proveedor = Proveedor.objects.create(
            nombre='CENABAST', tipo=Proveedor.Tipo.CENABAST, plazo_entrega_dias=10)
        self.pedido = Pedido.objects.create(proveedor=self.proveedor, creado_por=self.tecnico)
        self.item = PedidoItem.objects.create(pedido=self.pedido, producto=self.producto, cantidad_pedida=100)

    def linea(self, cantidad, lote='L1', dias=200):
        return {'item_id': self.item.pk, 'cantidad': cantidad, 'numero_lote': lote,
                'vencimiento': HOY + timedelta(days=dias)}

    def recibir(self, cantidad, lote='L1'):
        return services.recibir_pedido(
            pedido=self.pedido, lineas=[self.linea(cantidad, lote)], usuario=self.tecnico,
            ubicacion='BODEGA', documento_ref='GD-1')


class CicloDeVidaTests(PedidosBase):
    def test_numero_correlativo_se_genera(self):
        self.pedido.refresh_from_db()
        self.assertTrue(self.pedido.numero.startswith(f'PED-{HOY.year}-'))

    def test_enviar_fija_estado_y_fecha_estimada(self):
        pedido = services.enviar_pedido(self.pedido, self.quimico)
        self.assertEqual(pedido.estado, Pedido.Estado.ENVIADO)
        self.assertEqual(pedido.fecha_entrega_estimada, HOY + timedelta(days=10))
        self.assertEqual(pedido.aprobado_por, self.quimico)

    def test_no_se_envia_sin_productos(self):
        self.item.delete()
        with self.assertRaises(PedidoError):
            services.enviar_pedido(self.pedido, self.quimico)

    def test_no_se_recibe_un_borrador(self):
        with self.assertRaises(PedidoError):
            self.recibir(10)

    def test_recepcion_parcial_y_luego_total(self):
        services.enviar_pedido(self.pedido, self.quimico)
        self.recibir(40, 'L1')
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, Pedido.Estado.PARCIAL)
        self.assertEqual(stock_disponible(self.producto), 40)
        self.assertEqual(Lote.objects.get(numero_lote='L1').origen, Lote.Origen.CENABAST)
        self.recibir(60, 'L2')
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, Pedido.Estado.RECIBIDO)
        self.assertEqual(stock_disponible(self.producto), 100)

    def test_no_permite_recibir_mas_de_lo_pendiente(self):
        services.enviar_pedido(self.pedido, self.quimico)
        with self.assertRaises(PedidoError):
            self.recibir(101)
        self.assertEqual(stock_disponible(self.producto), 0)

    def test_con_mercaderia_recibida_se_cierra_pero_no_se_anula(self):
        services.enviar_pedido(self.pedido, self.quimico)
        self.recibir(40)
        with self.assertRaises(PedidoError):
            services.anular_pedido(self.pedido, self.quimico, 'error')
        services.cerrar_pedido(self.pedido, self.quimico, 'Proveedor no entregará el saldo')
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, Pedido.Estado.CERRADO)

    def test_un_pedido_enviado_sin_recepciones_se_puede_anular(self):
        services.enviar_pedido(self.pedido, self.quimico)
        services.anular_pedido(self.pedido, self.quimico, 'Pedido duplicado')
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, Pedido.Estado.ANULADO)


class IntegracionTests(PedidosBase):
    def test_unidades_en_transito_solo_de_pedidos_enviados_y_pendientes(self):
        self.assertEqual(unidades_en_transito(), {})            # borrador: aún no cuenta
        services.enviar_pedido(self.pedido, self.quimico)
        self.assertEqual(unidades_en_transito(), {self.producto.pk: 100})
        self.recibir(30)
        self.assertEqual(unidades_en_transito(), {self.producto.pk: 70})
        self.recibir(70, 'L2')
        self.assertEqual(unidades_en_transito(), {})

    def test_pedido_atrasado_genera_alerta_y_se_cierra_al_recibir(self):
        services.enviar_pedido(self.pedido, self.quimico)
        Pedido.objects.filter(pk=self.pedido.pk).update(fecha_entrega_estimada=HOY - timedelta(days=3))
        sincronizar()
        self.assertTrue(Alerta.objects.filter(tipo=Alerta.Tipo.PEDIDO_ATRASADO, resuelta=False).exists())
        self.recibir(100)
        sincronizar()
        self.assertFalse(Alerta.objects.filter(tipo=Alerta.Tipo.PEDIDO_ATRASADO, resuelta=False).exists())


class PermisosTests(PedidosBase):
    def test_tecnico_no_puede_autorizar_el_envio(self):
        self.client.login(username='tec', password='x')
        respuesta = self.client.post(reverse('pedidos:enviar', args=[self.pedido.pk]))
        self.assertEqual(respuesta.status_code, 403)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, Pedido.Estado.BORRADOR)

    def test_quimico_si_puede_autorizar_el_envio(self):
        self.client.login(username='qf', password='x')
        self.client.post(reverse('pedidos:enviar', args=[self.pedido.pk]))
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, Pedido.Estado.ENVIADO)

    def test_tecnico_ve_la_lista_de_pedidos(self):
        self.client.login(username='tec', password='x')
        self.assertEqual(self.client.get(reverse('pedidos:lista')).status_code, 200)

    def test_tecnico_no_administra_proveedores(self):
        self.client.login(username='tec', password='x')
        self.assertEqual(self.client.get(reverse('pedidos:proveedor_crear')).status_code, 403)
