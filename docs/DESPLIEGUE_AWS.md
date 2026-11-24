# Despliegue en AWS (EC2 + RDS PostgreSQL + Nginx)

Arquitectura recomendada para un proyecto académico: simple, económica y con prácticas reales de producción.

```
Internet ──► Nginx (EC2, HTTPS) ──► gunicorn ──► Django ──► RDS PostgreSQL (acceso solo desde la EC2, cifrado)
                                                   └──────► S3 privado (recetas escaneadas, opcional)
```

> **Datos**: es una **plataforma de simulación académica**. No cargue datos reales de pacientes. Si algún día se usara
> con datos reales, aplicarían la Ley 19.628 (datos personales) y la Ley 20.584 (derechos de los pacientes).

## 0. Antes de subir: genere las migraciones en su equipo

En producción no se generan migraciones en el servidor. Hágalo en su computador y súbalas con el código:

```bash
python manage.py makemigrations
git add */migrations/0*.py
```

## 1. Base de datos: Amazon RDS for PostgreSQL

1. Consola AWS → región **sa-east-1 (São Paulo)** → *RDS* → *Create database*.
2. Motor **PostgreSQL 16**, plantilla **Free tier / Dev-Test**, instancia `db.t4g.micro` o `db.t3.micro`.
3. *DB instance identifier*: `farmacia-db`. Usuario maestro: `farmacia_admin` y una contraseña larga (guárdela).
4. Almacenamiento 20 GB gp3, **Encryption habilitado**, **Public access: No**, respaldos automáticos 7 días.
5. En *Additional configuration* → **Initial database name: `farmacia`**.
6. Asigne el security group `sg-db` (paso 2). Anote el **endpoint** (`farmacia-db.xxxx.sa-east-1.rds.amazonaws.com`).

## 2. Red y servidor: Security Groups + EC2

| Security group | Entrada |
|---|---|
| `sg-web` | 80 y 443 desde `0.0.0.0/0`; 22 **solo desde su IP** |
| `sg-db`  | 5432 **solo desde `sg-web`** (la base nunca es accesible desde internet) |

**EC2**: Ubuntu Server 24.04 LTS, `t3.micro` (o `t3.small` si la demo va lenta), `sg-web`, 20 GB, par de claves `.pem`.
Asigne una **Elastic IP** para que la dirección no cambie al reiniciar.

## 3. Preparar el servidor

```bash
ssh -i clave.pem ubuntu@<ELASTIC_IP>
sudo apt update && sudo apt install -y python3-venv python3-pip nginx postgresql-client unzip
sudo mkdir -p /opt/farmacia && sudo chown ubuntu:ubuntu /opt/farmacia
```

Suba el proyecto (ZIP o `git clone`):

```bash
scp -i clave.pem farmacia_asistencial.zip ubuntu@<ELASTIC_IP>:/opt/farmacia/
# en el servidor:
cd /opt/farmacia && unzip farmacia_asistencial.zip && mv farmacia_asistencial app
python3 -m venv venv && ./venv/bin/pip install -r app/requirements.txt
```

## 4. Variables de entorno (`/opt/farmacia/.env`)

```bash
cp app/.env.example .env && nano .env && chmod 600 .env
```

```ini
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<python3 -c "import secrets; print(secrets.token_urlsafe(60))">
FIELD_ENCRYPTION_KEY=<python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
DJANGO_ALLOWED_HOSTS=farmacia.midominio.cl,<ELASTIC_IP>
DJANGO_CSRF_TRUSTED_ORIGINS=https://farmacia.midominio.cl
DJANGO_DETRAS_DE_PROXY=True
DJANGO_HTTPS=True

DB_ENGINE=postgres
DB_NAME=farmacia
DB_USER=farmacia_admin
DB_PASSWORD=<contraseña de RDS>
DB_HOST=farmacia-db.xxxx.sa-east-1.rds.amazonaws.com
DB_PORT=5432
DB_SSLMODE=require
```

> ⚠️ **Respalde `FIELD_ENCRYPTION_KEY` y `DJANGO_SECRET_KEY` fuera del servidor.** Si pierde la clave de cifrado, los
> teléfonos, direcciones y diagnósticos quedan irrecuperables.
>
> Primera prueba sin dominio ni HTTPS: use `DJANGO_HTTPS=False` temporalmente y acceda por `http://<ELASTIC_IP>`.

## 5. Inicializar la aplicación

```bash
cd /opt/farmacia/app
set -a; . /opt/farmacia/.env; set +a
../venv/bin/python manage.py migrate
../venv/bin/python manage.py collectstatic --noinput
../venv/bin/python manage.py createsuperuser          # o: cargar_datos_demo (solo demostración)
../venv/bin/python manage.py check --deploy
```

## 6. Servicio (gunicorn) y Nginx

```bash
sudo cp deploy/farmacia.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now farmacia
sudo systemctl status farmacia

sudo cp deploy/nginx.conf /etc/nginx/sites-available/farmacia     # edite server_name
sudo ln -s /etc/nginx/sites-available/farmacia /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

## 7. Dominio y HTTPS

1. DNS: registro **A** `farmacia.midominio.cl → <ELASTIC_IP>`.
2. `sudo apt install -y certbot python3-certbot-nginx && sudo certbot --nginx -d farmacia.midominio.cl`
3. Compruebe `https://farmacia.midominio.cl/salud/` → `{"estado": "ok"}`.

## 8. Recetas escaneadas en S3 (opcional)

1. S3 → bucket privado (`farmacia-recetas-<algo-unico>`, sa-east-1), **Block all public access** y cifrado por defecto.
2. IAM → rol para EC2 con permisos `s3:PutObject/GetObject/DeleteObject` sobre `arn:aws:s3:::BUCKET/*` y
   `s3:ListBucket` sobre `arn:aws:s3:::BUCKET`; asígnelo a la instancia.
3. `./venv/bin/pip install -r app/requirements-aws.txt` y en `.env`: `AWS_STORAGE_BUCKET_NAME=...`,
   `AWS_S3_REGION_NAME=sa-east-1`. Reinicie: `sudo systemctl restart farmacia`.

Los archivos siguen sin ser públicos: solo se entregan por la vista autenticada del sistema (que audita el acceso).

## 9. Respaldos

- **RDS**: respaldos automáticos y un snapshot manual antes de cada entrega.
- **Lógico**: `deploy/backup_db.sh` (pg_dump comprimido, conserva 14 días). Cron:
  `0 3 * * * /opt/farmacia/app/deploy/backup_db.sh >> /opt/farmacia/backup.log 2>&1`
- Respalde también `.env`. Pruebe restaurar al menos una vez.

## 10. Actualizar la aplicación

```bash
cd /opt/farmacia/app && git pull            # o suba el nuevo ZIP
set -a; . /opt/farmacia/.env; set +a
../venv/bin/pip install -r requirements.txt
../venv/bin/python manage.py migrate && ../venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart farmacia
```

## Solución de problemas

| Síntoma | Causa probable |
|---|---|
| `Bad Request (400)` | El dominio/IP no está en `DJANGO_ALLOWED_HOSTS`. |
| `502 Bad Gateway` | gunicorn caído: `sudo journalctl -u farmacia -n 50`. |
| Formularios responden `403 CSRF` | Falta `DJANGO_CSRF_TRUSTED_ORIGINS=https://…` o `DJANGO_DETRAS_DE_PROXY=True`. |
| Redirección infinita | `DJANGO_DETRAS_DE_PROXY` en `False` con HTTPS en Nginx. |
| `could not connect to server` (RDS) | `sg-db` no permite 5432 desde `sg-web`, o endpoint/clave mal escritos. |
| Página sin estilos | Falta `collectstatic` o el servicio no se reinició. |
| Auditoría muestra siempre 127.0.0.1 | Nginx sin `X-Real-IP` o `DJANGO_DETRAS_DE_PROXY=False`. |

## Alternativa con contenedores

El proyecto incluye `Dockerfile` y `docker-compose.yml` (PostgreSQL local para desarrollo). La misma imagen puede
ejecutarse en **AWS App Runner** o **ECS Fargate** apuntando a la RDS; use `/salud/` como chequeo de salud y agregue el
DNS del balanceador a `DJANGO_ALLOWED_HOSTS`. Para este tamaño de proyecto, EC2 + RDS es más simple de explicar.
