from django.contrib import admin

from .models import Pedido, PedidoItem, Proveedor, Recepcion, RecepcionItem

for modelo in (Proveedor, Pedido, PedidoItem, Recepcion, RecepcionItem):
    admin.site.register(modelo)
