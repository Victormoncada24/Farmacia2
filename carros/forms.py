from django import forms

from core.forms import BootstrapFormMixin, FiltroBase
from inventario.models import Producto

from .models import CarroClinico, CarroItem, SolicitudReposicion


class CarroForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = CarroClinico
        fields = ('nombre', 'tipo', 'ubicacion', 'responsable', 'precinto', 'activo')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from accounts.models import Usuario
        self.fields['responsable'].queryset = Usuario.objects.filter(is_active=True)
        self.aplicar_bootstrap()


class CarroItemForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = CarroItem
        fields = ('producto', 'cantidad_requerida')

    def __init__(self, *args, carro=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.carro = carro
        self.fields['producto'].queryset = Producto.objects.filter(activo=True).order_by('nombre')
        if self.instance.pk:
            self.fields['producto'].disabled = True
        self.aplicar_bootstrap()

    def clean_cantidad_requerida(self):
        valor = self.cleaned_data['cantidad_requerida']
        if valor < 1:
            raise forms.ValidationError('La dotación debe ser de al menos 1 unidad.')
        return valor

    def clean_producto(self):
        producto = self.cleaned_data['producto']
        if not self.instance.pk and self.carro and self.carro.items.filter(producto=producto).exists():
            raise forms.ValidationError('El producto ya forma parte de la dotación del carro.')
        return producto


class ReposicionForm(BootstrapFormMixin, forms.Form):
    observacion = forms.CharField(required=False, label='Observación', widget=forms.Textarea(attrs={'rows': 2}))

    def __init__(self, *args, carro, **kwargs):
        super().__init__(*args, **kwargs)
        for item in carro.items.select_related('producto'):
            self.fields[f'conteo_{item.pk}'] = forms.IntegerField(
                min_value=0, initial=item.cantidad_actual,
                label=f'{item.producto} — dotación {item.cantidad_requerida}',
                help_text=f'Según sistema: {item.cantidad_actual}. Ingrese lo que cuenta físicamente.')
        self.order_fields([n for n in self.fields if n.startswith('conteo_')] + ['observacion'])
        self.aplicar_bootstrap()

    def conteo(self):
        return {int(n.split('_')[1]): v for n, v in self.cleaned_data.items() if n.startswith('conteo_')}


class ConsumoForm(BootstrapFormMixin, forms.Form):
    producto = forms.ModelChoiceField(Producto.objects.none(), label='Producto consumido')
    cantidad = forms.IntegerField(min_value=1, label='Cantidad')
    referencia = forms.CharField(required=False, max_length=120, label='Paciente / cama / referencia')
    observacion = forms.CharField(required=False, max_length=200, label='Observación')

    def __init__(self, *args, carro, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['producto'].queryset = Producto.objects.filter(
            en_carros__carro=carro, en_carros__cantidad_actual__gt=0).order_by('nombre')
        self.aplicar_bootstrap()


class SolicitudForm(BootstrapFormMixin, forms.Form):
    observacion = forms.CharField(required=False, max_length=250, label='Observación / motivo')

    def __init__(self, *args, carro, **kwargs):
        super().__init__(*args, **kwargs)
        for item in carro.items.select_related('producto'):
            self.fields[f'sol_{item.pk}'] = forms.IntegerField(
                required=False, min_value=0, initial=item.faltante,
                label=str(item.producto), help_text=f'Actual {item.cantidad_actual} de {item.cantidad_requerida}.')
        self.items = {item.pk: item.producto_id for item in carro.items.all()}
        self.order_fields([n for n in self.fields if n.startswith('sol_')] + ['observacion'])
        self.aplicar_bootstrap()

    def cantidades(self):
        return {self.items[int(n.split('_')[1])]: (v or 0)
                for n, v in self.cleaned_data.items() if n.startswith('sol_')}


class SolicitudFiltro(FiltroBase):
    estado = forms.ChoiceField(required=False, label='Estado',
                               choices=[('', 'Todos')] + list(SolicitudReposicion.Estado.choices))
