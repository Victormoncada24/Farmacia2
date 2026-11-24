from django.contrib import admin

from .models import Categoria, Lote, MovimientoInventario, Producto, StockLote

admin.site.register(Categoria)
admin.site.register(Producto)
admin.site.register(Lote)
admin.site.register(StockLote)
admin.site.register(MovimientoInventario)
