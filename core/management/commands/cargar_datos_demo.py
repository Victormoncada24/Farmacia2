"""Carga datos de demostración: usuarios por rol, catálogo, lotes, pacientes, recetas, carros y libro."""
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import Usuario
from alertas.services import sincronizar
from carros import services as carros_srv
from carros.models import CarroClinico, CarroItem
from controlados import services as ctrl_srv
from controlados.models import MovimientoControlado
from core import roles
from core.utils import calcular_dv
from dispensacion import services as disp_srv
from dispensacion.models import Dispensacion, Receta, RecetaItem
from inventario import services as inv_srv
from inventario.models import Categoria, Lote, MovimientoInventario, Producto, Ubicacion
from pacientes.models import CuotaPrograma, InscripcionPrograma, Paciente, Programa
from pedidos import services as ped_srv
from pedidos.models import Pedido, PedidoItem, Proveedor

CLAVE_DEMO = 'Inacap2026!!'

CATEGORIAS = [
    'Antihipertensivos', 'Cardiovasculares y lípidos', 'Antidiabéticos', 'Analgésicos y antiinflamatorios',
    'Antibióticos', 'Gastroprotectores', 'Respiratorios', 'Endocrinológicos',
    'Controlados (estupefacientes y psicotrópicos)', 'Emergencia y carro de paro', 'Insumos clínicos',
]

# (código, nombre, presentación, categoría, tipo, control, mínimo, objetivo)
M, I = Producto.Tipo.MEDICAMENTO, Producto.Tipo.INSUMO
NC, PS, ES = Producto.Control.NINGUNO, Producto.Control.PSICOTROPICO, Producto.Control.ESTUPEFACIENTE
PRODUCTOS = [
    ('MED-001', 'Losartán', '50 mg comprimidos', 'Antihipertensivos', M, NC, 200, 600),
    ('MED-002', 'Enalapril', '10 mg comprimidos', 'Antihipertensivos', M, NC, 200, 600),
    ('MED-003', 'Atenolol', '50 mg comprimidos', 'Antihipertensivos', M, NC, 150, 450),
    ('MED-004', 'Amlodipino', '5 mg comprimidos', 'Antihipertensivos', M, NC, 150, 450),
    ('MED-005', 'Metformina', '850 mg comprimidos', 'Antidiabéticos', M, NC, 300, 900),
    ('MED-006', 'Glibenclamida', '5 mg comprimidos', 'Antidiabéticos', M, NC, 150, 450),
    ('MED-007', 'Insulina NPH', '100 UI/ml frasco 10 ml', 'Antidiabéticos', M, NC, 20, 60),
    ('MED-008', 'Atorvastatina', '20 mg comprimidos', 'Cardiovasculares y lípidos', M, NC, 150, 450),
    ('MED-009', 'Paracetamol', '500 mg comprimidos', 'Analgésicos y antiinflamatorios', M, NC, 300, 900),
    ('MED-010', 'Ibuprofeno', '400 mg comprimidos', 'Analgésicos y antiinflamatorios', M, NC, 150, 450),
    ('MED-011', 'Amoxicilina', '500 mg cápsulas', 'Antibióticos', M, NC, 100, 300),
    ('MED-012', 'Omeprazol', '20 mg cápsulas', 'Gastroprotectores', M, NC, 150, 450),
    ('MED-013', 'Salbutamol', '100 mcg inhalador', 'Respiratorios', M, NC, 30, 90),
    ('MED-014', 'Levotiroxina', '100 mcg comprimidos', 'Endocrinológicos', M, NC, 100, 300),
    ('MED-015', 'Clonazepam', '2 mg comprimidos', 'Controlados (estupefacientes y psicotrópicos)', M, PS, 30, 90),
    ('MED-016', 'Diazepam', '10 mg comprimidos', 'Controlados (estupefacientes y psicotrópicos)', M, PS, 30, 90),
    ('MED-017', 'Fenobarbital', '100 mg comprimidos', 'Controlados (estupefacientes y psicotrópicos)', M, PS, 30, 90),
    ('MED-018', 'Morfina', '10 mg/ml ampolla', 'Controlados (estupefacientes y psicotrópicos)', M, ES, 10, 30),
    ('EME-001', 'Adrenalina', '1 mg/ml ampolla', 'Emergencia y carro de paro', M, NC, 20, 60),
    ('EME-002', 'Atropina', '1 mg/ml ampolla', 'Emergencia y carro de paro', M, NC, 10, 30),
    ('EME-003', 'Amiodarona', '150 mg ampolla', 'Emergencia y carro de paro', M, NC, 10, 30),
    ('EME-004', 'Lidocaína', '2% ampolla', 'Emergencia y carro de paro', M, NC, 10, 30),
    ('EME-005', 'Suero fisiológico', '0,9% 500 ml', 'Emergencia y carro de paro', M, NC, 20, 60),
    ('INS-001', 'Jeringa', '10 ml', 'Insumos clínicos', I, NC, 50, 150),
    ('INS-002', 'Aguja', '21G', 'Insumos clínicos', I, NC, 50, 150),
]


def rut(cuerpo):
    return f'{cuerpo}-{calcular_dv(cuerpo)}'


class Command(BaseCommand):
    help = 'Carga datos de demostración (usuarios, catálogo, stock, pacientes, recetas, carros, libro).'

    @transaction.atomic
    def handle(self, *args, **opciones):
        if Producto.objects.exists() or Paciente.objects.exists():
            raise CommandError('La base de datos ya contiene datos. Use una base nueva para cargar la demo.')
        hoy = timezone.localdate()

        # ------------------------------------------------------------ Usuarios
        def usuario(username, nombre, apellido, cuerpo, rol, staff=False):
            return Usuario.objects.create_user(
                username=username, password=CLAVE_DEMO, first_name=nombre, last_name=apellido,
                email=f'{username}@demo.inacap.cl', rut=rut(cuerpo), telefono='+56 9 5555 0000', rol=rol,
                is_staff=staff)

        admin = usuario('admin', 'Ana', 'Administradora', 10111222, roles.ADMIN, staff=True)
        quimico = usuario('quimico', 'Camila', 'Fuentes (Q.F.)', 11222333, roles.QUIMICO)
        tecnico = usuario('tecnico', 'Tomás', 'Herrera', 12333444, roles.TECNICO)
        clinico = usuario('clinico', 'Carolina', 'Vega (Enfermera)', 13444555, roles.CLINICO)

        # ------------------------------------------------------------ Catálogo
        categorias = {n: Categoria.objects.create(nombre=n) for n in CATEGORIAS}
        productos = {}
        for codigo, nombre, presentacion, cat, tipo, control, minimo, objetivo in PRODUCTOS:
            productos[codigo] = Producto.objects.create(
                codigo=codigo, nombre=nombre, presentacion=presentacion, categoria=categorias[cat], tipo=tipo,
                control=control, stock_minimo=minimo, stock_objetivo=objetivo,
                principio_activo=nombre, codigo_barras=f'780{codigo[-3:]}00{len(nombre):04d}')

        # ---------------------------------------------------------------- Stock
        ingreso = inv_srv.ingresar_lote
        for i, (codigo, p) in enumerate(productos.items()):
            if codigo in ('MED-014', 'MED-013'):
                continue
            base = (p.stock_minimo or 30) * 3
            dias_a = 25 if codigo == 'MED-012' else 120 + i * 7   # Omeprazol: lote crítico (<30 días)
            ingreso(producto=p, numero_lote=f'L{2600 + i}A', fecha_vencimiento=hoy + timedelta(days=dias_a),
                    cantidad=int(base * 0.4), ubicacion=Ubicacion.BODEGA, usuario=tecnico,
                    documento_ref=f'GD-{1000 + i}', observacion='Remesa CENABAST (demo)')
            ingreso(producto=p, numero_lote=f'L{2600 + i}A', fecha_vencimiento=hoy + timedelta(days=dias_a),
                    cantidad=int(base * 0.6), ubicacion=Ubicacion.VITRINA, usuario=tecnico,
                    documento_ref=f'GD-{1000 + i}')
            ingreso(producto=p, numero_lote=f'L{2600 + i}B', fecha_vencimiento=hoy + timedelta(days=420),
                    cantidad=base, ubicacion=Ubicacion.BODEGA, usuario=tecnico, documento_ref=f'GD-{2000 + i}')
        # Casos para mostrar alertas
        ingreso(producto=productos['MED-011'], numero_lote='L-VENC-01', fecha_vencimiento=hoy - timedelta(days=20),
                cantidad=15, ubicacion=Ubicacion.BODEGA, usuario=tecnico, documento_ref='GD-0001')
        ingreso(producto=productos['MED-013'], numero_lote='L2613A', fecha_vencimiento=hoy + timedelta(days=300),
                cantidad=50, ubicacion=Ubicacion.VITRINA, usuario=tecnico, documento_ref='GD-3001')
        ingreso(producto=productos['MED-013'], numero_lote='L2613A', fecha_vencimiento=hoy + timedelta(days=300),
                cantidad=10, ubicacion=Ubicacion.BODEGA, usuario=tecnico, documento_ref='GD-3001')
        # MED-014 (Levotiroxina) queda sin stock a propósito.

        # Historial de consumo de las últimas 4 semanas (alimenta el abastecimiento inteligente)
        def historial(producto, semanal, semanas=4):
            for semana in range(semanas):
                inicio = timezone.now() - timedelta(minutes=5)
                inv_srv.descontar_fefo(
                    producto=producto, cantidad=semanal, ubicaciones=(Ubicacion.VITRINA,), usuario=tecnico,
                    tipo=MovimientoInventario.Tipo.DISPENSACION, referencia='Consumo histórico (demo)')
                MovimientoInventario.objects.filter(
                    producto=producto, referencia='Consumo histórico (demo)', fecha__gte=inicio
                ).update(fecha=timezone.now() - timedelta(days=3 + 7 * semana))

        for codigo, p in productos.items():
            if p.es_controlado or codigo in ('MED-013', 'MED-014'):
                continue
            historial(p, max(1, int(p.stock_minimo * 0.2)))
        historial(productos['MED-013'], 12)   # Salbutamol: consumo alto → cobertura crítica

        # ------------------------------------------------------------ Programas
        prog = {
            'hta': Programa.objects.create(nombre='Hipertensión Arterial', tipo=Programa.Tipo.GES),
            'dm2': Programa.objects.create(nombre='Diabetes Mellitus tipo 2', tipo=Programa.Tipo.GES),
            'epi': Programa.objects.create(nombre='Epilepsia no refractaria', tipo=Programa.Tipo.GES),
            'cv': Programa.objects.create(nombre='Crónicos cardiovasculares', tipo=Programa.Tipo.CRONICO),
            'resp': Programa.objects.create(nombre='Crónicos respiratorios', tipo=Programa.Tipo.CRONICO),
        }

        # ------------------------------------------------------------ Pacientes
        F = Paciente.Prevision

        def paciente(cuerpo, nombres, apellidos, nac, prev):
            return Paciente.objects.create(
                documento=rut(cuerpo), nombres=nombres, apellidos=apellidos, fecha_nacimiento=nac, prevision=prev,
                telefono='+56 9 4444 0000', direccion='Calle Demo 123, Santiago', email='paciente@demo.cl')

        p1 = paciente(12345678, 'María', 'González Rojas', hoy.replace(year=hoy.year - 58), F.FONASA_A)
        p2 = paciente(13456789, 'Juan', 'Pérez Soto', hoy.replace(year=hoy.year - 64), F.FONASA_B)
        p3 = paciente(14567890, 'Rosa', 'Muñoz Díaz', hoy.replace(year=hoy.year - 71), F.FONASA_A)
        p4 = paciente(15678901, 'Pedro', 'Soto Lagos', hoy.replace(year=hoy.year - 33), F.FONASA_C)
        p5 = paciente(16789012, 'Carla', 'Rojas Núñez', hoy.replace(year=hoy.year - 29), F.FONASA_B)
        p6 = paciente(17890123, 'Luis', 'Vidal Araya', hoy.replace(year=hoy.year - 45), F.ISAPRE)

        def inscribir(pac, programa, cuotas):
            ins = InscripcionPrograma.objects.create(paciente=pac, programa=programa,
                                                     diagnostico='Diagnóstico de demostración')
            for codigo, cantidad in cuotas:
                CuotaPrograma.objects.create(inscripcion=ins, producto=productos[codigo], cantidad_mensual=cantidad)

        inscribir(p1, prog['hta'], [('MED-001', 60), ('MED-004', 30)])
        inscribir(p2, prog['dm2'], [('MED-005', 90), ('MED-007', 4)])
        inscribir(p3, prog['cv'], [('MED-008', 30), ('MED-002', 30)])
        inscribir(p4, prog['epi'], [('MED-017', 60)])

        # Pacientes crónicos que NO han retirado a tiempo (para el módulo de adherencia)
        p7 = paciente(18901234, 'Elena', 'Castro Vera', hoy.replace(year=hoy.year - 67), F.FONASA_A)
        p8 = paciente(19012345, 'Mario', 'Fuentes Lira', hoy.replace(year=hoy.year - 72), F.FONASA_B)
        inscribir(p7, prog['hta'], [('MED-001', 60)])
        inscribir(p8, prog['dm2'], [('MED-005', 90)])
        InscripcionPrograma.objects.filter(paciente=p7).update(fecha_inicio=hoy - timedelta(days=120))
        InscripcionPrograma.objects.filter(paciente=p8).update(fecha_inicio=hoy - timedelta(days=200))

        # ------------------------------------------------------ Recetas y entregas
        def receta(pac, numero, programa, modalidad, lineas, medico='Dr. Andrés Lagos', mrut=13999888):
            r = Receta.objects.create(
                paciente=pac, numero=numero, programa=programa, modalidad=modalidad, medico_nombre=medico,
                medico_rut=rut(mrut), establecimiento_emisor='Establecimiento de simulación', fecha_emision=hoy - timedelta(days=2),
                vigencia_dias=30 if modalidad == Receta.Modalidad.ESTANDAR else 90, registrada_por=tecnico,
                observaciones='Control de rutina (demo)')
            for codigo, cantidad, indic in lineas:
                RecetaItem.objects.create(receta=r, producto=productos[codigo], cantidad_prescrita=cantidad,
                                          indicacion=indic)
            return r

        casos = [
            (receta(p1, 'R-1001', prog['hta'], Receta.Modalidad.ESTANDAR,
                    [('MED-001', 180, '1 comp cada 12 h'), ('MED-004', 90, '1 comp al día')]),
             {'MED-001': 60, 'MED-004': 30}, dict(retira_tercero=True, retiro_nombre='Héctor González',
                                                   retiro_rut=rut(8765432), retiro_parentesco='Padre'), 3),
            (receta(p2, 'R-1002', prog['dm2'], Receta.Modalidad.ESTANDAR,
                    [('MED-005', 270, '1 comp cada 8 h'), ('MED-007', 12, '20 UI en la mañana')]),
             {'MED-005': 90, 'MED-007': 4}, {}, 2),
            (receta(p3, 'R-1003', prog['cv'], Receta.Modalidad.ESTANDAR,
                    [('MED-008', 90, '1 comp nocturno'), ('MED-002', 90, '1 comp al día')]),
             {'MED-008': 30, 'MED-002': 30}, {}, 1),
            (receta(p4, 'R-1004', prog['epi'], Receta.Modalidad.RETENIDA, [('MED-017', 180, '1 comp cada 12 h')]),
             {'MED-017': 30}, {}, 0),
            (receta(p5, 'R-1005', None, Receta.Modalidad.ESTANDAR, [('MED-009', 40, 'SOS dolor'),
                                                                     ('MED-011', 21, '1 cáps cada 8 h por 7 días')]),
             {'MED-009': 20, 'MED-011': 21}, {}, 4),
        ]
        atrasados = [
            (receta(p7, 'R-0901', prog['hta'], Receta.Modalidad.ESTANDAR, [('MED-001', 240, '1 comp cada 12 h')]),
             {'MED-001': 60}, 42),
            (receta(p8, 'R-0902', prog['dm2'], Receta.Modalidad.ESTANDAR, [('MED-005', 360, '1 comp cada 8 h')]),
             {'MED-005': 90}, 78),
        ]
        receta(p6, 'R-1006', None, Receta.Modalidad.ESTANDAR, [('MED-009', 20, 'SOS')])  # sin cobertura pública (demo)

        for r, cantidades, retiro, hace_dias in casos:
            try:
                por_item = {i.pk: cantidades.get(i.producto.codigo, 0) for i in r.items.select_related('producto')}
                d = disp_srv.dispensar(receta=r, cantidades=por_item, usuario=tecnico,
                                       observacion='Entrega de demostración', **retiro)
                dia = min(hace_dias, hoy.day - 1)
                Dispensacion.objects.filter(pk=d.pk).update(fecha=timezone.now() - timedelta(days=dia))
            except disp_srv.DispensacionError as error:
                self.stdout.write(self.style.WARNING(f'Demo: no se pudo dispensar {r.numero}: {error}'))

        for r, cantidades, hace_dias in atrasados:
            try:
                por_item = {i.pk: cantidades.get(i.producto.codigo, 0) for i in r.items.select_related('producto')}
                d = disp_srv.dispensar(receta=r, cantidades=por_item, usuario=tecnico,
                                       observacion='Último retiro registrado (demo)')
                Dispensacion.objects.filter(pk=d.pk).update(fecha=timezone.now() - timedelta(days=hace_dias))
            except disp_srv.DispensacionError as error:
                self.stdout.write(self.style.WARNING(f'Demo: no se pudo dispensar {r.numero}: {error}'))

        # ------------------------------------------------------- Carros clínicos
        paro = CarroClinico.objects.create(nombre='Carro de Paro — Box de Reanimación', tipo=CarroClinico.Tipo.PARO,
                                           ubicacion='Box de Reanimación', responsable=clinico,
                                           precinto='PR-2026-014')
        unidosis = CarroClinico.objects.create(nombre='Carro Unidosis — Sala de Tratamiento', tipo=CarroClinico.Tipo.UNIDOSIS,
                                               ubicacion='Sala de Tratamiento', responsable=clinico)
        for codigo, cantidad in (('EME-001', 10), ('EME-002', 5), ('EME-003', 6), ('EME-004', 4), ('EME-005', 4),
                                 ('INS-001', 20), ('INS-002', 20)):
            CarroItem.objects.create(carro=paro, producto=productos[codigo], cantidad_requerida=cantidad)
        for codigo, cantidad in (('MED-009', 30), ('MED-012', 20), ('MED-002', 30)):
            CarroItem.objects.create(carro=unidosis, producto=productos[codigo], cantidad_requerida=cantidad)
        carros_srv.reponer_carro(paro, {}, tecnico, 'Abastecimiento inicial (demo)')
        carros_srv.reponer_carro(unidosis, {}, tecnico, 'Abastecimiento inicial (demo)')
        carros_srv.registrar_consumo(paro, productos['EME-001'], 3, clinico, 'Paro cardiorrespiratorio sala 2 (demo)')
        carros_srv.crear_solicitud(paro, clinico, {productos['EME-001'].pk: 3}, 'Reposición post-evento (demo)')

        # -------------------------------------------- Libro de controlados: firmas
        pendientes = list(MovimientoControlado.objects.order_by('id'))
        for movimiento in pendientes[:-2]:
            ctrl_srv.firmar(movimiento, quimico)
        ctrl_srv.registrar_conteo(producto=productos['MED-018'], cantidad_contada=
                                  ctrl_srv.saldo_libro(productos['MED-018']), usuario=quimico,
                                  observacion='Conteo mensual (demo)')

        # ----------------------------------------------- Proveedores y pedidos
        P = Proveedor.Tipo
        prov_cenabast = Proveedor.objects.create(
            nombre='CENABAST — Central Nacional de Abastecimiento', tipo=P.CENABAST, plazo_entrega_dias=20,
            contacto='Ejecutivo de cuentas (demo)', telefono='+56 2 2000 0000', email='pedidos@cenabast.demo')
        prov_ss = Proveedor.objects.create(
            nombre='Servicio de Salud — Bodega central', tipo=P.SERVICIO_SALUD, plazo_entrega_dias=7,
            contacto='Encargado de bodega (demo)', telefono='+56 2 2000 1111', email='bodega@servicio.demo')
        prov_drog = Proveedor.objects.create(
            nombre='Droguería Demo S.A.', tipo=P.DROGUERIA, rut=rut(76123456), plazo_entrega_dias=3,
            contacto='Ventas institucionales (demo)', telefono='+56 2 2000 2222', email='ventas@drogueria.demo')
        Proveedor.objects.create(
            nombre='Laboratorio Demo Chile', tipo=P.LABORATORIO, rut=rut(77234567), plazo_entrega_dias=10,
            contacto='Atención a clientes (demo)', email='clientes@laboratorio.demo')

        def pedido(prov, prioridad, lineas, obs=''):
            ped = Pedido.objects.create(proveedor=prov, creado_por=tecnico, prioridad=prioridad, observacion=obs)
            for codigo, cantidad in lineas:
                PedidoItem.objects.create(pedido=ped, producto=productos[codigo], cantidad_pedida=cantidad)
            return ped

        # 1) Borrador pendiente de autorización (Levotiroxina sin stock)
        pedido(prov_drog, Pedido.Prioridad.URGENTE, [('MED-014', 300), ('MED-013', 100)],
               'Levotiroxina sin stock (demo)')
        # 2) Enviado y atrasado → genera una alerta
        atrasado = pedido(prov_cenabast, Pedido.Prioridad.NORMAL, [('MED-012', 300), ('MED-007', 40)],
                          'Remesa trimestral (demo)')
        ped_srv.enviar_pedido(atrasado, quimico)
        Pedido.objects.filter(pk=atrasado.pk).update(
            fecha=timezone.now() - timedelta(days=32), fecha_envio=timezone.now() - timedelta(days=30),
            fecha_entrega_estimada=hoy - timedelta(days=10))
        # 3) Enviado con recepción parcial (ya ingresó stock con su lote)
        parcial = pedido(prov_ss, Pedido.Prioridad.NORMAL, [('MED-009', 500), ('MED-010', 200)],
                         'Reposición mensual (demo)')
        ped_srv.enviar_pedido(parcial, quimico)
        item = parcial.items.get(producto=productos['MED-009'])
        ped_srv.recibir_pedido(
            pedido=parcial, usuario=tecnico, ubicacion=Ubicacion.BODEGA, documento_ref='GD-DEMO-77',
            observacion='Entrega parcial (demo)',
            lineas=[{'item_id': item.pk, 'cantidad': 300, 'numero_lote': 'L-PED-01',
                     'vencimiento': hoy + timedelta(days=365)}])
        Pedido.objects.filter(pk=parcial.pk).update(fecha=timezone.now() - timedelta(days=6))

        sincronizar()

        self.stdout.write(self.style.SUCCESS('Datos de demostración cargados.'))
        self.stdout.write(f'Usuarios (contraseña para todos: {CLAVE_DEMO}):')
        for u in (admin, quimico, tecnico, clinico):
            self.stdout.write(f'  {u.username:<8} → {u.get_rol_display()}')
