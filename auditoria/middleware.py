import contextvars

_request_actual = contextvars.ContextVar('auditoria_request', default=None)


def request_actual():
    return _request_actual.get()


class AuditoriaMiddleware:
    """Guarda el request en un contexto para que las señales sepan quién actúa."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _request_actual.set(request)
        try:
            return self.get_response(request)
        finally:
            _request_actual.reset(token)
