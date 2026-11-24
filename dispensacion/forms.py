from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone

from core.forms import BootstrapFormMixin, FiltroBase
from core.utils import normalizar_rut, validar_rut
from core.validators import validar_archivo_receta
from inventario.models import Producto
from pacientes.models import Programa

from .models import Receta, RecetaItem


class RecetaForm(BootstrapFormMixin, forms.ModelForm):
    archivo = forms.FileField(
        label='Archivo de la receta (PDF, JPG o PNG, máx. 5 MB)', required=False,
        validators=[validar_archivo_receta])

    class Meta:
        model = Receta
        fields = ('numero', 'tipo', 'modalidad', 'control_saldo', 'fecha_emision', 'vigencia_dias',
                  'medico_nombre', 'medico_rut', 'establecimiento_emisor', 'programa', 'archivo',
                  'observaciones')
        widgets = {'observaciones': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, paciente=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['programa'].queryset = Programa.objects.filter(
            activo=True, inscripciones__paciente=paciente, inscripciones__activo=True).distinct()
        self.fields['programa'].empty_label = 'Atención estándar (sin programa)'
        self.fields['vigencia_dias'].min_value = 1
        self.aplicar_bootstrap()

    def clean_fecha_emision(self):
        fecha = self.cleaned_data['fecha_emision']
        if fecha > timezone.localdate():
            raise forms.ValidationError('La fecha de emisión no puede ser futura.')
        return fecha

    def clean(self):
        datos = super().clean()
        emision, dias = datos.get('fecha_emision'), datos.get('vigencia_dias')
        if emision and dias:
            from datetime import timedelta
            if emision + timedelta(days=dias) < timezone.localdate():
                raise forms.ValidationError('La receta ya está vencida según su fecha de emisión y vigencia.')
        return datos


class RecetaItemForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = RecetaItem
        fields = ('producto', 'cantidad_prescrita', 'indicacion')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['producto'].queryset = Producto.objects.filter(activo=True).order_by('nombre')
        self.fields['cantidad_prescrita'].widget.attrs['min'] = 1
        self.aplicar_bootstrap()

    def clean_cantidad_prescrita(self):
        valor = self.cleaned_data['cantidad_prescrita']
        if valor < 1:
            raise forms.ValidationError('Debe ser al menos 1.')
        return valor


RecetaItemFormSet = inlineformset_factory(
    Receta, RecetaItem, form=RecetaItemForm, extra=0, min_num=1, validate_min=True, can_delete=True)


class DispensacionForm(BootstrapFormMixin, forms.Form):
    retira_tercero = forms.BooleanField(required=False, label='Retira un tercero autorizado')
    retiro_nombre = forms.CharField(required=False, max_length=150, label='Nombre de quien retira')
    retiro_rut = forms.CharField(required=False, max_length=12, label='RUT de quien retira')
    retiro_parentesco = forms.CharField(required=False, max_length=60, label='Relación con el paciente (ej. Padre)')
    observacion = forms.CharField(required=False, label='Observación', widget=forms.Textarea(attrs={'rows': 2}))
    excepcion_cuota = forms.BooleanField(required=False, label='Autorizar excepción de cuota / cobertura (solo Q.F.)')

    def __init__(self, *args, receta, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.receta = receta
        if not usuario.puede('autorizar'):
            del self.fields['excepcion_cuota']
        for item in receta.items.select_related('producto'):
            self.fields[f'item_{item.pk}'] = forms.IntegerField(
                required=False, min_value=0, initial=0, label=str(item.producto),
                widget=forms.NumberInput(attrs={'style': 'max-width:110px', 'min': 0}))
        self.aplicar_bootstrap()

    def clean(self):
        datos = super().clean()
        if datos.get('retira_tercero'):
            for campo, etiqueta in (('retiro_nombre', 'el nombre'), ('retiro_rut', 'el RUT'),
                                    ('retiro_parentesco', 'la relación con el paciente')):
                if not datos.get(campo):
                    self.add_error(campo, f'Indique {etiqueta} de quien retira.')
            if datos.get('retiro_rut'):
                try:
                    validar_rut(datos['retiro_rut'])
                    datos['retiro_rut'] = normalizar_rut(datos['retiro_rut'])
                except forms.ValidationError as error:
                    self.add_error('retiro_rut', error)
        return datos

    def cantidades(self):
        return {int(nombre.split('_')[1]): (valor or 0)
                for nombre, valor in self.cleaned_data.items() if nombre.startswith('item_')}


class AnularRecetaForm(BootstrapFormMixin, forms.Form):
    motivo = forms.CharField(max_length=200, label='Motivo de anulación')


class RecetaFiltro(FiltroBase):
    modalidad = forms.ChoiceField(required=False, label='Modalidad',
                                  choices=[('', 'Todas')] + list(Receta.Modalidad.choices))
    anuladas = forms.BooleanField(required=False, label='Solo anuladas')


class HistorialFiltro(FiltroBase):
    programa = forms.ModelChoiceField(Programa.objects.all(), required=False, empty_label='Todos los programas')
    desde = forms.DateField(required=False, label='Desde')
    hasta = forms.DateField(required=False, label='Hasta')
