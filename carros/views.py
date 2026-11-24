from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.utils import timezone

from core.views import CrearView, EditarView, EliminarView, ListaGenericaView, permiso_requerido

from . import services
from .forms import (CarroForm, CarroItemForm, ConsumoForm, ReposicionForm, SolicitudFiltro, SolicitudForm)
from .models import CarroClinico, CarroItem, ConsumoCarro, ReposicionCarro, SolicitudReposicion


class CarroLista(ListaGenericaView):
    permiso = 'ver_carros'
    permiso_edicion = 'configurar_carros'
    model = CarroClinico
    titulo = 'Carros clínicos'
    subtitulo = 'Carro de Paro y Carros Unidosis (tratamiento) de los servicios clínicos.'
    columnas = (('Nombre', 'nombre'), ('Tipo', 'tipo_texto'), ('Servicio', 'ubicacion'),
                ('Responsable', 'responsable'), ('Precinto', 'precinto'), ('Productos', 'total_items'),
                ('Con faltante', 'items_con_faltante'), ('Estado', 'estado_texto'), ('Activo', 'activo'))
    campos_busqueda = ('nombre', 'ubicacion')
    url_crear = 'carros:crear'
    etiqueta_crear = 'Nuevo carro'
    url_detalle = 'carros:detalle'
    url_editar = 'carros:editar'
    url_eliminar = 'carros:eliminar'


@permiso_requerido('ver_carros')
def detalle(request, pk):
    carro = get_object_or_404(CarroClinico.objects.select_related('responsable'), pk=pk)
    return render(request, 'carros/detalle.html', {
        'titulo': carro.nombre, 'carro': carro, 'items': carro.items.select_related('producto'),
        'reposiciones': carro.reposiciones.select_related('realizada_por')[:8],
        'consumos': carro.consumos.select_related('producto', 'registrado_por')[:8],
        'solicitudes': carro.solicitudes.select_related('solicitante')[:5],
    })


class CarroCrear(CrearView):
    permiso = 'configurar_carros'
    model = CarroClinico
    form_class = CarroForm
    titulo = 'Nuevo carro clínico'
    success_url = reverse_lazy('carros:lista')


class CarroEditar(EditarView):
    permiso = 'configurar_carros'
    model = CarroClinico
    form_class = CarroForm
    titulo = 'Editar carro clínico'
    success_url = reverse_lazy('carros:lista')


class CarroEliminar(EliminarView):
    permiso = 'configurar_carros'
    model = CarroClinico
    titulo = 'Eliminar carro clínico'
    success_url = reverse_lazy('carros:lista')


# ------------------------------------------------------------ Dotación
@permiso_requerido('configurar_carros')
def item_crear(request, carro_id):
    carro = get_object_or_404(CarroClinico, pk=carro_id)
    form = CarroItemForm(request.POST or None, carro=carro)
    if request.method == 'POST' and form.is_valid():
        item = form.save(commit=False)
        item.carro = carro
        item.save()
        messages.success(request, 'Producto agregado a la dotación. Realice una reposición para abastecerlo.')
        return redirect('carros:detalle', pk=carro.pk)
    return render(request, 'core/form.html', {
        'titulo': f'Agregar producto a {carro.nombre}', 'form': form,
        'url_cancelar': reverse('carros:detalle', args=[carro.pk])})


@permiso_requerido('configurar_carros')
def item_editar(request, pk):
    item = get_object_or_404(CarroItem.objects.select_related('carro', 'producto'), pk=pk)
    form = CarroItemForm(request.POST or None, instance=item, carro=item.carro)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Dotación actualizada.')
        return redirect('carros:detalle', pk=item.carro_id)
    return render(request, 'core/form.html', {
        'titulo': f'Editar dotación — {item.producto.nombre}', 'form': form,
        'url_cancelar': reverse('carros:detalle', args=[item.carro_id])})


@permiso_requerido('configurar_carros')
@require_POST
def item_eliminar(request, pk):
    item = get_object_or_404(CarroItem, pk=pk)
    carro_id = item.carro_id
    item.delete()
    messages.success(request, 'Producto retirado de la dotación.')
    return redirect('carros:detalle', pk=carro_id)


# ------------------------------------------------- Reposición / consumo
@permiso_requerido('gestionar_carros')
def reponer(request, pk):
    carro = get_object_or_404(CarroClinico, pk=pk, activo=True)
    form = ReposicionForm(request.POST or None, carro=carro)
    if request.method == 'POST' and form.is_valid():
        reposicion = services.reponer_carro(carro, form.conteo(), request.user, form.cleaned_data['observacion'])
        repuestas = sum(d.cantidad_repuesta for d in reposicion.detalles.all())
        messages.success(request, f'Reposición registrada: {repuestas} unidades repuestas desde inventario (FEFO).')
        return redirect('carros:detalle', pk=carro.pk)
    return render(request, 'core/form.html', {
        'titulo': f'Reposición con conteo — {carro.nombre}', 'form': form,
        'url_cancelar': reverse('carros:detalle', args=[carro.pk]),
        'ayuda': 'Cuente físicamente cada producto. El sistema registra las diferencias respecto de lo esperado '
                 'y completa la dotación usando el stock de bodega/vitrina con criterio FEFO.'})


@permiso_requerido('registrar_consumo')
def consumo(request, pk):
    carro = get_object_or_404(CarroClinico, pk=pk, activo=True)
    form = ConsumoForm(request.POST or None, carro=carro)
    if request.method == 'POST' and form.is_valid():
        datos = form.cleaned_data
        try:
            services.registrar_consumo(carro, datos['producto'], datos['cantidad'], request.user,
                                       datos['referencia'], datos['observacion'])
        except ValueError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, 'Consumo registrado.')
            return redirect('carros:detalle', pk=carro.pk)
    return render(request, 'core/form.html', {
        'titulo': f'Registrar consumo — {carro.nombre}', 'form': form,
        'url_cancelar': reverse('carros:detalle', args=[carro.pk])})


# ---------------------------------------------------------- Solicitudes
@permiso_requerido('solicitar_reposicion')
def solicitar(request, pk):
    carro = get_object_or_404(CarroClinico, pk=pk, activo=True)
    form = SolicitudForm(request.POST or None, carro=carro)
    if request.method == 'POST' and form.is_valid():
        try:
            solicitud = services.crear_solicitud(carro, request.user, form.cantidades(),
                                                 form.cleaned_data['observacion'])
        except ValueError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, f'Solicitud N° {solicitud.pk} registrada. Farmacia la atenderá a la brevedad.')
            return redirect('carros:solicitud_detalle', pk=solicitud.pk)
    return render(request, 'core/form.html', {
        'titulo': f'Solicitar reposición — {carro.nombre}', 'form': form,
        'url_cancelar': reverse('carros:detalle', args=[carro.pk])})


class SolicitudLista(ListaGenericaView):
    permiso = 'ver_carros'
    model = SolicitudReposicion
    titulo = 'Solicitudes de reposición de carros'
    columnas = (('N°', 'pk'), ('Fecha', 'creada_en'), ('Carro', 'carro'), ('Solicitante', 'solicitante.nombre_completo'),
                ('Estado', 'estado_texto'), ('Atendida por', 'atendida_por.username'), ('Observación', 'observacion'))
    campos_busqueda = ('carro__nombre', 'solicitante__username', 'observacion')
    form_filtro = SolicitudFiltro
    url_detalle = 'carros:solicitud_detalle'

    def get_queryset(self):
        self.queryset = SolicitudReposicion.objects.select_related('carro', 'solicitante', 'atendida_por')
        return super().get_queryset()

    def aplicar_filtros(self, qs, datos):
        if datos.get('estado'):
            qs = qs.filter(estado=datos['estado'])
        return qs


@permiso_requerido('ver_carros')
def solicitud_detalle(request, pk):
    solicitud = get_object_or_404(
        SolicitudReposicion.objects.select_related('carro', 'solicitante', 'atendida_por'), pk=pk)
    return render(request, 'carros/solicitud_detalle.html', {
        'titulo': f'Solicitud N° {solicitud.pk}', 'solicitud': solicitud,
        'detalles': solicitud.detalles.select_related('producto')})


@permiso_requerido('gestionar_carros')
@require_POST
def solicitud_atender(request, pk):
    solicitud = get_object_or_404(SolicitudReposicion, pk=pk)
    try:
        solicitud = services.atender_solicitud(solicitud, request.user)
    except ValueError as error:
        messages.error(request, str(error))
    else:
        if solicitud.estado == SolicitudReposicion.Estado.PARCIAL:
            messages.warning(request, 'Solicitud atendida parcialmente: hay faltantes de stock o dotación. '
                                      'Revise las alertas.')
        else:
            messages.success(request, 'Solicitud atendida y stock actualizado.')
    return redirect('carros:solicitud_detalle', pk=pk)


@permiso_requerido('gestionar_carros')
@require_POST
def solicitud_rechazar(request, pk):
    solicitud = get_object_or_404(SolicitudReposicion, pk=pk, estado=SolicitudReposicion.Estado.PENDIENTE)
    solicitud.estado = SolicitudReposicion.Estado.RECHAZADA
    solicitud.atendida_por = request.user
    solicitud.atendida_en = timezone.now()
    solicitud.save(update_fields=['estado', 'atendida_por', 'atendida_en'])
    messages.info(request, 'Solicitud rechazada.')
    return redirect('carros:solicitud_detalle', pk=pk)


@permiso_requerido('ver_carros')
def solicitud_orden(request, pk):
    """Orden de reposición imprimible."""
    solicitud = get_object_or_404(
        SolicitudReposicion.objects.select_related('carro', 'solicitante', 'atendida_por'), pk=pk)
    return render(request, 'carros/orden.html', {
        'solicitud': solicitud, 'detalles': solicitud.detalles.select_related('producto')})
