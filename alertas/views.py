from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.forms import FiltroBase
from core.views import ListaGenericaView, permiso_requerido

from . import services
from .models import Alerta


class AlertaFiltro(FiltroBase):
    estado = forms.ChoiceField(required=False, label='Estado', choices=[
        ('abiertas', 'Abiertas'), ('resueltas', 'Resueltas'), ('todas', 'Todas')])
    tipo = forms.ChoiceField(required=False, label='Tipo', choices=[('', 'Todos los tipos')] + list(Alerta.Tipo.choices))
    severidad = forms.ChoiceField(required=False, label='Severidad',
                                  choices=[('', 'Todas')] + list(Alerta.Severidad.choices))


class AlertaLista(ListaGenericaView):
    permiso = 'ver_alertas'
    model = Alerta
    template_name = 'alertas/lista.html'
    titulo = 'Alertas oportunas'
    subtitulo = 'Stock crítico, vencimientos, carros clínicos y descuadres de medicamentos controlados.'
    columnas = (('Generada', 'creada_en'), ('Severidad', 'severidad_texto'), ('Tipo', 'get_tipo_display'),
                ('Mensaje', 'mensaje'))
    campos_busqueda = ('mensaje',)
    form_filtro = AlertaFiltro

    def get(self, request, *args, **kwargs):
        services.sincronizar()
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        self.queryset = Alerta.objects.select_related('producto', 'carro', 'lote')
        return super().get_queryset()

    def aplicar_filtros(self, qs, datos):
        estado = datos.get('estado') or 'abiertas'
        if estado == 'abiertas':
            qs = qs.filter(resuelta=False)
        elif estado == 'resueltas':
            qs = qs.filter(resuelta=True)
        if datos.get('tipo'):
            qs = qs.filter(tipo=datos['tipo'])
        if datos.get('severidad'):
            qs = qs.filter(severidad=datos['severidad'])
        return qs


@permiso_requerido('ver_alertas')
@require_POST
def resolver(request, pk):
    alerta = get_object_or_404(Alerta, pk=pk)
    if alerta.es_automatica:
        messages.info(request, 'Las alertas automáticas se cierran solas cuando se corrige la causa.')
    else:
        alerta.resuelta = True
        alerta.resuelta_en = timezone.now()
        alerta.resuelta_por = request.user
        alerta.save(update_fields=['resuelta', 'resuelta_en', 'resuelta_por'])
        messages.success(request, 'Alerta marcada como resuelta.')
    return redirect('alertas:lista')


@permiso_requerido('ver_alertas')
@require_POST
def recalcular(request):
    services.sincronizar()
    messages.success(request, 'Alertas recalculadas.')
    return redirect('alertas:lista')
