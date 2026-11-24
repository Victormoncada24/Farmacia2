from django import forms

from core.forms import BootstrapFormMixin, FiltroBase
from inventario.models import Producto

from .models import MovimientoControlado


class LibroFiltro(FiltroBase):
    producto = forms.ModelChoiceField(
        Producto.objects.exclude(control=Producto.Control.NINGUNO), required=False,
        empty_label='Todos los controlados')
    tipo = forms.ChoiceField(required=False, label='Movimiento',
                             choices=[('', 'Todos')] + list(MovimientoControlado.Tipo.choices))
    firma = forms.ChoiceField(required=False, label='Firma',
                              choices=[('', 'Todas'), ('pendiente', 'Pendientes de firma'), ('firmado', 'Firmados')])
    desde = forms.DateField(required=False, label='Desde')
    hasta = forms.DateField(required=False, label='Hasta')


class ConteoForm(BootstrapFormMixin, forms.Form):
    producto = forms.ModelChoiceField(Producto.objects.none(), label='Medicamento controlado')
    cantidad_contada = forms.IntegerField(min_value=0, label='Cantidad contada físicamente')
    observacion = forms.CharField(required=False, label='Observación', widget=forms.Textarea(attrs={'rows': 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['producto'].queryset = Producto.objects.filter(activo=True).exclude(
            control=Producto.Control.NINGUNO).order_by('nombre')
        self.aplicar_bootstrap()


class ResolverConteoForm(BootstrapFormMixin, forms.Form):
    nota = forms.CharField(label='Nota de regularización', widget=forms.Textarea(attrs={'rows': 3}),
                           help_text='Indique cómo se regularizó la diferencia (ajuste autorizado, error de conteo, etc.).')
