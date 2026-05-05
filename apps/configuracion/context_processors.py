"""
Context processor que expone la configuración general a todos los templates.
"""
from .models import ConfiguracionGeneral


def config_general(request):
    try:
        cfg = ConfiguracionGeneral.objects.first()
    except Exception:
        cfg = None
    return {'config_general': cfg}
