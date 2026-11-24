from django.contrib import admin

from .models import (CarroClinico, CarroItem, ConsumoCarro, ReposicionCarro, ReposicionDetalle,
                     SolicitudDetalle, SolicitudReposicion)

for modelo in (CarroClinico, CarroItem, ConsumoCarro, ReposicionCarro, ReposicionDetalle,
               SolicitudReposicion, SolicitudDetalle):
    admin.site.register(modelo)
