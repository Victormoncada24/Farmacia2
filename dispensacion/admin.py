from django.contrib import admin

from .models import Dispensacion, DispensacionItem, Receta, RecetaItem

admin.site.register(Receta)
admin.site.register(RecetaItem)
admin.site.register(Dispensacion)
admin.site.register(DispensacionItem)
