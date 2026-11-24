from django import forms
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm, UserCreationForm, PasswordChangeForm

from core.forms import BootstrapFormMixin, FiltroBase
from core import roles

from .models import Usuario


class LoginForm(BootstrapFormMixin, AuthenticationForm):
    pass


class CambiarClaveForm(BootstrapFormMixin, PasswordChangeForm):
    pass


class RestablecerClaveForm(BootstrapFormMixin, SetPasswordForm):
    pass


class UsuarioCrearForm(BootstrapFormMixin, UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ('username', 'first_name', 'last_name', 'rut', 'email', 'telefono', 'rol')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nombre in ('first_name', 'last_name', 'email'):
            self.fields[nombre].required = True


class UsuarioEditarForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Usuario
        fields = ('first_name', 'last_name', 'rut', 'email', 'telefono', 'rol', 'is_active')
        labels = {'is_active': 'Usuario activo'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nombre in ('first_name', 'last_name', 'email'):
            self.fields[nombre].required = True


class UsuarioFiltro(FiltroBase):
    rol = forms.ChoiceField(label='Rol', required=False, choices=[('', 'Todos los roles')] + roles.CHOICES)
    estado = forms.ChoiceField(
        label='Estado', required=False,
        choices=[('', 'Todos'), ('activo', 'Activos'), ('inactivo', 'Inactivos')],
    )
