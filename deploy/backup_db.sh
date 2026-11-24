#!/bin/sh
# Respaldo lógico de la base de datos (además de los snapshots automáticos de RDS).
# Uso:  ./deploy/backup_db.sh            (lee /opt/farmacia/.env)
# Opcional: BACKUP_S3_URI=s3://mi-bucket-respaldos/farmacia  para subirlo a S3 (requiere aws cli + rol IAM).
set -e
set -a; . "${ENV_FILE:-/opt/farmacia/.env}"; set +a
DESTINO="${BACKUP_DIR:-/opt/farmacia/backups}"
mkdir -p "$DESTINO"
ARCHIVO="$DESTINO/farmacia_$(date +%Y%m%d_%H%M%S).sql.gz"
PGPASSWORD="$DB_PASSWORD" pg_dump -h "$DB_HOST" -p "${DB_PORT:-5432}" -U "$DB_USER" "$DB_NAME" | gzip > "$ARCHIVO"
echo "Respaldo creado: $ARCHIVO"
if [ -n "$BACKUP_S3_URI" ]; then aws s3 cp "$ARCHIVO" "$BACKUP_S3_URI/"; fi
find "$DESTINO" -name 'farmacia_*.sql.gz' -mtime +14 -delete
