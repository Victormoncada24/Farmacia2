from django.urls import path

from . import views

app_name = 'inventario'

urlpatterns = [
    path('', views.StockLista.as_view(), name='stock'),
    path('productos/', views.ProductoLista.as_view(), name='producto_lista'),
    path('productos/nuevo/', views.ProductoCrear.as_view(), name='producto_crear'),
    path('productos/<int:pk>/', views.ProductoDetalle.as_view(), name='producto_detalle'),
    path('productos/<int:pk>/editar/', views.ProductoEditar.as_view(), name='producto_editar'),
    path('productos/<int:pk>/eliminar/', views.ProductoEliminar.as_view(), name='producto_eliminar'),
    path('categorias/', views.CategoriaLista.as_view(), name='categoria_lista'),
    path('categorias/nueva/', views.CategoriaCrear.as_view(), name='categoria_crear'),
    path('categorias/<int:pk>/editar/', views.CategoriaEditar.as_view(), name='categoria_editar'),
    path('categorias/<int:pk>/eliminar/', views.CategoriaEliminar.as_view(), name='categoria_eliminar'),
    path('lotes/', views.LoteLista.as_view(), name='lote_lista'),
    path('lotes/ingreso/', views.ingreso_lote, name='ingreso_lote'),
    path('transferir/', views.transferir, name='transferir'),
    path('ajuste/', views.ajuste, name='ajuste'),
    path('movimientos/', views.MovimientoLista.as_view(), name='movimiento_lista'),
]
