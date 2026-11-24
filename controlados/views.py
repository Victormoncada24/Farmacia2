from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST

from core.views import ListaGenericaView, permiso_requerido
from inventario.models import Producto
from inventario.services import stock_fisico_total

from . import services
from .forms import ConteoForm, LibroFiltro, ResolverConteoForm
from .models import ConteoFisico, MovimientoControlado


class LibroLista(ListaGenericaView):
    permiso = 'ver_controlados'
    template_name = 'controlados/libro.html'
    model = MovimientoControlado
    titulo = 'Libro digital de estupefacientes y psicotrópicos'
    subtitulo = 'Asientos correlativos con saldo. Cada asiento debe ser firmado por el Químico Farmacéutico.'
    columnas = (('Fecha y hora', 'fecha'), ('Producto', 'producto.nombre'), ('Lote', 'lote.numero_lote'),
                ('Movimiento', 'get_tipo_display'), ('Cantidad', 'cantidad'), ('Saldo', 'saldo_resultante'),
                ('Respaldo', 'referencia'), ('Paciente', 'paciente_documento'),
                ('Registró', 'registrado_por.username'), ('Firma', 'estado_firma'))
    campos_busqueda = ('producto__nombre', 'referencia', 'paciente_documento')
    form_filtro = LibroFiltro
    paginate_by = 40

    def get_queryset(self):
        self.queryset = MovimientoControlado.objects.select_related('producto', 'lote', 'registrado_por',
                                                                    'firmado_por')
        return super().get_queryset()

    def aplicar_filtros(self, qs, datos):
        if datos.get('producto'):
            qs = qs.filter(producto=datos['producto'])
        if datos.get('tipo'):
            qs = qs.filter(tipo=datos['tipo'])
        if datos.get('firma') == 'pendiente':
            qs = qs.filter(firmado_por__isnull=True)
        elif datos.get('firma') == 'firmado':
            qs = qs.filter(firmado_por__isnull=False)
        if datos.get('desde'):
            qs = qs.filter(fecha__date__gte=datos['desde'])
        if datos.get('hasta'):
            qs = qs.filter(fecha__date__lte=datos['hasta'])
        return qs


@permiso_requerido('autorizar')
@require_POST
def firmar(request, pk):
    movimiento = get_object_or_404(MovimientoControlado, pk=pk)
    if services.firmar(movimiento, request.user):
        messages.success(request, 'Asiento firmado.')
    else:
        messages.info(request, 'El asiento ya estaba firmado.')
    return redirect(request.META.get('HTTP_REFERER') or 'controlados:libro')


@permiso_requerido('autorizar')
@require_POST
def firmar_pendientes(request):
    total = 0
    for movimiento in MovimientoControlado.objects.filter(firmado_por__isnull=True):
        if services.firmar(movimiento, request.user):
            total += 1
    messages.success(request, f'Se firmaron {total} asientos pendientes.')
    return redirect('controlados:libro')


@permiso_requerido('ver_controlados')
def cuadratura(request):
    filas = []
    for producto in Producto.objects.filter(activo=True).exclude(control=Producto.Control.NINGUNO).order_by('nombre'):
        libro = services.saldo_libro(producto)
        sistema = stock_fisico_total(producto)
        ultimo = producto.conteos.first()
        filas.append({'producto': producto, 'libro': libro, 'sistema': sistema,
                      'diferencia': sistema - libro, 'ultimo_conteo': ultimo})
    conteos = ConteoFisico.objects.select_related('producto', 'registrado_por')[:30]
    return render(request, 'controlados/cuadratura.html', {
        'titulo': 'Cuadratura de medicamentos controlados', 'filas': filas, 'conteos': conteos,
    })


@permiso_requerido('autorizar')
def conteo_nuevo(request):
    form = ConteoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        conteo = services.registrar_conteo(
            producto=form.cleaned_data['producto'], cantidad_contada=form.cleaned_data['cantidad_contada'],
            usuario=request.user, observacion=form.cleaned_data['observacion'])
        if conteo.diferencia:
            messages.warning(request, f'Conteo registrado con diferencia de {conteo.diferencia:+d}. Se generó una alerta.')
        else:
            messages.success(request, 'Conteo registrado: el stock cuadra con el libro.')
        return redirect('controlados:cuadratura')
    return render(request, 'core/form.html', {
        'titulo': 'Registrar conteo físico', 'form': form, 'url_cancelar': reverse_lazy('controlados:cuadratura'),
    })


@permiso_requerido('autorizar')
def conteo_resolver(request, pk):
    conteo = get_object_or_404(ConteoFisico, pk=pk)
    form = ResolverConteoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        services.resolver_conteo(conteo, request.user, form.cleaned_data['nota'])
        messages.success(request, 'Descuadre regularizado.')
        return redirect('controlados:cuadratura')
    return render(request, 'core/form.html', {
        'titulo': f'Regularizar descuadre: {conteo.producto.nombre}', 'form': form,
        'url_cancelar': reverse_lazy('controlados:cuadratura'),
        'ayuda': f'Diferencia registrada: {conteo.diferencia:+d} (contado {conteo.cantidad_contada}, libro {conteo.saldo_libro}).',
    })
