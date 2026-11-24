import mimetypes
import os

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from auditoria.models import RegistroAuditoria
from auditoria.services import registrar as registrar_auditoria
from core.utils import normalizar_rut
from core.views import ListaGenericaView, permiso_requerido
from inventario.models import Producto, Ubicacion
from inventario.services import stock_disponible
from pacientes.models import InscripcionPrograma, Paciente

from . import services
from .forms import (AnularRecetaForm, DispensacionForm, HistorialFiltro, RecetaFiltro, RecetaForm,
                    RecetaItemFormSet)
from .models import Dispensacion, Receta


# ----------------------------------------------------- Búsqueda de paciente
@permiso_requerido('dispensar')
def nueva(request):
    """Punto de partida de una dispensación: buscar paciente por RUT/DNI o nombre."""
    texto = (request.GET.get('documento') or '').strip()
    paciente, resultados, recetas = None, [], []
    if texto:
        paciente = Paciente.objects.filter(documento__in=[texto.upper(), normalizar_rut(texto)]).first()
        if paciente is None:
            resultados = list(Paciente.objects.filter(
                Q(nombres__icontains=texto) | Q(apellidos__icontains=texto) | Q(documento__icontains=texto)
            )[:10])
            if len(resultados) == 1:
                paciente, resultados = resultados[0], []
        if paciente:
            recetas = paciente.recetas.select_related('programa')[:15]
    return render(request, 'dispensacion/nueva.html', {
        'titulo': 'Nueva dispensación', 'texto': texto, 'paciente': paciente,
        'resultados': resultados, 'recetas': recetas,
    })


# ------------------------------------------------------------------ Recetas
@permiso_requerido('dispensar')
def receta_crear(request, paciente_id):
    paciente = get_object_or_404(Paciente, pk=paciente_id, activo=True)
    receta = Receta(paciente=paciente, registrada_por=request.user)
    form = RecetaForm(request.POST or None, request.FILES or None, instance=receta, paciente=paciente)
    formset = RecetaItemFormSet(request.POST or None, instance=receta, prefix='items')
    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        productos = [f.cleaned_data['producto'] for f in formset.forms
                     if f.cleaned_data and not f.cleaned_data.get('DELETE')]
        if not productos:
            form.add_error(None, 'La receta debe incluir al menos un medicamento.')
        elif any(p.es_controlado for p in productos) and form.cleaned_data['modalidad'] != Receta.Modalidad.RETENIDA:
            form.add_error('modalidad', 'La receta incluye medicamentos controlados: debe registrarse como RETENIDA.')
        else:
            with transaction.atomic():
                receta = form.save()
                formset.instance = receta
                formset.save()
            messages.success(request, 'Receta registrada y validada.')
            return redirect('dispensacion:receta_detalle', pk=receta.pk)
    return render(request, 'dispensacion/receta_form.html', {
        'titulo': f'Registrar receta — {paciente.nombre_completo}', 'paciente': paciente,
        'form': form, 'formset': formset,
    })


@permiso_requerido('ver_dispensaciones')
def receta_detalle(request, pk):
    receta = get_object_or_404(Receta.objects.select_related('paciente', 'programa', 'registrada_por'), pk=pk)
    return render(request, 'dispensacion/receta_detalle.html', {
        'titulo': f'Receta {receta.numero}', 'receta': receta,
        'items': receta.items.select_related('producto'),
        'dispensaciones': receta.dispensaciones.select_related('dispensado_por'),
        'form_anular': AnularRecetaForm(),
    })


@permiso_requerido('autorizar')
@require_POST
def receta_anular(request, pk):
    receta = get_object_or_404(Receta, pk=pk)
    form = AnularRecetaForm(request.POST)
    if form.is_valid():
        services.anular_receta(receta, request.user, form.cleaned_data['motivo'])
        messages.success(request, 'Receta anulada.')
    else:
        messages.error(request, 'Debe indicar el motivo de la anulación.')
    return redirect('dispensacion:receta_detalle', pk=pk)


@permiso_requerido('ver_dispensaciones')
def receta_archivo(request, pk):
    """Entrega el archivo adjunto solo a usuarios autorizados (los archivos no son públicos)."""
    receta = get_object_or_404(Receta, pk=pk)
    if not receta.archivo:
        raise Http404('La receta no tiene archivo adjunto.')
    try:
        archivo = receta.archivo.open('rb')
    except FileNotFoundError:
        raise Http404('Archivo no encontrado.')
    registrar_auditoria(RegistroAuditoria.Accion.ACCESO, modelo='Receta', objeto_id=receta.pk,
                        descripcion=f'Visualización de archivo de receta {receta.numero}')
    tipo, _ = mimetypes.guess_type(receta.archivo.name)
    respuesta = FileResponse(archivo, content_type=tipo or 'application/octet-stream')
    respuesta['Content-Disposition'] = f'inline; filename="receta_{receta.numero}{os.path.splitext(receta.archivo.name)[1]}"'
    respuesta['X-Content-Type-Options'] = 'nosniff'
    return respuesta


class RecetaLista(ListaGenericaView):
    permiso = 'ver_dispensaciones'
    model = Receta
    titulo = 'Recetas registradas'
    columnas = (('Fecha emisión', 'fecha_emision'), ('N° receta', 'numero'), ('Paciente', 'paciente.nombre_completo'),
                ('Documento', 'paciente.documento'), ('Médico', 'medico_nombre'),
                ('Modalidad', 'get_modalidad_display'), ('Programa', 'programa'), ('Vence', 'fecha_vencimiento'),
                ('Estado', 'estado_texto'))
    campos_busqueda = ('numero', 'paciente__documento', 'paciente__nombres', 'paciente__apellidos', 'medico_nombre')
    form_filtro = RecetaFiltro
    url_detalle = 'dispensacion:receta_detalle'

    def get_queryset(self):
        self.queryset = Receta.objects.select_related('paciente', 'programa')
        return super().get_queryset()

    def aplicar_filtros(self, qs, datos):
        if datos.get('modalidad'):
            qs = qs.filter(modalidad=datos['modalidad'])
        if datos.get('anuladas'):
            qs = qs.filter(estado=Receta.Estado.ANULADA)
        return qs


# -------------------------------------------------------------- Dispensación
@permiso_requerido('dispensar')
def dispensar(request, receta_id):
    receta = get_object_or_404(Receta.objects.select_related('paciente', 'programa'), pk=receta_id)
    form = DispensacionForm(request.POST or None, receta=receta, usuario=request.user)
    if request.method == 'POST' and form.is_valid():
        datos = form.cleaned_data
        try:
            dispensacion = services.dispensar(
                receta=receta, cantidades=form.cantidades(), usuario=request.user,
                retira_tercero=datos.get('retira_tercero', False), retiro_nombre=datos.get('retiro_nombre', ''),
                retiro_rut=datos.get('retiro_rut', ''), retiro_parentesco=datos.get('retiro_parentesco', ''),
                observacion=datos.get('observacion', ''), excepcion_cuota=datos.get('excepcion_cuota', False))
        except services.DispensacionError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, f'Dispensación N° {dispensacion.pk} registrada y stock actualizado.')
            return redirect('dispensacion:detalle', pk=dispensacion.pk)

    inscripcion = None
    if receta.programa_id:
        inscripcion = InscripcionPrograma.objects.filter(
            paciente=receta.paciente, programa=receta.programa, activo=True).first()
    filas = []
    for item in receta.items.select_related('producto'):
        cuota = inscripcion.cuotas.filter(producto=item.producto).first() if inscripcion else None
        filas.append({
            'item': item, 'campo': form[f'item_{item.pk}'],
            'vitrina': stock_disponible(item.producto, (Ubicacion.VITRINA,)),
            'bodega': stock_disponible(item.producto, (Ubicacion.BODEGA,)),
            'cuota': cuota, 'saldo_cuota': cuota.saldo_mes() if cuota else None,
        })
    return render(request, 'dispensacion/dispensar.html', {
        'titulo': f'Dispensar — receta {receta.numero}', 'receta': receta, 'paciente': receta.paciente,
        'form': form, 'filas': filas, 'inscripcion': inscripcion,
    })


class HistorialLista(ListaGenericaView):
    permiso = 'ver_dispensaciones'
    model = Dispensacion
    titulo = 'Historial de dispensaciones'
    columnas = (('N°', 'pk'), ('Fecha y hora', 'fecha'), ('Paciente', 'paciente.nombre_completo'),
                ('Documento', 'paciente.documento'), ('Programa', 'programa_texto'), ('Medicamentos', 'resumen_items'),
                ('Retira', 'quien_retira'), ('Dispensó', 'dispensado_por.username'))
    campos_busqueda = ('paciente__documento', 'paciente__nombres', 'paciente__apellidos', 'receta__numero')
    form_filtro = HistorialFiltro
    url_detalle = 'dispensacion:detalle'

    def get_queryset(self):
        self.queryset = Dispensacion.objects.select_related('paciente', 'programa', 'dispensado_por')
        return super().get_queryset()

    def aplicar_filtros(self, qs, datos):
        if datos.get('programa'):
            qs = qs.filter(programa=datos['programa'])
        if datos.get('desde'):
            qs = qs.filter(fecha__date__gte=datos['desde'])
        if datos.get('hasta'):
            qs = qs.filter(fecha__date__lte=datos['hasta'])
        return qs


@permiso_requerido('ver_dispensaciones')
def detalle(request, pk):
    dispensacion = get_object_or_404(
        Dispensacion.objects.select_related('paciente', 'programa', 'receta', 'dispensado_por', 'autorizado_por'), pk=pk)
    return render(request, 'dispensacion/detalle.html', {
        'titulo': f'Dispensación N° {dispensacion.pk}', 'd': dispensacion,
        'items': dispensacion.items.select_related('producto', 'lote'),
    })


@permiso_requerido('ver_dispensaciones')
def comprobante(request, pk):
    """Orden / comprobante de entrega imprimible con plantilla fija."""
    dispensacion = get_object_or_404(
        Dispensacion.objects.select_related('paciente', 'programa', 'receta', 'dispensado_por'), pk=pk)
    return render(request, 'dispensacion/comprobante.html', {
        'd': dispensacion, 'items': dispensacion.items.select_related('producto', 'lote'),
    })
