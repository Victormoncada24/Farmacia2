from django.contrib import admin

from .models import ConteoFisico, MovimientoControlado

admin.site.register(MovimientoControlado)
admin.site.register(ConteoFisico)
