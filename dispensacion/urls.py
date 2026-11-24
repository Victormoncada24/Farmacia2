from django.urls import path

from . import views

app_name = 'dispensacion'

urlpatterns = [
    path('', views.HistorialLista.as_view(), name='historial'),
    path('nueva/', views.nueva, name='nueva'),
    path('<int:pk>/', views.detalle, name='detalle'),
    path('<int:pk>/imprimir/', views.comprobante, name='comprobante'),
    path('recetas/', views.RecetaLista.as_view(), name='receta_lista'),
    path('recetas/nueva/<int:paciente_id>/', views.receta_crear, name='receta_crear'),
    path('recetas/<int:pk>/', views.receta_detalle, name='receta_detalle'),
    path('recetas/<int:pk>/anular/', views.receta_anular, name='receta_anular'),
    path('recetas/<int:pk>/archivo/', views.receta_archivo, name='receta_archivo'),
    path('recetas/<int:receta_id>/dispensar/', views.dispensar, name='dispensar'),
]
