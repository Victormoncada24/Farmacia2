from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.db.models import F, IntegerField, Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import DetailView

from core.views import (CrearView, EditarView, EliminarView, ListaGenericaView, RolRequeridoMixin,
                        permiso_requerido)

from . import services
from .forms import (AjusteForm, CategoriaForm, IngresoLoteForm, LoteFiltro, MovimientoFiltro, ProductoFiltro,
                    ProductoForm, StockFiltro, TransferenciaForm)
from .models import Categoria, Lote, MovimientoInventario, Producto, Ubicacion


# ---------------------------------------------------------------- Stock
class StockLista(ListaGenericaView):
    permiso = 'ver_inventario'
    template_name = 'core/lista.html'
    titulo = 'Stock de medicamentos e insumos'
    subtitulo = 'Existencias utilizables (excluye lotes vencidos), separadas por bodega y vitrina.'
    columnas = (('Código', 'codigo'), ('Producto', '__str__'), ('Categoría', 'categoria'),
                ('Bodega', 'stock_bodega'), ('Vitrina', 'stock_vitrina'), ('Total', 'stock_total'),
                ('Mínimo', 'stock_minimo'), ('Próx. vencimiento', 'proximo_vencimiento'),
                ('Estado', 'estado_stock_texto'))
    campos_busqueda = ('nombre', 'codigo', 'principio_activo', 'codigo_barras')
    form_filtro = StockFiltro
    url_detalle = 'inventario:producto_detalle'

    def get_queryset(self):
        self.queryset = Producto.objects.filter(activo=True).select_related('categoria').con_stock()
        return super().get_queryset()

    def aplicar_filtros(self, qs, datos):
        if datos.get('categoria'):
            qs = qs.filter(categoria=datos['categoria'])
        if datos.get('estado') == 'critico':
            qs = qs.filter(stock_minimo__gt=0, stock_total__lte=F('stock_minimo'))
        elif datos.get('estado') == 'sin_stock':
            qs = qs.filter(stock_total=0)
        return qs


# ------------------------------------------------------------- Productos
class ProductoLista(ListaGenericaView):
    permiso = 'ver_inventario'
    permiso_edicion = 'editar_catalogo'
    model = Producto
    titulo = 'Catálogo de productos'
    columnas = (('Código', 'codigo'), ('Nombre', 'nombre'), ('Presentación', 'presentacion'),
                ('Categoría', 'categoria'), ('Tipo', 'get_tipo_display'), ('Control ISP', 'get_control_display'),
                ('Stock mínimo', 'stock_minimo'), ('Activo', 'activo'))
    campos_busqueda = ('nombre', 'codigo', 'principio_activo', 'codigo_barras')
    form_filtro = ProductoFiltro
    url_crear = 'inventario:producto_crear'
    etiqueta_crear = 'Nuevo producto'
    url_detalle = 'inventario:producto_detalle'
    url_editar = 'inventario:producto_editar'
    url_eliminar = 'inventario:producto_eliminar'

    def get_queryset(self):
        self.queryset = Producto.objects.select_related('categoria')
        return super().get_queryset()

    def aplicar_filtros(self, qs, datos):
        if datos.get('categoria'):
            qs = qs.filter(categoria=datos['categoria'])
        if datos.get('solo_controlados'):
            qs = qs.exclude(control=Producto.Control.NINGUNO)
        return qs


class ProductoDetalle(RolRequeridoMixin, DetailView):
    permiso = 'ver_inventario'
    template_name = 'inventario/producto_detalle.html'
    context_object_name = 'producto'

    def get_queryset(self):
        return Producto.objects.select_related('categoria').con_stock()

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        producto = self.object
        contexto['titulo'] = str(producto)
        contexto['lotes'] = (
            producto.lotes.annotate(
                s_bodega=Coalesce(Sum('stocks__cantidad', filter=Q(stocks__ubicacion=Ubicacion.BODEGA)), 0,
                                  output_field=IntegerField()),
                s_vitrina=Coalesce(Sum('stocks__cantidad', filter=Q(stocks__ubicacion=Ubicacion.VITRINA)), 0,
                                   output_field=IntegerField()),
            ).order_by('fecha_vencimiento'))
        contexto['movimientos'] = producto.movimientos.select_related('lote', 'usuario')[:15]
        return contexto


class ProductoCrear(CrearView):
    permiso = 'editar_catalogo'
    model = Producto
    form_class = ProductoForm
    titulo = 'Nuevo producto'
    success_url = reverse_lazy('inventario:producto_lista')


class ProductoEditar(EditarView):
    permiso = 'editar_catalogo'
    model = Producto
    form_class = ProductoForm
    titulo = 'Editar producto'
    success_url = reverse_lazy('inventario:producto_lista')


class ProductoEliminar(EliminarView):
    permiso = 'editar_catalogo'
    model = Producto
    titulo = 'Eliminar producto'
    success_url = reverse_lazy('inventario:producto_lista')


# ------------------------------------------------------------ Categorías
class CategoriaLista(ListaGenericaView):
    permiso = 'ver_inventario'
    permiso_edicion = 'editar_catalogo'
    model = Categoria
    titulo = 'Categorías de productos'
    columnas = (('Nombre', 'nombre'), ('Descripción', 'descripcion'))
    campos_busqueda = ('nombre',)
    url_crear = 'inventario:categoria_crear'
    etiqueta_crear = 'Nueva categoría'
    url_editar = 'inventario:categoria_editar'
    url_eliminar = 'inventario:categoria_eliminar'


class CategoriaCrear(CrearView):
    permiso = 'editar_catalogo'
    model = Categoria
    form_class = CategoriaForm
    titulo = 'Nueva categoría'
    success_url = reverse_lazy('inventario:categoria_lista')


class CategoriaEditar(EditarView):
    permiso = 'editar_catalogo'
    model = Categoria
    form_class = CategoriaForm
    titulo = 'Editar categoría'
    success_url = reverse_lazy('inventario:categoria_lista')


class CategoriaEliminar(EliminarView):
    permiso = 'editar_catalogo'
    model = Categoria
    titulo = 'Eliminar categoría'
    success_url = reverse_lazy('inventario:categoria_lista')


# ----------------------------------------------------------------- Lotes
class LoteLista(ListaGenericaView):
    permiso = 'ver_inventario'
    titulo = 'Lotes y fechas de vencimiento'
    subtitulo = 'Ordenados por vencimiento (criterio FEFO: primero en vencer, primero en salir).'
    columnas = (('Producto', 'producto'), ('Lote', 'numero_lote'), ('Vencimiento', 'fecha_vencimiento'),
                ('Días', 'dias_para_vencer'), ('Bodega', 's_bodega'), ('Vitrina', 's_vitrina'),
                ('Total', 's_total'), ('Origen', 'get_origen_display'), ('Estado', 'estado_vencimiento_texto'))
    campos_busqueda = ('producto__nombre', 'numero_lote', 'documento_ref')
    form_filtro = LoteFiltro
    url_detalle = None

    def get_queryset(self):
        entero = IntegerField()
        self.queryset = Lote.objects.select_related('producto').annotate(
            s_bodega=Coalesce(Sum('stocks__cantidad', filter=Q(stocks__ubicacion=Ubicacion.BODEGA)), 0,
                              output_field=entero),
            s_vitrina=Coalesce(Sum('stocks__cantidad', filter=Q(stocks__ubicacion=Ubicacion.VITRINA)), 0,
                               output_field=entero),
        ).annotate(s_total=F('s_bodega') + F('s_vitrina')).order_by('fecha_vencimiento', 'id')
        return super().get_queryset()

    def aplicar_filtros(self, qs, datos):
        hoy = timezone.localdate()
        critico = hoy + timedelta(days=settings.ALERTA_VENCIMIENTO_CRITICO_DIAS)
        proximo = hoy + timedelta(days=settings.ALERTA_VENCIMIENTO_DIAS)
        estado = datos.get('estado')
        if estado == 'vencido':
            qs = qs.filter(fecha_vencimiento__lt=hoy)
        elif estado == 'critico':
            qs = qs.filter(fecha_vencimiento__gte=hoy, fecha_vencimiento__lte=critico)
        elif estado == 'proximo':
            qs = qs.filter(fecha_vencimiento__gt=critico, fecha_vencimiento__lte=proximo)
        elif estado == 'vigente':
            qs = qs.filter(fecha_vencimiento__gt=proximo)
        if datos.get('con_stock'):
            qs = qs.filter(s_total__gt=0)
        return qs


@permiso_requerido('mover_inventario')
def ingreso_lote(request):
    form = IngresoLoteForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        datos = form.cleaned_data
        try:
            lote = services.ingresar_lote(
                producto=datos['producto'], numero_lote=datos['numero_lote'].strip(),
                fecha_vencimiento=datos['fecha_vencimiento'], cantidad=datos['cantidad'],
                ubicacion=datos['ubicacion'], usuario=request.user, origen=datos['origen'],
                documento_ref=datos['documento_ref'], observacion=datos['observacion'])
        except ValueError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, f'Ingreso registrado: {lote}.')
            return redirect('inventario:lote_lista')
    return render(request, 'core/form.html', {
        'titulo': 'Ingreso de lote / recepción de remesa', 'form': form,
        'url_cancelar': reverse_lazy('inventario:lote_lista'),
        'ayuda': 'Registra la recepción de mercadería (CENABAST, Servicio de Salud u otros) con su lote y '
                 'vencimiento. Si el producto es controlado, se anota automáticamente en el libro digital.',
    })


@permiso_requerido('mover_inventario')
def transferir(request):
    form = TransferenciaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        datos = form.cleaned_data
        try:
            services.transferir(lote=datos['lote'], origen=datos['origen'], destino=datos['destino'],
                                cantidad=datos['cantidad'], usuario=request.user, observacion=datos['observacion'])
        except ValueError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, 'Transferencia registrada.')
            return redirect('inventario:movimiento_lista')
    return render(request, 'core/form.html', {
        'titulo': 'Transferir entre bodega y vitrina', 'form': form,
        'url_cancelar': reverse_lazy('inventario:stock'),
    })


@permiso_requerido('ajustar_inventario')
def ajuste(request):
    form = AjusteForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        datos = form.cleaned_data
        try:
            services.ajustar_stock(lote=datos['lote'], ubicacion=datos['ubicacion'], tipo=datos['tipo'],
                                   cantidad=datos['cantidad'], usuario=request.user, motivo=datos['motivo'])
        except ValueError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, 'Ajuste registrado y autorizado.')
            return redirect('inventario:movimiento_lista')
    return render(request, 'core/form.html', {
        'titulo': 'Ajuste, merma o baja de stock', 'form': form,
        'url_cancelar': reverse_lazy('inventario:stock'),
        'ayuda': 'Operación regulada: requiere la autorización del Químico Farmacéutico y queda '
                 'registrada en el historial y en la auditoría.',
    })


# ----------------------------------------------------------- Movimientos
class MovimientoLista(ListaGenericaView):
    permiso = 'ver_inventario'
    model = MovimientoInventario
    titulo = 'Historial de movimientos de inventario'
    columnas = (('Fecha y hora', 'fecha'), ('Tipo', 'get_tipo_display'), ('Producto', 'producto.nombre'),
                ('Lote', 'lote.numero_lote'), ('Cantidad', 'cantidad'), ('Origen', 'get_ubicacion_origen_display'),
                ('Destino', 'get_ubicacion_destino_display'), ('Referencia', 'referencia'),
                ('Usuario', 'usuario.username'))
    campos_busqueda = ('producto__nombre', 'lote__numero_lote', 'referencia')
    form_filtro = MovimientoFiltro
    paginate_by = 40

    def get_queryset(self):
        self.queryset = MovimientoInventario.objects.select_related('producto', 'lote', 'usuario')
        return super().get_queryset()

    def aplicar_filtros(self, qs, datos):
        if datos.get('tipo'):
            qs = qs.filter(tipo=datos['tipo'])
        if datos.get('desde'):
            qs = qs.filter(fecha__date__gte=datos['desde'])
        if datos.get('hasta'):
            qs = qs.filter(fecha__date__lte=datos['hasta'])
        return qs
