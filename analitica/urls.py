from django.urls import path

from . import views

app_name = 'analitica'

urlpatterns = [
    path('abastecimiento/', views.abastecimiento, name='abastecimiento'),
    path('adherencia/', views.adherencia, name='adherencia'),
]
