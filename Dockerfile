FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt requirements-aws.txt ./
RUN pip install --no-cache-dir -r requirements-aws.txt

COPY . .
RUN chmod +x deploy/entrypoint.sh && useradd -m app && chown -R app /app
USER app

EXPOSE 8000
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "-c", "deploy/gunicorn.conf.py"]
