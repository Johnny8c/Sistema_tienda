"""
Context processors que exponen configuración a todos los templates.
"""
from .models import ConfiguracionGeneral


def config_general(request):
    try:
        cfg = ConfiguracionGeneral.objects.first()
    except Exception:
        cfg = None
    return {'config_general': cfg}


def aviso_pago_proveedor(request):
    """
    Aviso del pago al proveedor del sistema (visible solo al dueño).
    Configurado por variables de entorno (settings.DEV_PAGO_*).
    """
    from datetime import datetime, date
    from django.conf import settings

    if not request.user.is_authenticated:
        return {}
    # Solo dueño / superuser ven este aviso
    if not (getattr(request.user, 'es_dueno', lambda: False)() or request.user.is_superuser):
        return {}

    fecha_str = (settings.DEV_PAGO_FECHA or '').strip()
    if not fecha_str:
        return {}

    try:
        fecha_pago = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except ValueError:
        return {}

    hoy = date.today()
    dias = (fecha_pago - hoy).days

    # Aviso siempre visible (incluso si falta mucho), pero con nivel discreto
    if dias < 0:
        nivel = 'critico'      # Vencido
    elif dias <= 3:
        nivel = 'alto'         # 0-3 días
    elif dias <= 10:
        nivel = 'medio'        # 4-10 días
    elif dias <= 30:
        nivel = 'bajo'         # 11-30 días
    else:
        nivel = 'info'         # >30 días (informativo, discreto)

    return {
        'aviso_pago': {
            'fecha': fecha_pago,
            'dias': dias,
            'dias_abs': abs(dias),
            'nivel': nivel,
            'monto': settings.DEV_PAGO_MONTO,
            'moneda': settings.DEV_PAGO_MONEDA,
            'concepto': settings.DEV_PAGO_CONCEPTO,
            'contacto_nombre': settings.DEV_PAGO_CONTACTO_NOMBRE,
            'contacto_telefono': settings.DEV_PAGO_CONTACTO_TELEFONO,
            'contacto_email': settings.DEV_PAGO_CONTACTO_EMAIL,
            'instrucciones': settings.DEV_PAGO_INSTRUCCIONES,
        }
    }
