from datetime import timedelta

from django import forms
from django.db.models import Q
from django.utils import timezone

from core.forms import BootstrapFormMixin, FiltroBase

from .models import Categoria, Lote, MovimientoInventario, Producto, StockLote, Ubicacion

T = MovimientoInventario.Tipo


class CategoriaForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ('nombre', 'descripcion')


class ProductoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Producto
        fields = ('codigo', 'codigo_barras', 'nombre', 'principio_activo', 'presentacion', 'tipo', 'categoria',
                  'control', 'stock_minimo', 'stock_objetivo', 'activo')


class ProductoFiltro(FiltroBase):
    categoria = forms.ModelChoiceField(Categoria.objects.all(), required=False, empty_label='Todas las categorías')
    solo_controlados = forms.BooleanField(required=False, label='Solo controlados')


class StockFiltro(FiltroBase):
    categoria = forms.ModelChoiceField(Categoria.objects.all(), required=False, empty_label='Todas las categorías')
    estado = forms.ChoiceField(required=False, label='Estado', choices=[
        ('', 'Todos'), ('critico', 'Stock crítico'), ('sin_stock', 'Sin stock')])


class LoteFiltro(FiltroBase):
    estado = forms.ChoiceField(required=False, label='Vencimiento', choices=[
        ('', 'Todos'), ('vencido', 'Vencidos'), ('critico', 'Vencen en 30 días o menos'),
        ('proximo', 'Próximos a vencer'), ('vigente', 'Vigentes')])
    con_stock = forms.BooleanField(required=False, label='Solo con stock')


class MovimientoFiltro(FiltroBase):
    tipo = forms.ChoiceField(required=False, label='Tipo', choices=[('', 'Todos')] + list(T.choices))
    desde = forms.DateField(required=False, label='Desde')
    hasta = forms.DateField(required=False, label='Hasta')


class _LoteChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, lote):
        return f'{lote.producto.nombre} — lote {lote.numero_lote} — vence {lote.fecha_vencimiento:%d/%m/%Y}'


class IngresoLoteForm(BootstrapFormMixin, forms.Form):
    producto = forms.ModelChoiceField(Producto.objects.none(), label='Producto')
    numero_lote = forms.CharField(label='N° de lote', max_length=50)
    fecha_vencimiento = forms.DateField(label='Fecha de vencimiento')
    cantidad = forms.IntegerField(label='Cantidad recibida', min_value=1)
    ubicacion = forms.ChoiceField(label='Ubicación de destino', choices=Ubicacion.choices, initial=Ubicacion.BODEGA)
    origen = forms.ChoiceField(label='Origen', choices=Lote.Origen.choices)
    documento_ref = forms.CharField(label='N° de guía / remesa', max_length=60, required=False)
    observacion = forms.CharField(label='Observación', required=False, widget=forms.Textarea(attrs={'rows': 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['producto'].queryset = Producto.objects.filter(activo=True).order_by('nombre')
        self.aplicar_bootstrap()

    def clean_fecha_vencimiento(self):
        fecha = self.cleaned_data['fecha_vencimiento']
        if fecha <= timezone.localdate():
            raise forms.ValidationError('No se puede ingresar un lote vencido o que vence hoy.')
        return fecha


class TransferenciaForm(BootstrapFormMixin, forms.Form):
    lote = _LoteChoiceField(Lote.objects.none(), label='Lote')
    origen = forms.ChoiceField(label='Desde', choices=Ubicacion.choices, initial=Ubicacion.BODEGA)
    destino = forms.ChoiceField(label='Hacia', choices=Ubicacion.choices, initial=Ubicacion.VITRINA)
    cantidad = forms.IntegerField(label='Cantidad', min_value=1)
    observacion = forms.CharField(label='Observación', required=False, widget=forms.Textarea(attrs={'rows': 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['lote'].queryset = (
            Lote.objects.filter(activo=True, stocks__cantidad__gt=0, fecha_vencimiento__gte=timezone.localdate())
            .select_related('producto').distinct().order_by('producto__nombre', 'fecha_vencimiento'))
        self.aplicar_bootstrap()

    def clean(self):
        datos = super().clean()
        if datos.get('origen') and datos.get('origen') == datos.get('destino'):
            raise forms.ValidationError('El origen y el destino deben ser distintos.')
        return datos


class AjusteForm(BootstrapFormMixin, forms.Form):
    lote = _LoteChoiceField(Lote.objects.none(), label='Lote')
    ubicacion = forms.ChoiceField(label='Ubicación', choices=Ubicacion.choices)
    tipo = forms.ChoiceField(label='Tipo de ajuste', choices=[
        (T.AJUSTE_POSITIVO, T.AJUSTE_POSITIVO.label), (T.AJUSTE_NEGATIVO, T.AJUSTE_NEGATIVO.label),
        (T.MERMA, T.MERMA.label), (T.BAJA_VENCIDO, T.BAJA_VENCIDO.label)])
    cantidad = forms.IntegerField(label='Cantidad', min_value=1)
    motivo = forms.CharField(label='Motivo (obligatorio)', widget=forms.Textarea(attrs={'rows': 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['lote'].queryset = Lote.objects.select_related('producto').order_by(
            'producto__nombre', 'fecha_vencimiento')
        self.aplicar_bootstrap()
