from django.urls import path

from . import views

app_name = 'pedidos'

urlpatterns = [
    path('', views.PedidoLista.as_view(), name='lista'),
    path('nuevo/', views.crear, name='crear'),
    path('desde-sugerencia/', views.desde_sugerencia, name='desde_sugerencia'),
    path('<int:pk>/', views.detalle, name='detalle'),
    path('<int:pk>/editar/', views.editar, name='editar'),
    path('<int:pk>/eliminar/', views.eliminar, name='eliminar'),
    path('<int:pk>/enviar/', views.enviar, name='enviar'),
    path('<int:pk>/anular/', views.anular, name='anular'),
    path('<int:pk>/cerrar/', views.cerrar, name='cerrar'),
    path('<int:pk>/recepcionar/', views.recepcionar, name='recepcionar'),
    path('<int:pk>/imprimir/', views.orden, name='orden'),
    path('proveedores/', views.ProveedorLista.as_view(), name='proveedor_lista'),
    path('proveedores/nuevo/', views.ProveedorCrear.as_view(), name='proveedor_crear'),
    path('proveedores/<int:pk>/editar/', views.ProveedorEditar.as_view(), name='proveedor_editar'),
    path('proveedores/<int:pk>/eliminar/', views.ProveedorEliminar.as_view(), name='proveedor_eliminar'),
]
