from datetime import timedelta

from django import forms
from django.contrib.auth.decorators import login_required
from django.db.models import Count, IntegerField, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.utils import timezone

from alertas.models import Alerta
from alertas.services import sincronizar
from auditoria.models import RegistroAuditoria
from auditoria.services import registrar as registrar_auditoria
from core.exports import respuesta_excel, respuesta_pdf
from core.forms import BootstrapFormMixin
from core.views import permiso_requerido
from dispensacion.models import Dispensacion, DispensacionItem
from analitica import services as analitica
from inventario.models import Categoria, Producto, StockLote
from pacientes.models import InscripcionPrograma

from .informes import INFORMES


class RangoFechasForm(BootstrapFormMixin, forms.Form):
    desde = forms.DateField(required=False, label='Desde')
    hasta = forms.DateField(required=False, label='Hasta')


@login_required
def dashboard(request):
    return render(request, 'reportes/dashboard.html', {'titulo': 'Dashboard'})


@login_required
def api_dashboard(request):
    """Indicadores en tiempo real (el navegador consulta cada 30 s)."""
    sincronizar()
    hoy = timezone.localdate()
    inicio_mes = hoy.replace(day=1)
    util = Q(lote__activo=True, lote__fecha_vencimiento__gte=hoy)
    abiertas = Alerta.objects.filter(resuelta=False)

    kpis = {
        'productos': Producto.objects.filter(activo=True).count(),
        'unidades': StockLote.objects.filter(util).aggregate(t=Sum('cantidad'))['t'] or 0,
        'criticos': abiertas.filter(tipo=Alerta.Tipo.STOCK_CRITICO).count(),
        'por_vencer': abiertas.filter(tipo=Alerta.Tipo.PROXIMO_VENCER).count(),
        'vencidos': abiertas.filter(tipo=Alerta.Tipo.VENCIDO).count(),
        'alertas': abiertas.count(),
        'dispensaciones_hoy': Dispensacion.objects.filter(fecha__date=hoy).count(),
        'dispensaciones_mes': Dispensacion.objects.filter(fecha__date__gte=inicio_mes).count(),
        'recetas_mes': Dispensacion.objects.filter(fecha__date__gte=inicio_mes).values('receta').distinct().count(),
        'pacientes_programa': InscripcionPrograma.objects.filter(activo=True).values('paciente').distinct().count(),
    }

    util_cat = Q(productos__lotes__activo=True, productos__lotes__fecha_vencimiento__gte=hoy)
    categorias = Categoria.objects.annotate(
        u=Coalesce(Sum('productos__lotes__stocks__cantidad', filter=util_cat), 0, output_field=IntegerField())
    ).order_by('-u', 'nombre')
    stock_categoria = {'labels': [c.nombre for c in categorias], 'valores': [c.u for c in categorias]}

    top = (DispensacionItem.objects.filter(dispensacion__fecha__date__gte=hoy - timedelta(days=30))
           .values('producto__nombre').annotate(t=Sum('cantidad')).order_by('-t')[:8])
    top_productos = {'labels': [r['producto__nombre'] for r in top], 'valores': [r['t'] for r in top]}

    inicio = hoy - timedelta(days=13)
    por_dia = {r['dia']: r['n'] for r in Dispensacion.objects.filter(fecha__date__gte=inicio)
               .annotate(dia=TruncDate('fecha')).values('dia').annotate(n=Count('id'))}
    dias = [inicio + timedelta(days=i) for i in range(14)]
    dispensaciones_dia = {'labels': [d.strftime('%d/%m') for d in dias], 'valores': [por_dia.get(d, 0) for d in dias]}

    prog = (Dispensacion.objects.filter(fecha__date__gte=inicio_mes).values('programa__nombre')
            .annotate(n=Count('id')).order_by('-n'))
    por_programa = {'labels': [r['programa__nombre'] or 'Atención estándar' for r in prog],
                    'valores': [r['n'] for r in prog]}

    recientes = [{'severidad': a.get_severidad_display(), 'tipo': a.get_tipo_display(), 'mensaje': a.mensaje,
                  'fecha': timezone.localtime(a.creada_en).strftime('%d/%m %H:%M')}
                 for a in abiertas.order_by('severidad', '-creada_en')[:8]]

    inteligencia = None
    if request.user.puede('ver_analitica'):
        ab = analitica.resumen_abastecimiento(analitica.analizar_abastecimiento(hoy=hoy))
        ad = analitica.resumen_adherencia(analitica.analizar_adherencia(hoy=hoy))
        inteligencia = {'quiebres': ab['quiebres'] + ab['criticos'], 'en_riesgo': ab['unidades_en_riesgo'],
                        'atrasados': ad['atrasados'], 'abandono': ad['abandono']}

    return JsonResponse({
        'inteligencia': inteligencia, 'kpis': kpis, 'stock_categoria': stock_categoria, 'top_productos': top_productos,
        'dispensaciones_dia': dispensaciones_dia, 'por_programa': por_programa, 'alertas': recientes,
        'actualizado': timezone.localtime().strftime('%H:%M:%S'),
    })


@permiso_requerido('ver_reportes')
def indice(request):
    informes = [i for i in INFORMES.values() if request.user.puede(i.permiso)]
    return render(request, 'reportes/indice.html', {'titulo': 'Reportes', 'informes': informes})


@permiso_requerido('ver_reportes')
def informe(request, slug):
    definicion = INFORMES.get(slug)
    if definicion is None or not request.user.puede(definicion.permiso):
        raise Http404('Informe no disponible.')
    form = RangoFechasForm(request.GET)
    desde = hasta = None
    if definicion.usa_fechas and form.is_valid():
        desde, hasta = form.cleaned_data['desde'], form.cleaned_data['hasta']
    encabezados, filas = definicion.funcion(desde, hasta)
    filas = list(filas)

    formato = request.GET.get('formato')
    if formato in ('pdf', 'xlsx'):
        rango = ''
        if desde or hasta:
            rango = f' — período {desde.strftime("%d/%m/%Y") if desde else "inicio"} a ' \
                    f'{hasta.strftime("%d/%m/%Y") if hasta else "hoy"}'
        subtitulo = f'Generado el {timezone.localtime():%d/%m/%Y %H:%M} por {request.user.nombre_completo}{rango}'
        nombre = f'{slug}_{timezone.localdate():%Y%m%d}'
        registrar_auditoria(RegistroAuditoria.Accion.EXPORTAR, modelo='Reporte', objeto_id=slug,
                            descripcion=f'Exportación {formato.upper()}: {definicion.titulo}')
        if formato == 'pdf':
            return respuesta_pdf(definicion.titulo, encabezados, filas, nombre, subtitulo)
        return respuesta_excel(definicion.titulo, encabezados, filas, nombre, subtitulo)

    limite = 300
    return render(request, 'reportes/informe.html', {
        'titulo': definicion.titulo, 'definicion': definicion, 'form': form if definicion.usa_fechas else None,
        'encabezados': encabezados, 'filas': filas[:limite], 'total': len(filas), 'limite': limite,
        'querystring': request.GET.urlencode(),
    })
