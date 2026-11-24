from django.urls import path

from . import views

app_name = 'pacientes'

urlpatterns = [
    path('', views.PacienteLista.as_view(), name='lista'),
    path('nuevo/', views.PacienteCrear.as_view(), name='crear'),
    path('<int:pk>/', views.PacienteDetalle.as_view(), name='detalle'),
    path('<int:pk>/editar/', views.PacienteEditar.as_view(), name='editar'),
    path('<int:paciente_id>/inscribir/', views.inscripcion_crear, name='inscripcion_crear'),
    path('inscripciones/<int:pk>/', views.inscripcion_detalle, name='inscripcion_detalle'),
    path('inscripciones/<int:pk>/cerrar/', views.inscripcion_cerrar, name='inscripcion_cerrar'),
    path('cuotas/<int:pk>/eliminar/', views.cuota_eliminar, name='cuota_eliminar'),
    path('programas/', views.ProgramaLista.as_view(), name='programa_lista'),
    path('programas/nuevo/', views.ProgramaCrear.as_view(), name='programa_crear'),
    path('programas/<int:pk>/editar/', views.ProgramaEditar.as_view(), name='programa_editar'),
    path('programas/<int:pk>/eliminar/', views.ProgramaEliminar.as_view(), name='programa_eliminar'),
]
