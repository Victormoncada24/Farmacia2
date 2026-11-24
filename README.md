# Simulador de Farmacia Asistencial — INACAP

Proyecto Integrado AP-N4-C1 · INACAP · Django 5.2 · Área solicitante: Dirección de Carrera (Nataly Caamaño).

Plataforma web que simula la operación de una **farmacia asistencial de la red pública de salud**:
inventario con lotes y FEFO, dispensación gratuita a pacientes GES/AUGE y crónicos con control de cuotas,
carros clínicos (Carro de Paro y Unidosis), libro digital de medicamentos controlados (ISP), alertas,
dashboard en tiempo real y reportes exportables a PDF/Excel. Sigue las exclusiones del cliente: **no** incluye
ventas, POS, boletas/facturas, convenios Isapre ni precios/descuentos (eso corresponde a la farmacia privada).

## 1. Puesta en marcha

Requisitos: Python 3.11+ (probado el diseño para 3.12) y acceso a internet en el navegador
(Bootstrap y Chart.js se cargan por CDN).

```bash
cd farmacia_asistencial
python -m venv venv
# Linux/Mac:  source venv/bin/activate        Windows:  venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # Windows: copy .env.example .env   (opcional en desarrollo)

python manage.py makemigrations
python manage.py migrate
python manage.py cargar_datos_demo      # datos de ejemplo (recomendado para la presentación)
python manage.py runserver
```

Abrir http://127.0.0.1:8000/ . Para usar PostgreSQL local: `docker compose up --build` (ver `docs/DESPLIEGUE_AWS.md`). Con los datos demo, la contraseña de todos es `Inacap2026!!`:

| Usuario   | Rol                    | Qué probar |
|-----------|------------------------|-----------|
| `admin`   | Administrador          | Usuarios, roles, auditoría, reportes globales |
| `quimico` | Químico Farmacéutico   | Firmar libro de controlados, ajustes/mermas, excepciones de cuota, anular recetas, conteos |
| `tecnico` | Técnico en Farmacia    | Dispensar, ingresar remesas, transferir bodega↔vitrina, reponer carros |
| `clinico` | Personal Clínico       | Solicitar reposición y registrar consumos de carros; consultar disponibilidad |

> Nota: las migraciones se generan con `makemigrations` (no se incluyen precompiladas). Si ya tenía una base de datos
> de una versión anterior, ejecute de nuevo `makemigrations` y `migrate`: se agregaron el módulo de pedidos y un
> campo en las alertas.

Pruebas automatizadas: `python manage.py test`

## 2. Trazabilidad con su levantamiento de requerimientos

| Requerimiento | Dónde está implementado |
|---|---|
| RF-01 Gestión de usuarios (RUT, nombre, teléfono) | `accounts` · Usuarios (crear, editar, activar/desactivar, restablecer clave, eliminar con protección) |
| RF-02 Gestión de roles | `core/roles.py` + pantalla *Roles y permisos* (matriz por rol) |
| RF-03/04 Inventario, bodega y vitrina | `inventario` · productos, categorías, stock separado por ubicación, transferencias |
| RF-05 Lotes y vencimientos | `inventario.Lote` · ingreso/remesa (CENABAST u otros), estado de vencimiento |
| FEFO | `inventario/services.py::descontar_fefo` (primero en vencer, primero en salir; ignora lotes vencidos) |
| RF-06 / RF-07 Alertas de stock y vencimiento | `alertas` · se evalúan tras **cada movimiento** y en el dashboard; se cierran solas al corregir la causa |
| RF-08 / RF-09 Recetas y dispensación | `dispensacion` · receta física/digital, validación de RUT, médico, vigencia, saldo; dispensación atómica |
| RF-10 Programas GES/AUGE y crónicos | `pacientes` · inscripciones + **cuotas mensuales por producto**; cobertura validada al dispensar |
| RF-11 Trazabilidad de entregas | Quién retira (paciente o tercero: nombre, RUT, relación, ej. «Padre»), fecha/hora, lote entregado, comprobante imprimible |
| RF-12 / RF-13 Carro de Paro / Unidosis | `carros` · dotación, contenido actual, vencimiento más próximo, precinto |
| RF-14 Reposición de carros | Reposición con **conteo físico** (registra diferencias) + solicitudes del personal clínico atendidas por Farmacia |
| RF-15 Dashboard en tiempo real | `reportes` · KPIs y gráficos; se refresca cada 30 s (`/api/dashboard/`) |
| RF-16 Reportes PDF/Excel | 13 informes en `reportes/informes.py` (stock, vencimientos, pedido sugerido, dispensaciones, cuotas, libro ISP, carros, auditoría…) |
| RF-17 Historial de movimientos | `MovimientoInventario`, historial de dispensaciones, consumos y reposiciones |
| Medicamentos controlados (ISP) | `controlados` · libro digital con saldo correlativo, firma del Q.F., cuadratura y conteos físicos con alerta de descuadre |
| Imprimir orden con plantilla | Comprobante de dispensación y orden de reposición de carro (HTML para imprimir) |
| Seguridad y privacidad | Ver sección 4 |

Criterios medibles de su informe: alerta de stock crítico generada en el mismo movimiento (< 2 s); historial con
fecha, hora y usuario; reportes exportables PDF/Excel.

## 3. Estructura

```
config/         settings, urls, wsgi/asgi
core/           roles y permisos, validación de RUT, campos cifrados, validador de archivos,
                vistas genéricas, exportadores PDF/Excel, comando cargar_datos_demo
accounts/       usuario personalizado (RUT, teléfono, rol), login con bloqueo, CRUD de usuarios
auditoria/      bitácora inmutable (accesos, altas/cambios/bajas, exportaciones, acceso a archivos)
inventario/     productos, categorías, lotes, stock por ubicación, movimientos, FEFO
alertas/        stock crítico, vencimientos, carros, descuadres de controlados
pacientes/      pacientes (datos sensibles cifrados), programas, inscripciones, cuotas
dispensacion/   recetas, dispensación, historial, comprobante
carros/         carros clínicos, dotación, reposición, consumo, solicitudes
controlados/    libro digital ISP, firmas, cuadratura
reportes/       dashboard + informes exportables
templates/  static/
```

## 4. Seguridad implementada

- **Autenticación**: contraseñas con PBKDF2 (Django), mínimo 10 caracteres, validadores estándar; bloqueo temporal
  tras 5 intentos fallidos; cierre de sesión por inactividad a los 30 min.
- **Autorización por roles** en cada vista (`permiso_requerido` / `RolRequeridoMixin`) y menús diferenciados por rol.
- **Cifrado de datos sensibles** (Fernet/AES): teléfono, dirección y correo del paciente, diagnóstico y observaciones
  clínicas. La clave sale de `FIELD_ENCRYPTION_KEY` (¡respáldela! sin ella no se pueden descifrar). Los campos cifrados
  no se pueden usar en búsquedas.
- **Validación de archivos subidos**: solo PDF/JPG/PNG, máx. 5 MB, verificación de la firma binaria real del archivo,
  nombre aleatorio, y **no se sirven públicamente**: solo mediante una vista autenticada que además audita el acceso.
- **Auditoría**: usuario, fecha, hora e IP de accesos, cambios, exportaciones y accesos a archivos; registros inmutables.
- **Integridad**: operaciones de stock atómicas (todo o nada), protección contra eliminación de datos con historial,
  CSRF, cookies HttpOnly/SameSite, y con `DJANGO_DEBUG=False` cookies seguras, HSTS y redirección a HTTPS.

## 5. Despliegue e integración con el sitio de INACAP

Es una aplicación Django independiente. Las formas habituales de integrarla:

1. **Subdominio propio** (recomendado), p. ej. `farmacia.inacap.cl`, servido con `gunicorn config.wsgi` detrás de
   Nginx/Apache con HTTPS. Variables: `DJANGO_DEBUG=False`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`,
   `DJANGO_CSRF_TRUSTED_ORIGINS=https://farmacia.inacap.cl`, `DJANGO_DETRAS_DE_PROXY=True`, `DB_ENGINE=postgres`…
   Luego `python manage.py collectstatic` (WhiteNoise sirve los estáticos).
2. **Subdirectorio** (p. ej. `https://www.inacap.cl/farmacia/`): definir `DJANGO_SCRIPT_NAME=/farmacia` y
   `DJANGO_STATIC_URL=/farmacia/static/`, y enrutar ese prefijo desde el servidor web.
3. **Enlace o `<iframe>`** desde una página existente: el enlace es lo más simple. Para `<iframe>` hay que activar
   `DJANGO_PERMITIR_IFRAME=True`, y las cookies de sesión requieren `SameSite=None; Secure`; se desaconseja por seguridad.

## 6. Limitaciones conocidas y mejoras futuras

- **No se pudo ejecutar el código en el entorno donde fue generado** (sin acceso a instalar Django). Se verificó
  sintaxis, imports entre módulos, nombres, URLs y plantillas con análisis estático, pero **debe ejecutar
  `python manage.py test` y recorrer el sistema con los datos demo** antes de entregar; si aparece algún error,
  es esperable que sea menor y rápido de corregir.
- Los *pacientes* no inician sesión: son entidades atendidas por el personal (sus «funciones» del levantamiento se
  cubren con el registro de retiro y la validación de cobertura).
- El Carro Unidosis se modela a nivel de producto/carro (no por cama o paciente).
- No hay anulación de dispensaciones (requeriría reversar stock y libro); sí anulación de recetas.
- Interoperabilidad real con Fonasa/CENABAST/ISP queda como fase futura (el levantamiento la menciona como tendencia).
- Sugerencia Scrum para fases: (1) usuarios/roles/inventario/dispensación, (2) programas y cuotas, (3) carros,
  (4) controlados y reportes, (5) endurecimiento de seguridad y despliegue.


## 7. Módulos agregados

### 7.1 Pedidos a proveedores (`pedidos`)
Permite al establecimiento solicitar medicamentos e insumos a sus proveedores (CENABAST, Servicio de Salud, droguerías,
laboratorios) y recibirlos contra el pedido.

| Paso | Quién | Qué ocurre |
|---|---|---|
| 1. Crear borrador | Técnico o Q.F. | Elige proveedor, prioridad y productos con cantidades. Puede crearse a mano o **con un clic desde Abastecimiento inteligente** (pedido sugerido). |
| 2. Autorizar y enviar | **Solo Q.F.** | El pedido pasa a *Enviado*; se calcula la **entrega estimada** con el plazo del proveedor. |
| 3. Recepcionar | Técnico o Q.F. | Se registra guía/factura, lote y vencimiento de lo que llegó. **Alimenta el inventario** (lote + stock) y, si es controlado, el libro digital. Admite entregas parciales. |
| 4. Cierre | Q.F. | *Recibido* (completo) o *Cerrado con faltantes*; un pedido enviado sin recepciones puede *Anularse*. |

Integraciones: el **pedido sugerido descuenta lo que ya viene en camino**; un pedido que pasa su fecha estimada genera
la alerta **«Pedido a proveedor atrasado»**; hay orden de pedido imprimible, informe PDF/Excel y auditoría de cada paso.

### 7.2 Inteligencia de abastecimiento y adherencia (`analitica`) — valor agregado
- **Abastecimiento inteligente**: consumo diario, días de cobertura, fecha estimada de quiebre, **pérdida proyectada por
  vencimiento** (simulación FEFO), clasificación ABC y pedido sugerido. Genera alertas *antes* de que ocurra el quiebre.
- **Adherencia de pacientes**: detecta pacientes GES/crónicos que no han retirado sus medicamentos (atrasados / riesgo de
  abandono) y muestra su teléfono de contacto para llamarlos.
- Responde a lo pedido por el cliente: *«monitoreo inteligente de existencias para evitar el desabastecimiento o la
  pérdida de medicamentos por caducidad»*.

### 7.3 Nombre de la plataforma
Se muestra «Simulador de Farmacia Asistencial · Plataforma de simulación académica · INACAP». Se cambia sin tocar
código con las variables `APP_NOMBRE` y `APP_SUBTITULO` (ver `.env.example`).

### 7.4 PostgreSQL y AWS
Configuración para RDS (SSL, conexiones persistentes), endpoint `/salud/`, Docker, Nginx, systemd, respaldos y recetas
en S3: ver **`docs/DESPLIEGUE_AWS.md`**.

### 7.5 Pruebas
- `python manage.py test` — suite completa (requiere Django instalado).
- Sin Django: `python -m unittest analitica.test_calculos pedidos.test_logica` — lógica pura de cobertura, riesgo de
  vencimiento, pedido sugerido, ABC, adherencia y ciclo de vida de pedidos (**29 pruebas**, ejecutadas con éxito al
  construir esta versión).
