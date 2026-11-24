"""Mixins y vistas genéricas reutilizadas por todos los módulos."""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db.models import ProtectedError, Q, RestrictedError
from django.shortcuts import redirect
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .forms import FiltroBase


class RolRequeridoMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Exige sesión iniciada y que el rol del usuario tenga el permiso `permiso`."""
    permiso = None

    def test_func(self):
        if not self.permiso:
            return True
        return self.request.user.puede(self.permiso)


def permiso_requerido(clave):
    """Decorador equivalente para vistas basadas en funciones."""
    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not request.user.puede(clave):
                raise PermissionDenied
            return vista(request, *args, **kwargs)
        return login_required(envoltura)
    return decorador


class TituloMixin:
    titulo = ''
    url_cancelar = None

    def get_titulo(self):
        return self.titulo

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto['titulo'] = self.get_titulo()
        contexto['url_cancelar'] = self.url_cancelar or getattr(self, 'success_url', None) or '/'
        return contexto


class MensajeExitoMixin:
    mensaje_exito = 'Los datos se guardaron correctamente.'

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        messages.success(self.request, self.mensaje_exito)
        return respuesta


class CrearView(RolRequeridoMixin, TituloMixin, MensajeExitoMixin, CreateView):
    template_name = 'core/form.html'


class EditarView(RolRequeridoMixin, TituloMixin, MensajeExitoMixin, UpdateView):
    template_name = 'core/form.html'


class EliminarView(RolRequeridoMixin, TituloMixin, DeleteView):
    template_name = 'core/confirmar_eliminar.html'

    def form_valid(self, form):
        descripcion = str(self.object)
        try:
            self.object.delete()
        except (ProtectedError, RestrictedError):
            messages.error(
                self.request,
                f'No se puede eliminar «{descripcion}» porque tiene registros asociados. '
                'Puede desactivarlo en su lugar.',
            )
            return redirect(self.get_success_url())
        messages.success(self.request, f'«{descripcion}» fue eliminado.')
        return redirect(self.get_success_url())


class ListaGenericaView(RolRequeridoMixin, ListView):
    """Listado con búsqueda, filtros GET, paginación y acciones por fila."""
    template_name = 'core/lista.html'
    paginate_by = 25
    titulo = ''
    columnas = ()             # ((etiqueta, 'ruta.al.atributo'), ...)
    campos_busqueda = ()      # campos para el filtro de texto libre
    form_filtro = None        # clase de formulario de filtros (opcional)
    url_crear = None
    etiqueta_crear = 'Nuevo'
    url_detalle = None
    url_editar = None
    url_eliminar = None
    acciones_extra = ()       # ((nombre_url, etiqueta, icono_bootstrap), ...)
    permiso_edicion = None    # permiso requerido para mostrar crear/editar/eliminar
    subtitulo = ''

    def aplicar_filtros(self, qs, datos):
        return qs

    def get_queryset(self):
        qs = super().get_queryset()
        self.filtro = None
        clase = self.form_filtro or (FiltroBase if self.campos_busqueda else None)
        if clase:
            self.filtro = clase(self.request.GET)
            if self.filtro.is_valid():
                datos = self.filtro.cleaned_data
                texto = (datos.get('q') or '').strip()
                if texto and self.campos_busqueda:
                    condicion = Q()
                    for campo in self.campos_busqueda:
                        condicion |= Q(**{f'{campo}__icontains': texto})
                    qs = qs.filter(condicion)
                qs = self.aplicar_filtros(qs, datos)
        return qs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        parametros = self.request.GET.copy()
        parametros.pop('page', None)
        usuario = self.request.user
        contexto.update(
            titulo=self.titulo,
            subtitulo=self.subtitulo,
            columnas=self.columnas,
            filtro=self.filtro,
            querystring=parametros.urlencode(),
            url_crear=self.url_crear,
            etiqueta_crear=self.etiqueta_crear,
            url_detalle=self.url_detalle,
            url_editar=self.url_editar,
            url_eliminar=self.url_eliminar,
            acciones_extra=self.acciones_extra,
            puede_editar=bool(self.permiso_edicion and usuario.puede(self.permiso_edicion)),
        )
        return contexto
