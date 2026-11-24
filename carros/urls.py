from django.urls import path

from . import views

app_name = 'carros'

urlpatterns = [
    path('', views.CarroLista.as_view(), name='lista'),
    path('nuevo/', views.CarroCrear.as_view(), name='crear'),
    path('<int:pk>/', views.detalle, name='detalle'),
    path('<int:pk>/editar/', views.CarroEditar.as_view(), name='editar'),
    path('<int:pk>/eliminar/', views.CarroEliminar.as_view(), name='eliminar'),
    path('<int:carro_id>/items/agregar/', views.item_crear, name='item_crear'),
    path('items/<int:pk>/editar/', views.item_editar, name='item_editar'),
    path('items/<int:pk>/eliminar/', views.item_eliminar, name='item_eliminar'),
    path('<int:pk>/reponer/', views.reponer, name='reponer'),
    path('<int:pk>/consumo/', views.consumo, name='consumo'),
    path('<int:pk>/solicitar/', views.solicitar, name='solicitar'),
    path('solicitudes/', views.SolicitudLista.as_view(), name='solicitud_lista'),
    path('solicitudes/<int:pk>/', views.solicitud_detalle, name='solicitud_detalle'),
    path('solicitudes/<int:pk>/atender/', views.solicitud_atender, name='solicitud_atender'),
    path('solicitudes/<int:pk>/rechazar/', views.solicitud_rechazar, name='solicitud_rechazar'),
    path('solicitudes/<int:pk>/imprimir/', views.solicitud_orden, name='solicitud_orden'),
]
