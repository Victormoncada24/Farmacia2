from django import forms


class DateInput(forms.DateInput):
    input_type = 'date'

    def __init__(self, attrs=None, format=None):
        super().__init__(attrs=attrs, format=format or '%Y-%m-%d')


class BootstrapFormMixin:
    """Aplica clases Bootstrap a todos los campos y usa <input type=date> en fechas."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aplicar_bootstrap()

    def aplicar_bootstrap(self):
        for campo in self.fields.values():
            if isinstance(campo, forms.DateField) and not isinstance(campo.widget, DateInput):
                campo.widget = DateInput()
                campo.widget.is_required = campo.required
            widget = campo.widget
            if isinstance(widget, forms.CheckboxInput):
                clase = 'form-check-input'
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                clase = 'form-select'
            else:
                clase = 'form-control'
            actuales = widget.attrs.get('class', '')
            if clase not in actuales.split():
                widget.attrs['class'] = f'{actuales} {clase}'.strip()


class FiltroBase(BootstrapFormMixin, forms.Form):
    """Formulario de filtros (GET) con búsqueda de texto libre."""
    q = forms.CharField(label='Buscar', required=False)
