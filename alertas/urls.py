from django.urls import path

from . import views

app_name = 'alertas'

urlpatterns = [
    path('', views.AlertaLista.as_view(), name='lista'),
    path('recalcular/', views.recalcular, name='recalcular'),
    path('<int:pk>/resolver/', views.resolver, name='resolver'),
]
