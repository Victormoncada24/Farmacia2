from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (('Datos institucionales', {'fields': ('rut', 'telefono', 'rol')}),)
    add_fieldsets = UserAdmin.add_fieldsets + (('Datos institucionales', {'fields': ('rut', 'telefono', 'rol', 'email')}),)
    list_display = ('username', 'first_name', 'last_name', 'rut', 'rol', 'is_active')
    list_filter = ('rol', 'is_active')
