from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import DetailView

from core.views import (CrearView, EditarView, EliminarView, ListaGenericaView, RolRequeridoMixin,
                        permiso_requerido)

from .forms import CuotaForm, InscripcionForm, PacienteFiltro, PacienteForm, ProgramaForm
from .models import CuotaPrograma, InscripcionPrograma, Paciente, Programa


class PacienteLista(ListaGenericaView):
    permiso = 'ver_pacientes'
    permiso_edicion = 'gestionar_pacientes'
    model = Paciente
    titulo = 'Pacientes'
    columnas = (('Documento', 'documento'), ('Nombre', 'nombre_completo'), ('Edad', 'edad'),
                ('Previsión', 'get_prevision_display'), ('Activo', 'activo'))
    campos_busqueda = ('documento', 'nombres', 'apellidos')
    form_filtro = PacienteFiltro
    url_crear = 'pacientes:crear'
    etiqueta_crear = 'Nuevo paciente'
    url_detalle = 'pacientes:detalle'
    url_editar = 'pacientes:editar'

    def aplicar_filtros(self, qs, datos):
        if datos.get('programa'):
            qs = qs.filter(inscripciones__programa=datos['programa'], inscripciones__activo=True).distinct()
        return qs


class PacienteDetalle(RolRequeridoMixin, DetailView):
    permiso = 'ver_pacientes'
    model = Paciente
    template_name = 'pacientes/detalle.html'
    context_object_name = 'paciente'

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        paciente = self.object
        contexto['titulo'] = paciente.nombre_completo
        contexto['inscripciones'] = paciente.inscripciones.select_related('programa')
        contexto['recetas'] = paciente.recetas.select_related('programa')[:10]
        contexto['dispensaciones'] = paciente.dispensaciones.select_related('dispensado_por', 'programa')[:10]
        return contexto


class PacienteCrear(CrearView):
    permiso = 'gestionar_pacientes'
    model = Paciente
    form_class = PacienteForm
    titulo = 'Nuevo paciente'
    success_url = reverse_lazy('pacientes:lista')
    mensaje_exito = 'Paciente registrado.'

    def get_success_url(self):
        return reverse('pacientes:detalle', args=[self.object.pk])


class PacienteEditar(EditarView):
    permiso = 'gestionar_pacientes'
    model = Paciente
    form_class = PacienteForm
    titulo = 'Editar paciente'
    success_url = reverse_lazy('pacientes:lista')

    def get_success_url(self):
        return reverse('pacientes:detalle', args=[self.object.pk])


# -------------------------------------------------------- Programas (catálogo)
class ProgramaLista(ListaGenericaView):
    permiso = 'ver_pacientes'
    permiso_edicion = 'configurar_programas'
    model = Programa
    titulo = 'Programas de salud (GES/AUGE y crónicos)'
    columnas = (('Nombre', 'nombre'), ('Tipo', 'get_tipo_display'), ('Descripción', 'descripcion'),
                ('Activo', 'activo'))
    campos_busqueda = ('nombre',)
    url_crear = 'pacientes:programa_crear'
    etiqueta_crear = 'Nuevo programa'
    url_editar = 'pacientes:programa_editar'
    url_eliminar = 'pacientes:programa_eliminar'


class ProgramaCrear(CrearView):
    permiso = 'configurar_programas'
    model = Programa
    form_class = ProgramaForm
    titulo = 'Nuevo programa de salud'
    success_url = reverse_lazy('pacientes:programa_lista')


class ProgramaEditar(EditarView):
    permiso = 'configurar_programas'
    model = Programa
    form_class = ProgramaForm
    titulo = 'Editar programa de salud'
    success_url = reverse_lazy('pacientes:programa_lista')


class ProgramaEliminar(EliminarView):
    permiso = 'configurar_programas'
    model = Programa
    titulo = 'Eliminar programa'
    success_url = reverse_lazy('pacientes:programa_lista')


# ------------------------------------------------------------ Inscripciones
@permiso_requerido('gestionar_pacientes')
def inscripcion_crear(request, paciente_id):
    paciente = get_object_or_404(Paciente, pk=paciente_id)
    form = InscripcionForm(request.POST or None, paciente=paciente)
    if request.method == 'POST' and form.is_valid():
        inscripcion = form.save(commit=False)
        inscripcion.paciente = paciente
        inscripcion.save()
        messages.success(request, 'Paciente inscrito. Ahora defina las cuotas mensuales cubiertas.')
        return redirect('pacientes:inscripcion_detalle', pk=inscripcion.pk)
    return render(request, 'core/form.html', {
        'titulo': f'Inscribir a {paciente.nombre_completo} en un programa', 'form': form,
        'url_cancelar': reverse('pacientes:detalle', args=[paciente.pk]),
    })


@permiso_requerido('ver_pacientes')
def inscripcion_detalle(request, pk):
    inscripcion = get_object_or_404(InscripcionPrograma.objects.select_related('paciente', 'programa'), pk=pk)
    form = CuotaForm(request.POST or None, inscripcion=inscripcion)
    if request.method == 'POST':
        if not request.user.puede('gestionar_pacientes'):
            messages.error(request, 'No tiene permiso para modificar cuotas.')
            return redirect('pacientes:inscripcion_detalle', pk=pk)
        if form.is_valid():
            cuota = form.save(commit=False)
            cuota.inscripcion = inscripcion
            cuota.save()
            messages.success(request, 'Cuota agregada.')
            return redirect('pacientes:inscripcion_detalle', pk=pk)
    return render(request, 'pacientes/inscripcion_detalle.html', {
        'titulo': f'{inscripcion.programa.nombre} — {inscripcion.paciente.nombre_completo}',
        'inscripcion': inscripcion, 'cuotas': inscripcion.cuotas.select_related('producto'), 'form': form,
    })


@permiso_requerido('gestionar_pacientes')
@require_POST
def cuota_eliminar(request, pk):
    cuota = get_object_or_404(CuotaPrograma, pk=pk)
    inscripcion_id = cuota.inscripcion_id
    cuota.delete()
    messages.success(request, 'Cuota eliminada.')
    return redirect('pacientes:inscripcion_detalle', pk=inscripcion_id)


@permiso_requerido('gestionar_pacientes')
@require_POST
def inscripcion_cerrar(request, pk):
    inscripcion = get_object_or_404(InscripcionPrograma, pk=pk)
    inscripcion.activo = False
    inscripcion.fecha_termino = timezone.localdate()
    inscripcion.save(update_fields=['activo', 'fecha_termino'])
    messages.success(request, 'Inscripción cerrada.')
    return redirect('pacientes:detalle', pk=inscripcion.paciente_id)
