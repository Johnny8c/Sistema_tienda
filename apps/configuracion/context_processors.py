"""
Context processors que exponen configuración a todos los templates.
"""
import logging
from django.core.cache import cache
from .models import ConfiguracionGeneral
from .pwa import apple_touch_icon_url

logger = logging.getLogger(__name__)

_LOGO_CHECK_CACHE_KEY = 'cfg_logo_ok'
_LOGO_CHECK_TTL = 60 * 5  # 5 min


def config_general(request):
    try:
        cfg = ConfiguracionGeneral.objects.first()
    except Exception:
        cfg = None

    # Auto-limpieza de logo huérfano. Solo verificamos contra el storage una vez
    # cada 5 minutos para no añadir latencia a cada request (Cloudinary.exists()
    # es una llamada HTTP). El resultado positivo se cachea; si es negativo
    # limpiamos el campo y refrescamos el cfg en memoria.
    if cfg and cfg.logo:
        if cache.get(_LOGO_CHECK_CACHE_KEY) != cfg.logo.name:
            try:
                if cfg.logo.storage.exists(cfg.logo.name):
                    cache.set(_LOGO_CHECK_CACHE_KEY, cfg.logo.name, _LOGO_CHECK_TTL)
                else:
                    logger.warning('Logo huérfano (%s). Limpiando referencia.', cfg.logo.name)
                    cfg.logo = None
                    cfg.save(update_fields=['logo'])
                    cache.delete(_LOGO_CHECK_CACHE_KEY)
            except Exception:
                logger.exception('No se pudo verificar la existencia del logo')

    return {
        'config_general': cfg,
        'pwa_apple_icon': apple_touch_icon_url(request, cfg),
    }


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
