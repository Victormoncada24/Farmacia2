"""Capa de datos del módulo de inteligencia: arma las entradas para calculos.py desde el ORM."""
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.conf import settings
from django.db.models import F, Max, Sum
from django.utils import timezone

from dispensacion.models import Dispensacion, DispensacionItem
from inventario.models import Lote, MovimientoInventario, Producto
from pacientes.models import CuotaPrograma, InscripcionPrograma
from pedidos.models import Pedido, PedidoItem

from . import calculos as calc

T = MovimientoInventario.Tipo
PERIODO_DEFECTO = getattr(settings, 'ABASTECIMIENTO_PERIODO_DIAS', 30)
LEAD_TIME_DEFECTO = getattr(settings, 'ABASTECIMIENTO_LEAD_TIME_DIAS', 15)
DIAS_OBJETIVO_DEFECTO = getattr(settings, 'ABASTECIMIENTO_DIAS_OBJETIVO', 60)


# ------------------------------------------------------------ Abastecimiento
@dataclass
class FilaAbastecimiento:
    producto: Producto
    categoria: str
    unidades_periodo: int
    consumo_diario: float
    stock: int
    vencidas: int
    dias_cobertura: float | None
    fecha_quiebre: date | None
    en_riesgo: int
    detalle_riesgo: list = field(default_factory=list)
    pedido: int = 0
    estado: str = 'SIN_CONSUMO'
    abc: str = 'C'
    en_transito: int = 0

    @property
    def estado_texto(self):
        return calc.ESTADOS_ABASTECIMIENTO[self.estado]

    @property
    def cobertura_texto(self):
        return '—' if self.dias_cobertura is None else f'{self.dias_cobertura:.0f}'

    @property
    def riesgo_texto(self):
        if not self.detalle_riesgo:
            return ''
        return '; '.join(f'{l.numero}: {r} u. (vence en {d} d)' for l, r, d in self.detalle_riesgo)


def consumo_por_producto(dias):
    """Unidades que salieron por dispensación o reposición de carros en los últimos `dias`."""
    desde = timezone.now() - timedelta(days=dias)
    filas = (MovimientoInventario.objects
             .filter(fecha__gte=desde, tipo__in=[T.DISPENSACION, T.REPOSICION_CARRO])
             .values('producto').annotate(total=Sum('cantidad')))
    return {f['producto']: f['total'] for f in filas}


def unidades_en_transito():
    """Unidades pendientes de recibir en pedidos ya enviados a proveedores ({producto_id: unidades})."""
    filas = (PedidoItem.objects
             .filter(pedido__estado__in=[Pedido.Estado.ENVIADO, Pedido.Estado.PARCIAL])
             .values('producto').annotate(pend=Sum(F('cantidad_pedida') - F('cantidad_recibida'))))
    return {f['producto']: max(f['pend'] or 0, 0) for f in filas}


def _lotes_por_producto():
    """{producto_id: [LoteStock]} con unidades totales (bodega + vitrina) por lote activo."""
    filas = (Lote.objects.filter(activo=True).annotate(u=Sum('stocks__cantidad')).filter(u__gt=0)
             .values('id', 'producto_id', 'numero_lote', 'fecha_vencimiento', 'u'))
    resultado = {}
    for f in filas:
        resultado.setdefault(f['producto_id'], []).append(
            calc.LoteStock(id=f['id'], numero=f['numero_lote'], vencimiento=f['fecha_vencimiento'], unidades=f['u']))
    return resultado


def analizar_abastecimiento(dias=None, lead_time=None, dias_objetivo=None, hoy=None):
    """Cobertura, quiebre proyectado, riesgo de merma y pedido sugerido por producto.

    El pedido sugerido descuenta lo que ya viene en camino (pedidos enviados y no recibidos).
    """
    dias = dias or PERIODO_DEFECTO
    lead_time = lead_time or LEAD_TIME_DEFECTO
    dias_objetivo = dias_objetivo or DIAS_OBJETIVO_DEFECTO
    hoy = hoy or timezone.localdate()

    consumos = consumo_por_producto(dias)
    lotes = _lotes_por_producto()
    transito = unidades_en_transito()
    abc = calc.clasificar_abc({pid: consumos.get(pid, 0) for pid in Producto.objects.filter(activo=True)
                               .values_list('id', flat=True)})
    filas = []
    for producto in Producto.objects.filter(activo=True).select_related('categoria'):
        lista = lotes.get(producto.id, [])
        vigentes = [l for l in lista if l.vencimiento >= hoy]
        stock = sum(l.unidades for l in vigentes)
        unidades = consumos.get(producto.id, 0)
        consumo = calc.consumo_diario(unidades, dias)
        cobertura = calc.dias_cobertura(stock, consumo)
        en_riesgo, vencidas, detalle = calc.simular_riesgo_vencimiento(lista, consumo, hoy)
        en_camino = transito.get(producto.id, 0)
        bruto = calc.pedido_sugerido(stock, en_riesgo, consumo, producto.objetivo_efectivo, dias_objetivo)
        filas.append(FilaAbastecimiento(
            producto=producto, categoria=producto.categoria.nombre, unidades_periodo=unidades,
            consumo_diario=consumo, stock=stock, vencidas=vencidas, dias_cobertura=cobertura,
            fecha_quiebre=(hoy + timedelta(days=int(cobertura))) if cobertura is not None else None,
            en_riesgo=en_riesgo, detalle_riesgo=detalle, pedido=max(bruto - en_camino, 0),
            estado=calc.clasificar_abastecimiento(stock, consumo, cobertura if cobertura is not None else 0,
                                                  en_riesgo, lead_time),
            abc=abc.get(producto.id, 'C'), en_transito=en_camino))
    filas.sort(key=lambda f: (calc.ORDEN_ESTADO[f.estado],
                              f.dias_cobertura if f.dias_cobertura is not None else 1e9, f.producto.nombre))
    return filas


def resumen_abastecimiento(filas):
    return {
        'quiebres': sum(1 for f in filas if f.estado == 'QUIEBRE'),
        'criticos': sum(1 for f in filas if f.estado == 'CRITICO'),
        'atencion': sum(1 for f in filas if f.estado == 'ATENCION'),
        'unidades_en_riesgo': sum(f.en_riesgo for f in filas),
        'productos_con_riesgo': sum(1 for f in filas if f.en_riesgo > 0),
        'unidades_vencidas': sum(f.vencidas for f in filas),
        'pedido_total_unidades': sum(f.pedido for f in filas),
        'productos_a_pedir': sum(1 for f in filas if f.pedido > 0),
    }


# ----------------------------------------------------------------- Adherencia
@dataclass
class FilaAdherencia:
    inscripcion: InscripcionPrograma
    ultimo_retiro: date | None
    dias_sin_retiro: int | None
    dias_inscrito: int
    unidades_pendientes_mes: int
    cobertura: float | None
    estado: str

    @property
    def paciente(self):
        return self.inscripcion.paciente

    @property
    def programa(self):
        return self.inscripcion.programa

    @property
    def estado_texto(self):
        return calc.ESTADOS_ADHERENCIA[self.estado]

    @property
    def cobertura_pct(self):
        return None if self.cobertura is None else round(self.cobertura * 100)


def analizar_adherencia(programa=None, umbral_atraso=35, umbral_abandono=60, hoy=None):
    """Estado de retiro de medicamentos de pacientes inscritos en programas (GES / crónicos)."""
    hoy = hoy or timezone.localdate()
    inscripciones = (InscripcionPrograma.objects.filter(activo=True, paciente__activo=True, cuotas__isnull=False)
                     .distinct().select_related('paciente', 'programa'))
    if programa:
        inscripciones = inscripciones.filter(programa=programa)
    inscripciones = list(inscripciones)
    if not inscripciones:
        return []
    ids_ins = [i.pk for i in inscripciones]
    ids_pac = {i.paciente_id for i in inscripciones}

    cuotas = {}
    for c in CuotaPrograma.objects.filter(inscripcion_id__in=ids_ins):
        cuotas.setdefault(c.inscripcion_id, {})[c.producto_id] = c.cantidad_mensual

    base = DispensacionItem.objects.filter(dispensacion__paciente_id__in=ids_pac)

    def _agrupar(qs):
        filas = qs.values('dispensacion__paciente_id', 'dispensacion__programa_id', 'producto_id').annotate(t=Sum('cantidad'))
        return {(f['dispensacion__paciente_id'], f['dispensacion__programa_id'], f['producto_id']): f['t'] for f in filas}

    entregado_90 = _agrupar(base.filter(dispensacion__fecha__date__gte=hoy - timedelta(days=90)))
    entregado_mes = _agrupar(base.filter(dispensacion__fecha__year=hoy.year, dispensacion__fecha__month=hoy.month))
    ultimos = {(f['paciente_id'], f['programa_id']): f['u'] for f in
               Dispensacion.objects.filter(paciente_id__in=ids_pac).values('paciente_id', 'programa_id')
               .annotate(u=Max('fecha'))}

    filas = []
    for ins in inscripciones:
        cuota_ins = cuotas.get(ins.pk, {})
        ent90 = {p: entregado_90.get((ins.paciente_id, ins.programa_id, p), 0) for p in cuota_ins}
        entm = {p: entregado_mes.get((ins.paciente_id, ins.programa_id, p), 0) for p in cuota_ins}
        pendientes = sum(max(c - entm[p], 0) for p, c in cuota_ins.items())
        ultimo = ultimos.get((ins.paciente_id, ins.programa_id))
        ultimo_fecha = timezone.localtime(ultimo).date() if ultimo else None
        dias_sin = (hoy - ultimo_fecha).days if ultimo_fecha else None
        dias_ins = (hoy - ins.fecha_inicio).days
        meses = min(3.0, max(1.0, dias_ins / 30))
        filas.append(FilaAdherencia(
            inscripcion=ins, ultimo_retiro=ultimo_fecha, dias_sin_retiro=dias_sin, dias_inscrito=dias_ins,
            unidades_pendientes_mes=pendientes, cobertura=calc.cobertura_tratamiento(cuota_ins, ent90, meses),
            estado=calc.clasificar_adherencia(pendiente_mes=pendientes > 0, dias_sin_retiro=dias_sin,
                                              dias_inscrito=dias_ins, umbral_atraso=umbral_atraso,
                                              umbral_abandono=umbral_abandono)))
    filas.sort(key=lambda f: (calc.ORDEN_ADHERENCIA[f.estado], -(f.dias_sin_retiro if f.dias_sin_retiro is not None
                                                                 else f.dias_inscrito)))
    return filas


def resumen_adherencia(filas):
    total = len(filas)
    return {
        'total': total,
        'al_dia': sum(1 for f in filas if f.estado == 'AL_DIA'),
        'pendientes': sum(1 for f in filas if f.estado == 'PENDIENTE'),
        'atrasados': sum(1 for f in filas if f.estado == 'ATRASADO'),
        'abandono': sum(1 for f in filas if f.estado == 'ABANDONO'),
        'pct_al_dia': round(100 * sum(1 for f in filas if f.estado == 'AL_DIA') / total) if total else 0,
    }
