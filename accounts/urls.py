from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    path('ingresar/', views.IngresoView.as_view(), name='login'),
    path('salir/', LogoutView.as_view(), name='logout'),
    path('perfil/', views.perfil, name='perfil'),
    path('cambiar-clave/', views.CambiarClaveView.as_view(), name='cambiar_clave'),
    path('roles/', views.roles_permisos, name='roles'),
    path('usuarios/', views.UsuarioLista.as_view(), name='usuario_lista'),
    path('usuarios/nuevo/', views.UsuarioCrear.as_view(), name='usuario_crear'),
    path('usuarios/<int:pk>/editar/', views.UsuarioEditar.as_view(), name='usuario_editar'),
    path('usuarios/<int:pk>/eliminar/', views.UsuarioEliminar.as_view(), name='usuario_eliminar'),
    path('usuarios/<int:pk>/clave/', views.usuario_clave, name='usuario_clave'),
    path('usuarios/<int:pk>/estado/', views.usuario_estado, name='usuario_estado'),
]
