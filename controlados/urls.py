from django.urls import path

from . import views

app_name = 'controlados'

urlpatterns = [
    path('', views.LibroLista.as_view(), name='libro'),
    path('<int:pk>/firmar/', views.firmar, name='firmar'),
    path('firmar-pendientes/', views.firmar_pendientes, name='firmar_pendientes'),
    path('cuadratura/', views.cuadratura, name='cuadratura'),
    path('conteo/nuevo/', views.conteo_nuevo, name='conteo_nuevo'),
    path('conteo/<int:pk>/resolver/', views.conteo_resolver, name='conteo_resolver'),
]
