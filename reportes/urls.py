from django.urls import path

from . import views

app_name = 'reportes'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('api/dashboard/', views.api_dashboard, name='api_dashboard'),
    path('reportes/', views.indice, name='indice'),
    path('reportes/<slug:slug>/', views.informe, name='informe'),
]
