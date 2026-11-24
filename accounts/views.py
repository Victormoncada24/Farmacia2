import hashlib

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.core.cache import cache
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST

from core import roles
from core.utils import obtener_ip
from core.views import (CrearView, EditarView, EliminarView, ListaGenericaView, permiso_requerido)

from .forms import (CambiarClaveForm, LoginForm, RestablecerClaveForm, UsuarioCrearForm, UsuarioEditarForm,
                    UsuarioFiltro)
from .models import Usuario


class IngresoView(LoginView):
    """Inicio de sesión con bloqueo temporal tras varios intentos fallidos."""
    template_name = 'accounts/login.html'
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def _clave_cache(self):
        usuario = (self.request.POST.get('username') or '').strip().lower()
        huella = hashlib.sha256(f'{obtener_ip(self.request)}|{usuario}'.encode()).hexdigest()
        return f'login_fallos:{huella}'

    def post(self, request, *args, **kwargs):
        if cache.get(self._clave_cache(), 0) >= settings.LOGIN_MAX_INTENTOS:
            messages.error(
                request,
                'Demasiados intentos fallidos. Por seguridad, espere unos minutos antes de reintentar.',
            )
            return self.get(request, *args, **kwargs)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        clave = self._clave_cache()
        cache.set(clave, cache.get(clave, 0) + 1, settings.LOGIN_BLOQUEO_SEGUNDOS)
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(self._clave_cache())
        return super().form_valid(form)


class CambiarClaveView(PasswordChangeView):
    template_name = 'core/form.html'
    form_class = CambiarClaveForm
    success_url = reverse_lazy('accounts:perfil')

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update(titulo='Cambiar mi contraseña', url_cancelar=reverse_lazy('accounts:perfil'))
        return contexto

    def form_valid(self, form):
        messages.success(self.request, 'Su contraseña fue actualizada.')
        return super().form_valid(form)


@login_required
def perfil(request):
    return render(request, 'accounts/perfil.html', {'titulo': 'Mi perfil'})


@permiso_requerido('usuarios')
def roles_permisos(request):
    matriz = [
        {'clave': clave, 'descripcion': datos[0], 'roles': {r: (r in datos[1]) for r in roles.NOMBRES}}
        for clave, datos in roles.PERMISOS.items()
    ]
    return render(request, 'accounts/roles.html', {
        'titulo': 'Roles y permisos', 'matriz': matriz, 'roles': roles.CHOICES,
    })


class UsuarioLista(ListaGenericaView):
    permiso = 'usuarios'
    permiso_edicion = 'usuarios'
    model = Usuario
    titulo = 'Usuarios del sistema'
    columnas = (('Usuario', 'username'), ('Nombre', 'nombre_completo'), ('RUT', 'rut'),
                ('Teléfono', 'telefono'), ('Rol', 'get_rol_display'), ('Activo', 'is_active'))
    campos_busqueda = ('username', 'first_name', 'last_name', 'rut', 'email')
    form_filtro = UsuarioFiltro
    url_crear = 'accounts:usuario_crear'
    etiqueta_crear = 'Nuevo usuario'
    url_editar = 'accounts:usuario_editar'
    url_eliminar = 'accounts:usuario_eliminar'
    acciones_extra = (('accounts:usuario_clave', 'Restablecer contraseña', 'bi-key'),
                      ('accounts:usuario_estado', 'Activar / desactivar', 'bi-toggle-on', 'post'))

    def aplicar_filtros(self, qs, datos):
        if datos.get('rol'):
            qs = qs.filter(rol=datos['rol'])
        if datos.get('estado') == 'activo':
            qs = qs.filter(is_active=True)
        elif datos.get('estado') == 'inactivo':
            qs = qs.filter(is_active=False)
        return qs


class UsuarioCrear(CrearView):
    permiso = 'usuarios'
    model = Usuario
    form_class = UsuarioCrearForm
    titulo = 'Nuevo usuario'
    success_url = reverse_lazy('accounts:usuario_lista')
    mensaje_exito = 'Usuario creado correctamente.'


class UsuarioEditar(EditarView):
    permiso = 'usuarios'
    model = Usuario
    form_class = UsuarioEditarForm
    titulo = 'Editar usuario'
    success_url = reverse_lazy('accounts:usuario_lista')

    def form_valid(self, form):
        if self.object.pk == self.request.user.pk and not form.cleaned_data['is_active']:
            form.add_error('is_active', 'No puede desactivar su propio usuario.')
            return self.form_invalid(form)
        return super().form_valid(form)


class UsuarioEliminar(EliminarView):
    permiso = 'usuarios'
    model = Usuario
    titulo = 'Eliminar usuario'
    success_url = reverse_lazy('accounts:usuario_lista')

    def form_valid(self, form):
        if self.object.pk == self.request.user.pk:
            messages.error(self.request, 'No puede eliminar su propio usuario.')
            return redirect(self.success_url)
        return super().form_valid(form)


@permiso_requerido('usuarios')
def usuario_clave(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    form = RestablecerClaveForm(usuario, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Contraseña de {usuario.username} restablecida.')
        return redirect('accounts:usuario_lista')
    return render(request, 'core/form.html', {
        'titulo': f'Restablecer contraseña de {usuario.username}', 'form': form,
        'url_cancelar': reverse_lazy('accounts:usuario_lista'),
    })


@permiso_requerido('usuarios')
@require_POST
def usuario_estado(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    if usuario.pk == request.user.pk:
        messages.error(request, 'No puede desactivar su propio usuario.')
    else:
        usuario.is_active = not usuario.is_active
        usuario.save(update_fields=['is_active'])
        messages.success(request, f'Usuario {usuario.username} {"activado" if usuario.is_active else "desactivado"}.')
    return redirect('accounts:usuario_lista')
