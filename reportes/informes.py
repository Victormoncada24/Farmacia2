"""Catálogo de informes. Cada función devuelve (encabezados, filas)."""
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable

from django.conf import settings
from django.db.models import Count, F, IntegerField, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from auditoria.models import RegistroAuditoria
from carros.models import CarroItem, ConsumoCarro
from controlados.models import MovimientoControlado
from dispensacion.models import Dispensacion, DispensacionItem
from inventario.models import Categoria, Lote, MovimientoInventario, Producto, Ubicacion
from analitica import services as analitica
from pacientes.models import CuotaPrograma
from pedidos.models import PedidoItem

ENTERO = IntegerField()


@dataclass(frozen=True)
class Informe:
    slug: str
    titulo: str
    descripcion: str
    funcion: Callable
    usa_fechas: bool = False
    permiso: str = 'ver_reportes'


def _rango(qs, campo, desde, hasta):
    if desde:
        qs = qs.filter(**{f'{campo}__date__gte': desde})
    if hasta:
        qs = qs.filter(**{f'{campo}__date__lte': hasta})
    return qs


def informe_stock(desde, hasta):
    qs = Producto.objects.filter(activo=True).select_related('categoria').con_stock().order_by(
        'categoria__nombre', 'nombre')
    filas = [(p.codigo, str(p), p.categoria.nombre, p.stock_bodega, p.stock_vitrina, p.stock_total,
              p.stock_minimo, p.proximo_vencimiento, p.estado_stock_texto) for p in qs]
    return ('Código', 'Producto', 'Categoría', 'Bodega', 'Vitrina', 'Total', 'Stock mínimo',
            'Próx. vencimiento', 'Estado'), filas


def informe_stock_categoria(desde, hasta):
    hoy = timezone.localdate()
    util = Q(productos__lotes__activo=True, productos__lotes__fecha_vencimiento__gte=hoy)
    filas = []
    for cat in Categoria.objects.annotate(
            unidades=Coalesce(Sum('productos__lotes__stocks__cantidad', filter=util), 0, output_field=ENTERO),
            n_productos=Count('productos', distinct=True)).order_by('nombre'):
        criticos = sum(1 for p in Producto.objects.filter(categoria=cat, activo=True, stock_minimo__gt=0).con_stock()
                       if p.stock_total <= p.stock_minimo)
        filas.append((cat.nombre, cat.n_productos, cat.unidades, criticos))
    return ('Categoría', 'N° de productos', 'Unidades disponibles', 'Productos en nivel crítico'), filas


def informe_vencimientos(desde, hasta):
    limite = timezone.localdate() + timedelta(days=settings.ALERTA_VENCIMIENTO_DIAS)
    lotes = (Lote.objects.filter(activo=True, fecha_vencimiento__lte=limite).select_related('producto')
             .annotate(total=Coalesce(Sum('stocks__cantidad'), 0, output_field=ENTERO))
             .filter(total__gt=0).order_by('fecha_vencimiento'))
    filas = [(l.producto.nombre, l.numero_lote, l.fecha_vencimiento, l.dias_para_vencer, l.stock_bodega,
              l.stock_vitrina, l.estado_vencimiento_texto) for l in lotes]
    return ('Producto', 'Lote', 'Vencimiento', 'Días', 'Bodega', 'Vitrina', 'Estado'), filas


def informe_movimientos(desde, hasta):
    qs = _rango(MovimientoInventario.objects.select_related('producto', 'lote', 'usuario'), 'fecha', desde, hasta)
    filas = [(m.fecha, m.get_tipo_display(), m.producto.nombre, m.lote.numero_lote, m.cantidad,
              m.get_ubicacion_origen_display(), m.get_ubicacion_destino_display(), m.referencia,
              m.usuario.username) for m in qs]
    return ('Fecha', 'Tipo', 'Producto', 'Lote', 'Cantidad', 'Origen', 'Destino', 'Referencia', 'Usuario'), filas


def informe_dispensaciones(desde, hasta):
    qs = _rango(DispensacionItem.objects.select_related(
        'dispensacion__paciente', 'dispensacion__programa', 'dispensacion__dispensado_por', 'producto', 'lote'),
        'dispensacion__fecha', desde, hasta).order_by('-dispensacion__fecha')
    filas = [(i.dispensacion.pk, i.dispensacion.fecha, i.dispensacion.paciente.documento,
              i.dispensacion.paciente.nombre_completo, i.dispensacion.programa_texto, i.producto.nombre,
              i.lote.numero_lote, i.cantidad, i.dispensacion.quien_retira, i.dispensacion.dispensado_por.username)
             for i in qs]
    return ('N°', 'Fecha', 'Documento', 'Paciente', 'Programa', 'Producto', 'Lote', 'Cantidad', 'Retira',
            'Dispensó'), filas


def informe_por_programa(desde, hasta):
    qs = _rango(Dispensacion.objects.all(), 'fecha', desde, hasta).values('programa__nombre').annotate(
        n=Count('id', distinct=True), pacientes=Count('paciente', distinct=True), unidades=Sum('items__cantidad')).order_by('-n')
    filas = [(r['programa__nombre'] or 'Atención estándar', r['n'], r['pacientes'], r['unidades'] or 0) for r in qs]
    return ('Programa', 'Dispensaciones', 'Pacientes atendidos', 'Unidades entregadas'), filas


def informe_top_productos(desde, hasta):
    qs = _rango(DispensacionItem.objects.all(), 'dispensacion__fecha', desde, hasta).values(
        'producto__codigo', 'producto__nombre', 'producto__categoria__nombre').annotate(
        total=Sum('cantidad'), entregas=Count('dispensacion', distinct=True)).order_by('-total')[:50]
    filas = [(r['producto__codigo'], r['producto__nombre'], r['producto__categoria__nombre'], r['total'],
              r['entregas']) for r in qs]
    return ('Código', 'Producto', 'Categoría', 'Unidades dispensadas', 'N° de entregas'), filas


def informe_pedido(desde, hasta):
    filas = []
    for p in Producto.objects.filter(activo=True, stock_minimo__gt=0).select_related('categoria').con_stock():
        if p.stock_total <= p.stock_minimo:
            filas.append((p.codigo, str(p), p.categoria.nombre, p.stock_total, p.stock_minimo, p.objetivo_efectivo,
                          max(p.objetivo_efectivo - p.stock_total, 0)))
    return ('Código', 'Producto', 'Categoría', 'Stock actual', 'Mínimo', 'Objetivo', 'Cantidad sugerida a pedir'), filas


def informe_cuotas(desde, hasta):
    filas = []
    for c in CuotaPrograma.objects.filter(inscripcion__activo=True).select_related(
            'inscripcion__paciente', 'inscripcion__programa', 'producto'):
        entregado = c.entregado_mes()
        filas.append((c.inscripcion.paciente.documento, c.inscripcion.paciente.nombre_completo,
                      c.inscripcion.programa.nombre, c.producto.nombre, c.cantidad_mensual, entregado,
                      max(c.cantidad_mensual - entregado, 0)))
    return ('Documento', 'Paciente', 'Programa', 'Producto', 'Cuota mensual', 'Entregado en el mes',
            'Saldo del mes'), filas


def informe_libro(desde, hasta):
    qs = _rango(MovimientoControlado.objects.select_related('producto', 'lote', 'registrado_por', 'firmado_por'),
                'fecha', desde, hasta).order_by('producto__nombre', 'fecha', 'id')
    filas = [(m.fecha, m.producto.nombre, m.lote.numero_lote if m.lote else '', m.get_tipo_display(), m.cantidad,
              m.saldo_resultante, m.referencia, m.paciente_documento, m.registrado_por.username,
              m.firmado_por.username if m.firmado_por else 'Pendiente') for m in qs]
    return ('Fecha', 'Producto', 'Lote', 'Movimiento', 'Cantidad', 'Saldo', 'Respaldo', 'Paciente',
            'Registró', 'Firmó'), filas


def informe_carros(desde, hasta):
    items = CarroItem.objects.select_related('carro', 'producto').order_by('carro__nombre', 'producto__nombre')
    filas = [(i.carro.nombre, i.carro.tipo_texto, i.producto.nombre, i.cantidad_requerida, i.cantidad_actual,
              i.faltante, i.fecha_vencimiento, i.estado) for i in items]
    return ('Carro', 'Tipo', 'Producto', 'Dotación', 'Actual', 'Faltante', 'Vencimiento', 'Estado'), filas


def informe_consumo_carros(desde, hasta):
    qs = _rango(ConsumoCarro.objects.select_related('carro', 'producto', 'registrado_por'), 'fecha', desde, hasta)
    filas = [(c.fecha, c.carro.nombre, c.producto.nombre, c.cantidad, c.referencia, c.registrado_por.username)
             for c in qs]
    return ('Fecha', 'Carro', 'Producto', 'Cantidad', 'Referencia', 'Registró'), filas


def informe_auditoria(desde, hasta):
    qs = _rango(RegistroAuditoria.objects.all(), 'fecha', desde, hasta)[:5000]
    filas = [(r.fecha, r.usuario_texto, r.get_accion_display(), r.modelo, r.objeto_id, r.descripcion, r.ip or '')
             for r in qs]
    return ('Fecha y hora', 'Usuario', 'Acción', 'Entidad', 'ID', 'Detalle', 'IP'), filas


def informe_abastecimiento(desde, hasta):
    filas = [(f.producto.codigo, str(f.producto), f.categoria, f.abc, f.unidades_periodo,
              round(f.consumo_diario, 2), f.stock, f.cobertura_texto, f.fecha_quiebre, f.en_riesgo,
              f.vencidas, f.en_transito, f.pedido, f.estado_texto) for f in analitica.analizar_abastecimiento()]
    return ('Código', 'Producto', 'Categoría', 'ABC', 'Consumo período', 'Consumo diario', 'Stock utilizable',
            'Cobertura (días)', 'Quiebre estimado', 'En riesgo de vencer', 'Ya vencidas', 'En tránsito',
            'Pedido sugerido', 'Estado'), filas


def informe_adherencia(desde, hasta):
    filas = [(f.paciente.documento, f.paciente.nombre_completo, f.paciente.telefono or '', f.programa.nombre,
              f.ultimo_retiro, f.dias_sin_retiro if f.dias_sin_retiro is not None else '',
              f.unidades_pendientes_mes, '' if f.cobertura_pct is None else f'{f.cobertura_pct}%',
              f.estado_texto) for f in analitica.analizar_adherencia()]
    return ('Documento', 'Paciente', 'Teléfono', 'Programa', 'Último retiro', 'Días sin retiro',
            'Unidades pendientes del mes', 'Cobertura 90 días', 'Estado'), filas


def informe_pedidos(desde, hasta):
    qs = _rango(PedidoItem.objects.select_related('pedido__proveedor', 'pedido__creado_por', 'producto'),
                'pedido__fecha', desde, hasta).order_by('-pedido__fecha', 'pedido__numero', 'producto__nombre')
    filas = [(i.pedido.numero, i.pedido.fecha, i.pedido.proveedor.nombre, i.pedido.get_prioridad_display(),
              i.pedido.estado_texto, i.producto.codigo, i.producto.nombre, i.cantidad_pedida, i.cantidad_recibida,
              i.pendiente, i.pedido.fecha_entrega_estimada, i.pedido.creado_por.username) for i in qs]
    return ('N° pedido', 'Fecha', 'Proveedor', 'Prioridad', 'Estado', 'Código', 'Producto', 'Pedido', 'Recibido',
            'Pendiente', 'Entrega estimada', 'Creó'), filas


INFORMES = {i.slug: i for i in (
    Informe('stock', 'Stock actual por producto', 'Existencias en bodega y vitrina con estado crítico.', informe_stock),
    Informe('stock-categoria', 'Resumen de stock por categoría', 'Unidades y productos críticos por categoría.',
            informe_stock_categoria),
    Informe('vencimientos', 'Lotes vencidos y por vencer', 'Control de fechas de vencimiento (FEFO).',
            informe_vencimientos),
    Informe('pedido-sugerido', 'Sugerencia de pedido / abastecimiento', 'Productos bajo el mínimo y cantidad sugerida.',
            informe_pedido),
    Informe('movimientos', 'Movimientos de inventario', 'Historial de ingresos, transferencias y salidas.',
            informe_movimientos, True),
    Informe('dispensaciones', 'Historial de dispensaciones', 'Entregas a pacientes con lote y quién retira.',
            informe_dispensaciones, True, 'ver_dispensaciones'),
    Informe('dispensaciones-programa', 'Dispensaciones por programa de salud', 'GES/AUGE, crónicos y estándar.',
            informe_por_programa, True, 'ver_dispensaciones'),
    Informe('productos-mas-dispensados', 'Productos más dispensados', 'Ranking de medicamentos entregados.',
            informe_top_productos, True, 'ver_dispensaciones'),
    Informe('cuotas-mes', 'Cuotas mensuales por paciente', 'Cuota, entregado y saldo del mes en curso.',
            informe_cuotas, False, 'ver_dispensaciones'),
    Informe('libro-controlados', 'Libro de estupefacientes y psicotrópicos', 'Asientos con saldo y firmas.',
            informe_libro, True, 'ver_controlados'),
    Informe('abastecimiento-inteligente', 'Abastecimiento inteligente (cobertura, quiebres y riesgo de merma)',
            'Consumo diario, días de cobertura, pérdida proyectada por vencimiento, clase ABC, stock en tránsito y pedido sugerido.',
            informe_abastecimiento, False, 'ver_analitica'),
    Informe('adherencia-pacientes', 'Adherencia de pacientes a programas',
            'Pacientes crónicos/GES con retiros pendientes o en riesgo de abandono, con teléfono de contacto.',
            informe_adherencia, False, 'ver_analitica'),
    Informe('pedidos-proveedores', 'Pedidos a proveedores',
            'Pedidos con su estado, cantidades pedidas, recibidas y pendientes, y entrega estimada.',
            informe_pedidos, True, 'ver_pedidos'),
    Informe('carros', 'Estado de carros clínicos', 'Dotación, faltantes y vencimientos por carro.', informe_carros),
    Informe('consumo-carros', 'Consumo de carros clínicos', 'Consumos registrados por el personal clínico.',
            informe_consumo_carros, True),
    Informe('auditoria', 'Auditoría de accesos y operaciones', 'Bitácora de usuarios, fechas y horas.',
            informe_auditoria, True, 'auditoria'),
)}
