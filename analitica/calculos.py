"""Lógica analítica pura (sin Django): cobertura, riesgo de vencimiento, pedido sugerido,
clasificación ABC y adherencia a tratamientos crónicos.

Se mantiene separada del ORM para poder probarla de forma aislada.
"""
from dataclasses import dataclass
from datetime import date
from math import ceil

HORIZONTE_RIESGO_DIAS = 180
EPS = 1e-9


@dataclass(frozen=True)
class LoteStock:
    id: int
    numero: str
    vencimiento: date
    unidades: int


# ---------------------------------------------------------------- Abastecimiento
def consumo_diario(unidades_periodo, dias_periodo):
    if dias_periodo <= 0:
        return 0.0
    return unidades_periodo / dias_periodo


def dias_cobertura(stock, consumo):
    """Días que alcanza el stock al ritmo actual. None si no hay consumo."""
    if consumo <= 0:
        return None
    return stock / consumo


def simular_riesgo_vencimiento(lotes, consumo, hoy, horizonte=HORIZONTE_RIESGO_DIAS):
    """Simula el consumo FEFO y estima cuántas unidades vencerán sin haberse usado.

    Para cada lote (ordenado por vencimiento) la demanda que puede absorber antes de vencer es
    `consumo * días_hasta_vencer` menos lo ya absorbido por los lotes anteriores.
    Devuelve (unidades_en_riesgo, unidades_ya_vencidas, detalle) donde detalle es una lista de
    (lote, unidades_en_riesgo, días_para_vencer) solo para lotes vigentes en riesgo.
    Solo se evalúan lotes que vencen dentro del `horizonte` (días).
    """
    ordenados = sorted((l for l in lotes if l.unidades > 0), key=lambda l: (l.vencimiento, l.id))
    absorbido = 0.0
    en_riesgo = 0
    vencidas = 0
    detalle = []
    for lote in ordenados:
        dias = (lote.vencimiento - hoy).days
        if dias < 0:
            vencidas += lote.unidades
            continue
        if dias > horizonte:
            break
        absorbible = max(0.0, consumo * dias - absorbido)
        usado = min(float(lote.unidades), absorbible)
        riesgo = int(ceil(lote.unidades - usado - EPS))
        absorbido += usado
        if riesgo > 0:
            en_riesgo += riesgo
            detalle.append((lote, riesgo, dias))
    return en_riesgo, vencidas, detalle


def pedido_sugerido(stock_utilizable, en_riesgo, consumo, objetivo, dias_objetivo):
    """Unidades a pedir para alcanzar el mayor entre el stock objetivo y la cobertura deseada,
    descontando lo que se perderá por vencimiento."""
    necesario = max(objetivo, int(ceil(consumo * dias_objetivo - EPS)))
    efectivo = max(stock_utilizable - en_riesgo, 0)
    return max(necesario - efectivo, 0)


def clasificar_abastecimiento(stock, consumo, cobertura, en_riesgo, lead_time):
    """Semáforo de abastecimiento: QUIEBRE, CRITICO, ATENCION, OPTIMO o SIN_CONSUMO."""
    if consumo <= 0:
        return 'SIN_CONSUMO'
    if stock <= 0:
        return 'QUIEBRE'
    if cobertura < lead_time:
        return 'CRITICO'
    if cobertura < lead_time * 2 or en_riesgo > 0:
        return 'ATENCION'
    return 'OPTIMO'


ESTADOS_ABASTECIMIENTO = {
    'QUIEBRE': 'Quiebre', 'CRITICO': 'Crítico', 'ATENCION': 'Atención',
    'OPTIMO': 'Óptimo', 'SIN_CONSUMO': 'Sin consumo',
}
ORDEN_ESTADO = {'QUIEBRE': 0, 'CRITICO': 1, 'ATENCION': 2, 'OPTIMO': 3, 'SIN_CONSUMO': 4}


def clasificar_abc(consumos):
    """Clasificación ABC (Pareto) por unidades consumidas: A ≈ 80 %, B ≈ 15 %, C el resto.

    `consumos` es {id: unidades}. Devuelve {id: 'A'|'B'|'C'}.
    """
    total = sum(consumos.values())
    if total <= 0:
        return {k: 'C' for k in consumos}
    resultado = {}
    acumulado = 0.0
    for clave, valor in sorted(consumos.items(), key=lambda kv: (-kv[1], kv[0])):
        antes = acumulado / total
        acumulado += valor
        if valor <= 0:
            resultado[clave] = 'C'
        elif antes < 0.80:
            resultado[clave] = 'A'
        elif antes < 0.95:
            resultado[clave] = 'B'
        else:
            resultado[clave] = 'C'
    return resultado


# -------------------------------------------------------------------- Adherencia
def cobertura_tratamiento(cuotas, entregado, meses=3.0):
    """Proporción (0–1) del tratamiento esperado que el paciente efectivamente retiró.

    `cuotas` = {producto: cuota_mensual}; `entregado` = {producto: unidades retiradas en el período}.
    Devuelve None si no hay cuotas definidas.
    """
    esperado = sum(c * meses for c in cuotas.values())
    if esperado <= 0:
        return None
    cubierto = sum(min(float(entregado.get(p, 0)), c * meses) for p, c in cuotas.items())
    return cubierto / esperado


def clasificar_adherencia(*, pendiente_mes, dias_sin_retiro, dias_inscrito, umbral_atraso=35, umbral_abandono=60):
    """AL_DIA, PENDIENTE, ATRASADO o ABANDONO.

    Si el paciente nunca ha retirado se usa el tiempo transcurrido desde su inscripción.
    """
    if not pendiente_mes:
        return 'AL_DIA'
    referencia = dias_sin_retiro if dias_sin_retiro is not None else dias_inscrito
    if referencia >= umbral_abandono:
        return 'ABANDONO'
    if referencia >= umbral_atraso:
        return 'ATRASADO'
    return 'PENDIENTE'


ESTADOS_ADHERENCIA = {
    'AL_DIA': 'Al día', 'PENDIENTE': 'Pendiente', 'ATRASADO': 'Atrasado', 'ABANDONO': 'Riesgo de abandono',
}
ORDEN_ADHERENCIA = {'ABANDONO': 0, 'ATRASADO': 1, 'PENDIENTE': 2, 'AL_DIA': 3}
