from django import forms

from core.forms import BootstrapFormMixin, FiltroBase
from inventario.models import Producto

from .models import CuotaPrograma, InscripcionPrograma, Paciente, Programa


class PacienteForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Paciente
        fields = ('tipo_documento', 'documento', 'nombres', 'apellidos', 'fecha_nacimiento', 'prevision',
                  'telefono', 'direccion', 'email', 'activo')

    def clean_fecha_nacimiento(self):
        from django.utils import timezone
        fecha = self.cleaned_data.get('fecha_nacimiento')
        if fecha and fecha > timezone.localdate():
            raise forms.ValidationError('La fecha de nacimiento no puede ser futura.')
        return fecha


class PacienteFiltro(FiltroBase):
    programa = forms.ModelChoiceField(Programa.objects.filter(activo=True), required=False,
                                      empty_label='Todos los programas')


class ProgramaForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Programa
        fields = ('nombre', 'tipo', 'descripcion', 'activo')


class InscripcionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = InscripcionPrograma
        fields = ('programa', 'fecha_inicio', 'diagnostico')
        widgets = {'diagnostico': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, paciente=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.paciente = paciente
        self.fields['programa'].queryset = Programa.objects.filter(activo=True)
        self.aplicar_bootstrap()

    def clean_programa(self):
        programa = self.cleaned_data['programa']
        if self.paciente and InscripcionPrograma.objects.filter(
                paciente=self.paciente, programa=programa, activo=True).exists():
            raise forms.ValidationError('El paciente ya está inscrito y vigente en este programa.')
        return programa


class CuotaForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = CuotaPrograma
        fields = ('producto', 'cantidad_mensual')

    def __init__(self, *args, inscripcion=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.inscripcion = inscripcion
        self.fields['producto'].queryset = Producto.objects.filter(activo=True).order_by('nombre')
        self.fields['cantidad_mensual'].min_value = 1
        self.aplicar_bootstrap()

    def clean_cantidad_mensual(self):
        valor = self.cleaned_data['cantidad_mensual']
        if valor < 1:
            raise forms.ValidationError('La cuota debe ser de al menos 1 unidad.')
        return valor

    def clean_producto(self):
        producto = self.cleaned_data['producto']
        if self.inscripcion and self.inscripcion.cuotas.filter(producto=producto).exists():
            raise forms.ValidationError('Este producto ya tiene una cuota en la inscripción.')
        return producto
