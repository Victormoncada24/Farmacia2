from django.shortcuts import render

from core.views import permiso_requerido
from pedidos.models import Proveedor

from . import services
from .forms import AbastecimientoForm, AdherenciaForm


@permiso_requerido('ver_analitica')
def abastecimiento(request):
    form = AbastecimientoForm(request.GET)
    datos = form.cleaned_data if form.is_valid() else {}
    dias = int(datos.get('dias') or services.PERIODO_DEFECTO)
    lead_time = datos.get('lead_time') or services.LEAD_TIME_DEFECTO
    objetivo = datos.get('dias_objetivo') or services.DIAS_OBJETIVO_DEFECTO
    filas = services.analizar_abastecimiento(dias, lead_time, objetivo)
    resumen = services.resumen_abastecimiento(filas)
    if datos.get('estado'):
        filas = [f for f in filas if f.estado == datos['estado']]
    if datos.get('solo_pedir'):
        filas = [f for f in filas if f.pedido > 0]
    grafico = [f for f in filas if f.dias_cobertura is not None][:10]
    return render(request, 'analitica/abastecimiento.html', {
        'titulo': 'Abastecimiento inteligente', 'form': form, 'filas': filas, 'resumen': resumen,
        'dias': dias, 'lead_time': lead_time, 'dias_objetivo': objetivo,
        'proveedores': Proveedor.objects.filter(activo=True),
        'grafico': {'labels': [f.producto.nombre for f in grafico],
                    'valores': [round(f.dias_cobertura) for f in grafico]},
    })


@permiso_requerido('ver_analitica')
def adherencia(request):
    form = AdherenciaForm(request.GET)
    datos = form.cleaned_data if form.is_valid() else {}
    filas = services.analizar_adherencia(
        programa=datos.get('programa'), umbral_atraso=datos.get('umbral_atraso') or 35,
        umbral_abandono=datos.get('umbral_abandono') or 60)
    resumen = services.resumen_adherencia(filas)
    if datos.get('estado'):
        filas = [f for f in filas if f.estado == datos['estado']]
    return render(request, 'analitica/adherencia.html', {
        'titulo': 'Adherencia a tratamientos', 'form': form, 'filas': filas, 'resumen': resumen,
    })
