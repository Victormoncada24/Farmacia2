from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.views import CrearView, EditarView, EliminarView, ListaGenericaView, permiso_requerido

from . import services
from .forms import (PedidoFiltro, PedidoForm, PedidoItemFormSet, ProveedorFiltro, ProveedorForm,
                    RecepcionForm)
from .models import Pedido, Proveedor
from .services import PedidoError


# ------------------------------------------------------------ Proveedores
class ProveedorLista(ListaGenericaView):
    permiso = 'ver_pedidos'
    permiso_edicion = 'gestionar_proveedores'
    model = Proveedor
    titulo = 'Proveedores de medicamentos e insumos'
    subtitulo = 'Entidades a las que el establecimiento solicita abastecimiento (CENABAST, Servicio de Salud, etc.).'
    columnas = (('Nombre', 'nombre'), ('Tipo', 'get_tipo_display'), ('RUT', 'rut'), ('Contacto', 'contacto'),
                ('Teléfono', 'telefono'), ('Correo', 'email'), ('Plazo (días)', 'plazo_entrega_dias'),
                ('Activo', 'activo'))
    campos_busqueda = ('nombre', 'rut', 'contacto')
    form_filtro = ProveedorFiltro
    url_crear = 'pedidos:proveedor_crear'
    etiqueta_crear = 'Nuevo proveedor'
    url_editar = 'pedidos:proveedor_editar'
    url_eliminar = 'pedidos:proveedor_eliminar'

    def aplicar_filtros(self, qs, datos):
        if datos.get('tipo'):
            qs = qs.filter(tipo=datos['tipo'])
        return qs


class ProveedorCrear(CrearView):
    permiso = 'gestionar_proveedores'
    model = Proveedor
    form_class = ProveedorForm
    titulo = 'Nuevo proveedor'
    success_url = reverse_lazy('pedidos:proveedor_lista')


class ProveedorEditar(EditarView):
    permiso = 'gestionar_proveedores'
    model = Proveedor
    form_class = ProveedorForm
    titulo = 'Editar proveedor'
    success_url = reverse_lazy('pedidos:proveedor_lista')


class ProveedorEliminar(EliminarView):
    permiso = 'gestionar_proveedores'
    model = Proveedor
    titulo = 'Eliminar proveedor'
    success_url = reverse_lazy('pedidos:proveedor_lista')


# ---------------------------------------------------------------- Pedidos
class PedidoLista(ListaGenericaView):
    permiso = 'ver_pedidos'
    permiso_edicion = 'gestionar_pedidos'
    model = Pedido
    titulo = 'Pedidos a proveedores'
    subtitulo = 'Solicitudes de abastecimiento: borrador → autorización del Q.F. → envío → recepción contra el pedido.'
    columnas = (('N°', 'numero'), ('Fecha', 'fecha'), ('Proveedor', 'proveedor'), ('Prioridad', 'get_prioridad_display'),
                ('Estado', 'estado_texto'), ('Productos', 'total_items'), ('Recibido', 'avance_texto'),
                ('Entrega estimada', 'fecha_entrega_estimada'), ('Atraso', 'atraso_texto'),
                ('Creó', 'creado_por.username'))
    campos_busqueda = ('numero', 'proveedor__nombre', 'observacion')
    form_filtro = PedidoFiltro
    url_crear = 'pedidos:crear'
    etiqueta_crear = 'Nuevo pedido'
    url_detalle = 'pedidos:detalle'

    def get_queryset(self):
        self.queryset = Pedido.objects.select_related('proveedor', 'creado_por').prefetch_related('items')
        return super().get_queryset()

    def aplicar_filtros(self, qs, datos):
        if datos.get('estado'):
            qs = qs.filter(estado=datos['estado'])
        if datos.get('proveedor'):
            qs = qs.filter(proveedor=datos['proveedor'])
        if datos.get('atrasados'):
            qs = qs.filter(estado__in=['ENVIADO', 'PARCIAL'], fecha_entrega_estimada__lt=timezone.localdate())
        if datos.get('desde'):
            qs = qs.filter(fecha__date__gte=datos['desde'])
        if datos.get('hasta'):
            qs = qs.filter(fecha__date__lte=datos['hasta'])
        return qs


def _formulario(request, pedido, titulo):
    form = PedidoForm(request.POST or None, instance=pedido)
    formset = PedidoItemFormSet(request.POST or None, instance=pedido, prefix='items')
    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        activos = [f for f in formset.forms if f.cleaned_data and not f.cleaned_data.get('DELETE')]
        if not activos:
            form.add_error(None, 'El pedido debe incluir al menos un producto.')
        else:
            with transaction.atomic():
                pedido = form.save()
                formset.instance = pedido
                formset.save()
            messages.success(request, f'Pedido {pedido.numero} guardado como borrador. '
                                      'El Químico Farmacéutico debe autorizarlo para enviarlo.')
            return redirect('pedidos:detalle', pk=pedido.pk)
    return render(request, 'pedidos/pedido_form.html', {
        'titulo': titulo, 'form': form, 'formset': formset,
        'url_cancelar': reverse('pedidos:detalle', args=[pedido.pk]) if pedido.pk else reverse('pedidos:lista'),
    })


@permiso_requerido('gestionar_pedidos')
def crear(request):
    if not Proveedor.objects.filter(activo=True).exists():
        messages.warning(request, 'Primero debe existir al menos un proveedor activo.')
        return redirect('pedidos:proveedor_lista')
    return _formulario(request, Pedido(creado_por=request.user), 'Nuevo pedido a proveedor')


@permiso_requerido('gestionar_pedidos')
def editar(request, pk):
    pedido = get_object_or_404(Pedido, pk=pk)
    if not pedido.editable:
        messages.error(request, 'Solo se pueden editar pedidos en borrador.')
        return redirect('pedidos:detalle', pk=pk)
    return _formulario(request, pedido, f'Editar pedido {pedido.numero}')


@permiso_requerido('ver_pedidos')
def detalle(request, pk):
    pedido = get_object_or_404(Pedido.objects.select_related('proveedor', 'creado_por', 'aprobado_por'), pk=pk)
    return render(request, 'pedidos/detalle.html', {
        'titulo': f'Pedido {pedido.numero}', 'pedido': pedido,
        'items': pedido.items.select_related('producto'),
        'recepciones': pedido.recepciones.select_related('recibido_por').prefetch_related('items__producto', 'items__lote'),
    })


@permiso_requerido('gestionar_pedidos')
@require_POST
def eliminar(request, pk):
    pedido = get_object_or_404(Pedido, pk=pk)
    if not pedido.editable:
        messages.error(request, 'Solo se pueden eliminar borradores. Para los demás use «Anular».')
        return redirect('pedidos:detalle', pk=pk)
    numero = pedido.numero
    pedido.delete()
    messages.success(request, f'Borrador {numero} eliminado.')
    return redirect('pedidos:lista')


@permiso_requerido('autorizar')
@require_POST
def enviar(request, pk):
    pedido = get_object_or_404(Pedido, pk=pk)
    try:
        pedido = services.enviar_pedido(pedido, request.user)
    except PedidoError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f'Pedido {pedido.numero} autorizado y enviado a {pedido.proveedor.nombre}. '
                                  f'Entrega estimada: {pedido.fecha_entrega_estimada:%d/%m/%Y}.')
    return redirect('pedidos:detalle', pk=pk)


@permiso_requerido('autorizar')
@require_POST
def anular(request, pk):
    pedido = get_object_or_404(Pedido, pk=pk)
    motivo = (request.POST.get('motivo') or '').strip()
    if not motivo:
        messages.error(request, 'Debe indicar el motivo de la anulación.')
    else:
        try:
            services.anular_pedido(pedido, request.user, motivo[:250])
        except PedidoError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, 'Pedido anulado.')
    return redirect('pedidos:detalle', pk=pk)


@permiso_requerido('autorizar')
@require_POST
def cerrar(request, pk):
    pedido = get_object_or_404(Pedido, pk=pk)
    motivo = (request.POST.get('motivo') or '').strip()
    if not motivo:
        messages.error(request, 'Debe indicar el motivo del cierre.')
    else:
        try:
            services.cerrar_pedido(pedido, request.user, motivo[:250])
        except PedidoError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, 'Pedido cerrado con faltantes.')
    return redirect('pedidos:detalle', pk=pk)


@permiso_requerido('gestionar_pedidos')
def recepcionar(request, pk):
    pedido = get_object_or_404(Pedido.objects.select_related('proveedor'), pk=pk)
    if not pedido.abierto:
        messages.error(request, f'El pedido no admite recepciones (estado: {pedido.estado_texto}).')
        return redirect('pedidos:detalle', pk=pk)
    form = RecepcionForm(request.POST or None, pedido=pedido)
    if request.method == 'POST' and form.is_valid():
        try:
            services.recibir_pedido(
                pedido=pedido, lineas=form.lineas(), usuario=request.user, ubicacion=form.cleaned_data['ubicacion'],
                documento_ref=form.cleaned_data['documento_ref'], observacion=form.cleaned_data['observacion'])
        except PedidoError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, 'Recepción registrada: el stock y los lotes fueron actualizados.')
            return redirect('pedidos:detalle', pk=pk)
    return render(request, 'pedidos/recepcionar.html', {
        'titulo': f'Recepcionar mercadería — {pedido.numero}', 'pedido': pedido, 'form': form})


@permiso_requerido('gestionar_pedidos')
@require_POST
def desde_sugerencia(request):
    """Crea un borrador con los productos que el módulo de abastecimiento inteligente recomienda pedir."""
    proveedor = get_object_or_404(Proveedor, pk=request.POST.get('proveedor') or 0, activo=True)

    def entero(nombre, defecto):
        try:
            return max(int(request.POST.get(nombre, defecto)), 1)
        except (TypeError, ValueError):
            return defecto

    try:
        pedido = services.pedido_desde_sugerencia(
            proveedor=proveedor, usuario=request.user, dias=entero('dias', 30), lead_time=entero('lead_time', 15),
            dias_objetivo=entero('dias_objetivo', 60), solo_criticos=request.POST.get('alcance') == 'criticos')
    except PedidoError as error:
        messages.warning(request, str(error))
        return redirect('analitica:abastecimiento')
    messages.success(request, f'Borrador {pedido.numero} creado con {pedido.total_items} productos. '
                              'Revise las cantidades y solicite la autorización del Químico Farmacéutico.')
    return redirect('pedidos:detalle', pk=pedido.pk)


@permiso_requerido('ver_pedidos')
def orden(request, pk):
    """Orden de pedido imprimible."""
    pedido = get_object_or_404(Pedido.objects.select_related('proveedor', 'creado_por', 'aprobado_por'), pk=pk)
    return render(request, 'pedidos/orden.html', {'pedido': pedido, 'items': pedido.items.select_related('producto')})
