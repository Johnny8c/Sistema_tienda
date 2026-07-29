"""
Vista de fallo de CSRF.

Django responde el fallo de CSRF con una página HTML de error 403. Para las
pantallas normales eso está bien, pero un fetch() del POS intenta parsear esa
página como JSON y el cajero termina viendo "Unexpected token '<'". Acá
detectamos las peticiones AJAX y les respondemos JSON con un mensaje claro.
"""
from django.http import JsonResponse
from django.views.csrf import csrf_failure as django_csrf_failure


def _es_ajax(request) -> bool:
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('Accept', '')
    )


def csrf_failure(request, reason='', template_name='403_csrf.html'):
    if _es_ajax(request):
        return JsonResponse({
            'ok': False,
            'error': 'La sesión caducó por seguridad. Recarga la página (F5) e intenta de nuevo.',
            'sesion_expirada': True,
        }, status=403)
    return django_csrf_failure(request, reason=reason, template_name=template_name)
