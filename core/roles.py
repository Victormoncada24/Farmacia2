"""Roles institucionales y matriz de permisos del sistema.

Cada permiso es una clave -> (descripción, roles autorizados).
La matriz se muestra en la pantalla "Roles y permisos" (RF-02).
"""

ADMIN = 'ADMIN'
QUIMICO = 'QUIMICO'
TECNICO = 'TECNICO'
CLINICO = 'CLINICO'

CHOICES = [
    (ADMIN, 'Administrador'),
    (QUIMICO, 'Químico Farmacéutico'),
    (TECNICO, 'Técnico en Farmacia'),
    (CLINICO, 'Personal Clínico'),
]
NOMBRES = dict(CHOICES)
TODOS = (ADMIN, QUIMICO, TECNICO, CLINICO)

PERMISOS = {
    'usuarios': ('Administrar usuarios y roles', (ADMIN,)),
    'ver_inventario': ('Consultar inventario y disponibilidad', TODOS),
    'editar_catalogo': ('Crear y editar productos y categorías', (ADMIN, QUIMICO)),
    'mover_inventario': ('Ingresar lotes y transferir entre bodega y vitrina', (QUIMICO, TECNICO)),
    'ajustar_inventario': ('Ajustes, mermas y bajas de stock', (QUIMICO,)),
    'ver_pacientes': ('Consultar pacientes y programas', (ADMIN, QUIMICO, TECNICO)),
    'gestionar_pacientes': ('Registrar pacientes, inscripciones y cuotas', (QUIMICO, TECNICO)),
    'configurar_programas': ('Mantener catálogo de programas de salud', (ADMIN, QUIMICO)),
    'dispensar': ('Registrar recetas y dispensar medicamentos', (QUIMICO, TECNICO)),
    'ver_dispensaciones': ('Consultar recetas e historial de dispensaciones', (ADMIN, QUIMICO, TECNICO)),
    'autorizar': ('Autorizar procesos regulados (firmas, excepciones, anulaciones, conteos)', (QUIMICO,)),
    'ver_carros': ('Consultar carros clínicos', TODOS),
    'gestionar_carros': ('Reponer y atender solicitudes de carros clínicos', (QUIMICO, TECNICO)),
    'configurar_carros': ('Crear carros y definir su dotación', (ADMIN, QUIMICO)),
    'solicitar_reposicion': ('Solicitar reposición de carros', (QUIMICO, TECNICO, CLINICO)),
    'registrar_consumo': ('Registrar consumos de carros', (QUIMICO, TECNICO, CLINICO)),
    'ver_controlados': ('Consultar libro digital de controlados', (ADMIN, QUIMICO, TECNICO)),
    'ver_alertas': ('Consultar alertas', TODOS),
    'ver_analitica': ('Consultar abastecimiento inteligente y adherencia de pacientes', (ADMIN, QUIMICO, TECNICO)),
    'ver_pedidos': ('Consultar pedidos a proveedores y proveedores', (ADMIN, QUIMICO, TECNICO)),
    'gestionar_pedidos': ('Crear pedidos a proveedores y recepcionar mercadería', (QUIMICO, TECNICO)),
    'gestionar_proveedores': ('Mantener el catálogo de proveedores', (ADMIN, QUIMICO)),
    'ver_reportes': ('Ver y exportar reportes', (ADMIN, QUIMICO, TECNICO)),
    'auditoria': ('Consultar registro de auditoría', (ADMIN, QUIMICO)),
}


def roles_de(clave):
    return PERMISOS[clave][1]
