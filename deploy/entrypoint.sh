#!/bin/sh
# Prepara la aplicación antes de arrancar el servidor.
set -e

# SOLO desarrollo: genera migraciones si aún no se han creado/commiteadas.
# En producción genere las migraciones en su equipo y súbalas al repositorio.
if [ "${AUTO_MAKEMIGRATIONS:-0}" = "1" ]; then
  python manage.py makemigrations --noinput
fi

python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec "$@"
