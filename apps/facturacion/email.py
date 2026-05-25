"""
Envío de facturas electrónicas por email.

Cuando una FacturaSRI queda AUTORIZADA por el SRI, esta funcion arma el
mensaje y lo envia por SMTP (configurado en settings.EMAIL_*). Adjunta:
  - RIDE PDF (representacion legible que el cliente puede imprimir)
  - XML firmado y autorizado (comprobante legal segun normativa SRI)

Diseñado para no romper el flujo de venta: si falla el envio, se logea
el error y se retorna False. La factura queda autorizada igual; el dueno
puede reenviar manualmente desde el detalle.

Provider-agnostic: funciona con Resend SMTP, Gmail SMTP, o cualquier
otro proveedor SMTP que se configure en EMAIL_HOST/EMAIL_HOST_PASSWORD.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def _email_configurado() -> bool:
    """True si hay credenciales SMTP completas. Si False, el backend usa
    'console' (los emails se imprimen, no se envian) y deberiamos abortar
    silenciosamente."""
    return bool(getattr(settings, 'EMAIL_HOST_PASSWORD', '')) \
        and bool(getattr(settings, 'DEFAULT_FROM_EMAIL', ''))


def enviar_factura_por_email(factura, request=None) -> tuple[bool, str]:
    """
    Envia la factura AUTORIZADA al email del cliente con el RIDE PDF y el
    XML firmado adjuntos.

    Returns:
        (ok: bool, mensaje: str) — `ok=True` si se envio; `mensaje` es
        descriptivo (para mostrar en messages.* o logs).
    """
    from .models import FacturaSRI, ConfiguracionSRI
    from .services.sri.ride_pdf import generar_ride_pdf
    from apps.configuracion.models import ConfiguracionGeneral

    # 1. Validaciones tempranas
    if factura.estado != FacturaSRI.AUTORIZADA:
        return False, 'La factura aún no está autorizada por el SRI.'

    email_cliente = (factura.cliente.email or '').strip()
    if not email_cliente:
        return False, 'El cliente no tiene email registrado.'

    if not _email_configurado():
        logger.warning(
            'EMAIL no configurado (falta EMAIL_HOST_PASSWORD o '
            'DEFAULT_FROM_EMAIL). Factura %s no se envio.',
            factura.pk,
        )
        return False, 'El envío de email no está configurado en el sistema.'

    # 2. Generar adjuntos
    try:
        cfg_sri = ConfiguracionSRI.get_singleton()
        cfg_general = ConfiguracionGeneral.get_singleton()
        pdf_bytes = generar_ride_pdf(factura, factura.items.all(), cfg_sri, factura.cliente)
    except Exception:
        logger.exception('No se pudo generar RIDE PDF para factura %s', factura.pk)
        return False, 'Error generando el PDF de la factura.'

    nombre_archivo = factura.clave_acceso or f'factura_{factura.pk}'

    # 3. Render del cuerpo HTML/TXT
    ctx = {
        'factura': factura,
        'cliente': factura.cliente,
        'negocio': cfg_general,
    }
    try:
        body_html = render_to_string('facturacion/email_factura.html', ctx)
        body_txt  = render_to_string('facturacion/email_factura.txt',  ctx)
    except Exception:
        logger.exception('No se pudo renderizar template de email factura %s', factura.pk)
        return False, 'Error armando el cuerpo del email.'

    subject = (
        f'Factura electrónica Nº {factura.numero_factura} — '
        f'{cfg_general.nombre_negocio if cfg_general else "Tienda"}'
    )

    # 4. Construir el mensaje
    reply_to = []
    if cfg_general and cfg_general.email:
        reply_to.append(cfg_general.email)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=body_txt,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email_cliente],
        reply_to=reply_to or None,
    )
    msg.attach_alternative(body_html, 'text/html')
    msg.attach(f'RIDE_{nombre_archivo}.pdf', pdf_bytes, 'application/pdf')
    if factura.xml_firmado:
        msg.attach(f'{nombre_archivo}.xml', factura.xml_firmado, 'application/xml')

    # 5. Enviar (sin fail_silently para detectar errores SMTP)
    try:
        msg.send(fail_silently=False)
    except Exception as exc:
        logger.exception('Falla SMTP enviando factura %s a %s', factura.pk, email_cliente)
        return False, f'Error de envío: {type(exc).__name__}: {exc}'

    logger.info('Factura %s enviada por email a %s', factura.pk, email_cliente)
    return True, f'Email enviado a {email_cliente}.'
