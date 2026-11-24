from django import forms
from django.db.models import Q
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils import timezone

from core.forms import BootstrapFormMixin, FiltroBase
from inventario.models import Producto, Ubicacion

from .logica import validar_linea_recepcion
from .models import Pedido, PedidoItem, Proveedor


class ProveedorForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = ('nombre', 'tipo', 'rut', 'contacto', 'telefono', 'email', 'plazo_entrega_dias',
                  'observaciones', 'activo')
        widgets = {'observaciones': forms.Textarea(attrs={'rows': 2})}


class ProveedorFiltro(FiltroBase):
    tipo = forms.ChoiceField(required=False, label='Tipo', choices=[('', 'Todos')] + list(Proveedor.Tipo.choices))


class PedidoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Pedido
        fields = ('proveedor', 'prioridad', 'observacion')
        widgets = {'observacion': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        condicion = Q(activo=True)
        if self.instance.pk:
            condicion |= Q(pk=self.instance.proveedor_id)
        self.fields['proveedor'].queryset = Proveedor.objects.filter(condicion)
        self.aplicar_bootstrap()


class PedidoItemForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = PedidoItem
        fields = ('producto', 'cantidad_pedida')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['producto'].queryset = Producto.objects.filter(activo=True).order_by('nombre')
        self.fields['cantidad_pedida'].widget.attrs['min'] = 1
        self.aplicar_bootstrap()


class BasePedidoItemFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        vistos = set()
        for form in self.forms:
            datos = getattr(form, 'cleaned_data', None)
            if not datos or datos.get('DELETE'):
                continue
            producto = datos.get('producto')
            if producto is None:
                continue
            if producto.pk in vistos:
                raise forms.ValidationError(
                    'Un producto aparece más de una vez en el pedido. Sume las cantidades en una sola línea.')
            vistos.add(producto.pk)


PedidoItemFormSet = inlineformset_factory(
    Pedido, PedidoItem, form=PedidoItemForm, formset=BasePedidoItemFormSet,
    extra=0, min_num=1, validate_min=True, can_delete=True)


class PedidoFiltro(FiltroBase):
    estado = forms.ChoiceField(required=False, label='Estado', choices=[('', 'Todos')] + list(Pedido.Estado.choices))
    proveedor = forms.ModelChoiceField(Proveedor.objects.all(), required=False, empty_label='Todos los proveedores')
    atrasados = forms.BooleanField(required=False, label='Solo atrasados')
    desde = forms.DateField(required=False, label='Desde')
    hasta = forms.DateField(required=False, label='Hasta')


class RecepcionForm(BootstrapFormMixin, forms.Form):
    documento_ref = forms.CharField(max_length=60, label='N° de guía de despacho / factura')
    ubicacion = forms.ChoiceField(label='Ubicación de ingreso', choices=Ubicacion.choices, initial=Ubicacion.BODEGA)
    observacion = forms.CharField(required=False, label='Observación', widget=forms.Textarea(attrs={'rows': 2}))

    def __init__(self, *args, pedido, **kwargs):
        super().__init__(*args, **kwargs)
        self.pedido = pedido
        self._lineas = []
        self.items = [i for i in pedido.items.select_related('producto') if i.pendiente > 0]
        for item in self.items:
            self.fields[f'cant_{item.pk}'] = forms.IntegerField(
                required=False, min_value=0, initial=0, label='Cantidad recibida',
                widget=forms.NumberInput(attrs={'style': 'max-width:120px', 'min': 0}))
            self.fields[f'lote_{item.pk}'] = forms.CharField(required=False, max_length=50, label='N° de lote')
            self.fields[f'venc_{item.pk}'] = forms.DateField(required=False, label='Vencimiento')
        self.aplicar_bootstrap()

    @property
    def filas(self):
        return [{'item': i, 'cant': self[f'cant_{i.pk}'], 'lote': self[f'lote_{i.pk}'], 'venc': self[f'venc_{i.pk}']}
                for i in self.items]

    def clean(self):
        datos = super().clean()
        hoy = timezone.localdate()
        self._lineas = []
        for item in self.items:
            cantidad = datos.get(f'cant_{item.pk}') or 0
            if cantidad <= 0:
                continue
            error = validar_linea_recepcion(item.pendiente, cantidad)
            if error:
                self.add_error(f'cant_{item.pk}', error)
                continue
            lote = (datos.get(f'lote_{item.pk}') or '').strip()
            vencimiento = datos.get(f'venc_{item.pk}')
            if not lote:
                self.add_error(f'lote_{item.pk}', 'Indique el N° de lote.')
            if not vencimiento:
                self.add_error(f'venc_{item.pk}', 'Indique el vencimiento.')
            elif vencimiento <= hoy:
                self.add_error(f'venc_{item.pk}', 'El lote está vencido o vence hoy.')
            if lote and vencimiento and vencimiento > hoy:
                self._lineas.append({'item_id': item.pk, 'cantidad': cantidad, 'numero_lote': lote,
                                     'vencimiento': vencimiento})
        if not self._lineas and not self.errors:
            raise forms.ValidationError('Indique la cantidad recibida de al menos un producto.')
        return datos

    def lineas(self):
        return self._lineas
