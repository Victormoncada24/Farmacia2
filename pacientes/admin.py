from django.contrib import admin

from .models import CuotaPrograma, InscripcionPrograma, Paciente, Programa

admin.site.register(Paciente)
admin.site.register(Programa)
admin.site.register(InscripcionPrograma)
admin.site.register(CuotaPrograma)
