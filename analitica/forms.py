from django import forms

from core.forms import BootstrapFormMixin
from pacientes.models import Programa

from .calculos import ESTADOS_ABASTECIMIENTO, ESTADOS_ADHERENCIA


class AbastecimientoForm(BootstrapFormMixin, forms.Form):
    dias = forms.ChoiceField(label='Período de consumo', required=False,
                             choices=[('30', 'Últimos 30 días'), ('60', 'Últimos 60 días'), ('90', 'Últimos 90 días')])
    lead_time = forms.IntegerField(label='Plazo de reposición (días)', required=False, min_value=1, max_value=120,
                                   help_text='Tiempo que tarda en llegar un pedido (CENABAST / Servicio de Salud).')
    dias_objetivo = forms.IntegerField(label='Cobertura objetivo (días)', required=False, min_value=7, max_value=365)
    estado = forms.ChoiceField(label='Estado', required=False,
                               choices=[('', 'Todos')] + list(ESTADOS_ABASTECIMIENTO.items()))
    solo_pedir = forms.BooleanField(label='Solo productos con pedido sugerido', required=False)


class AdherenciaForm(BootstrapFormMixin, forms.Form):
    programa = forms.ModelChoiceField(Programa.objects.filter(activo=True), required=False,
                                      empty_label='Todos los programas')
    estado = forms.ChoiceField(label='Estado', required=False,
                               choices=[('', 'Todos')] + list(ESTADOS_ADHERENCIA.items()))
    umbral_atraso = forms.IntegerField(label='Atraso desde (días sin retiro)', required=False, min_value=7,
                                       max_value=120)
    umbral_abandono = forms.IntegerField(label='Riesgo de abandono desde (días)', required=False, min_value=14,
                                         max_value=365)
