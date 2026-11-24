import multiprocessing
import os

bind = os.environ.get('GUNICORN_BIND', '0.0.0.0:8000')
workers = int(os.environ.get('GUNICORN_WORKERS', min(2 * multiprocessing.cpu_count() + 1, 5)))
timeout = 60
accesslog = '-'
errorlog = '-'
