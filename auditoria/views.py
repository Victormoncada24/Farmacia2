from django import forms

from core.forms import DateInput, FiltroBase
from core.views import ListaGenericaView

from .models import RegistroAuditoria


class AuditoriaFiltro(FiltroBase):
    accion = forms.ChoiceField(label='Acción', required=False,
                               choices=[('', 'Todas')] + list(RegistroAuditoria.Accion.choices))
    desde = forms.DateField(label='Desde', required=False)
    hasta = forms.DateField(label='Hasta', required=False)


class AuditoriaLista(ListaGenericaView):
    permiso = 'auditoria'
    model = RegistroAuditoria
    titulo = 'Auditoría y trazabilidad de accesos'
    subtitulo = 'Registro inmutable de accesos y operaciones: usuario, fecha, hora y dirección IP.'
    columnas = (('Fecha y hora', 'fecha'), ('Usuario', 'usuario_texto'), ('Acción', 'get_accion_display'),
                ('Entidad', 'modelo'), ('ID', 'objeto_id'), ('Detalle', 'descripcion'), ('IP', 'ip'))
    campos_busqueda = ('usuario_texto', 'modelo', 'descripcion')
    form_filtro = AuditoriaFiltro
    paginate_by = 50

    def aplicar_filtros(self, qs, datos):
        if datos.get('accion'):
            qs = qs.filter(accion=datos['accion'])
        if datos.get('desde'):
            qs = qs.filter(fecha__date__gte=datos['desde'])
        if datos.get('hasta'):
            qs = qs.filter(fecha__date__lte=datos['hasta'])
        return qs
