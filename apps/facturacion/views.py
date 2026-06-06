"""
Vistas del módulo de facturación electrónica SRI.
"""
import base64
import logging
from datetime import datetime
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db import transaction
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)

SRI_INTERACTIVE_TIMEOUT = 4
SRI_INTERACTIVE_RETRY_DELAYS = [1]

from apps.usuarios.decorators import requiere_dueno, requiere_no_bodeguero
from apps.clientes.models import Cliente
from apps.ventas.models import Venta
from .models import ConfiguracionSRI, FacturaSRI, ItemFacturaSRI
from .services.sri.clave_acceso import generar_clave_acceso
from .services.sri.xml_generator import generar_xml
from .services.sri.xml_signer import firmar_xml
from .services.sri.sri_client import enviar_comprobante, consultar_autorizacion
from .services.sri.ride_pdf import generar_ride_pdf
from .services.sri.p12_crypto import (
    cifrar_dato, descifrar_dato,
    extraer_info_certificado, validar_p12,
)


# ── CONFIGURACIÓN ──────────────────────────────────────────────

@login_required
@requiere_dueno
def configuracion_sri(request):
    cfg = ConfiguracionSRI.get_singleton()

    if request.method == 'POST':
        if not cfg:
            cfg = ConfiguracionSRI()

        cfg.ruc                   = request.POST.get('ruc', '').strip()
        cfg.razon_social          = request.POST.get('razon_social', '').strip()
        cfg.nombre_comercial      = request.POST.get('nombre_comercial', '').strip()
        cfg.direccion             = request.POST.get('direccion', '').strip()
        cfg.telefono              = request.POST.get('telefono', '').strip()
        cfg.establecimiento       = (request.POST.get('establecimiento', '001') or '001').zfill(3)
        cfg.punto_emision         = (request.POST.get('punto_emision', '001') or '001').zfill(3)
        cfg.ambiente              = request.POST.get('ambiente', 'pruebas')
        cfg.iva_porcentaje        = int(request.POST.get('iva_porcentaje', '15') or 15)
        cfg.obligado_contabilidad = request.POST.get('obligado_contabilidad') == 'on'

        # Manejo del .p12
        p12_file = request.FILES.get('certificado_p12')
        clave    = request.POST.get('clave_certificado', '').strip()
        if p12_file and clave:
            p12_b64 = base64.b64encode(p12_file.read()).decode('ascii')
            try:
                validar_p12(p12_b64, clave)
            except ValueError as e:
                messages.error(request, str(e))
                return redirect('configuracion_sri')

            info = extraer_info_certificado(p12_b64, clave) or {}
            cfg.certificado_p12   = cifrar_dato(p12_b64)
            cfg.clave_certificado = cifrar_dato(clave)
            cfg.cert_titular      = info.get('titular', '')[:400]
            cfg.cert_vencimiento  = info.get('vencimiento')
        elif clave and cfg.pk and not p12_file:
            # Solo se actualiza la contraseña sin re-subir el .p12
            cfg.clave_certificado = cifrar_dato(clave)

        cfg.save()
        messages.success(request, 'Configuración SRI guardada.')
        return redirect('configuracion_sri')

    return render(request, 'facturacion/configuracion.html', {'cfg': cfg})


# ── FACTURAS ──────────────────────────────────────────────────

@login_required
@requiere_no_bodeguero
def lista_facturas(request):
    from datetime import datetime
    from apps.usuarios.models import Usuario

    estado      = request.GET.get('estado', '')
    q           = request.GET.get('q', '')
    fecha_desde = request.GET.get('desde', '')
    fecha_hasta = request.GET.get('hasta', '')
    vendedor_id = request.GET.get('vendedor', '')

    facturas = FacturaSRI.objects.select_related('cliente', 'creada_por').order_by('-creada_en')

    # Vendedor solo ve sus propias facturas
    if not request.user.es_dueno():
        facturas = facturas.filter(creada_por=request.user)

    if estado:
        facturas = facturas.filter(estado=estado)
    if q:
        facturas = facturas.filter(cliente__nombre__icontains=q)
    if fecha_desde:
        try:
            facturas = facturas.filter(fecha_emision__gte=datetime.strptime(fecha_desde, '%Y-%m-%d').date())
        except ValueError:
            pass
    if fecha_hasta:
        try:
            facturas = facturas.filter(fecha_emision__lte=datetime.strptime(fecha_hasta, '%Y-%m-%d').date())
        except ValueError:
            pass
    if vendedor_id and request.user.es_dueno():
        facturas = facturas.filter(creada_por_id=vendedor_id)

    vendedores = (Usuario.objects.filter(rol__in=[Usuario.ROL_VENDEDOR, Usuario.ROL_DUENO])
                  .order_by('first_name', 'username')) if request.user.es_dueno() else None

    # KPIs sobre el queryset filtrado
    from django.db.models import Sum, Count, Q
    from django.core.paginator import Paginator
    from django.utils import timezone
    hoy = timezone.now().date()
    base = FacturaSRI.objects.all()
    if not request.user.es_dueno():
        base = base.filter(creada_por=request.user)
    kpi_hoy = base.filter(fecha_emision=hoy).aggregate(
        cnt=Count('id'), total=Sum('total')
    )
    kpi_mes = base.filter(fecha_emision__year=hoy.year, fecha_emision__month=hoy.month).aggregate(
        cnt=Count('id'), total=Sum('total')
    )
    kpi_pendientes = base.filter(estado=FacturaSRI.EMITIDA).count()
    kpi_rechazadas = base.filter(estado=FacturaSRI.RECHAZADA).count()

    # Paginación: 50 facturas por página
    paginator = Paginator(facturas, 50)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'facturacion/lista.html', {
        'facturas':   page_obj,
        'page_obj':   page_obj,
        'estado_sel': estado,
        'q':          q,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'vendedor_id': vendedor_id,
        'vendedores':  vendedores,
        'estados':     FacturaSRI.ESTADOS,
        'kpi_hoy':       kpi_hoy,
        'kpi_mes':       kpi_mes,
        'kpi_pendientes': kpi_pendientes,
        'kpi_rechazadas': kpi_rechazadas,
    })


@login_required
@requiere_no_bodeguero
def detalle_factura(request, pk):
    factura = get_object_or_404(FacturaSRI, pk=pk)
    # El vendedor solo puede ver sus propias facturas
    if not request.user.es_dueno() and factura.creada_por_id != request.user.pk:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('No tienes permiso para ver esta factura.')
    return render(request, 'facturacion/detalle.html', {
        'factura': factura,
        'items': factura.items.all(),
    })


# ── EMISIÓN ───────────────────────────────────────────────────

def _round_money(v):
    return Decimal(str(v)).quantize(Decimal('0.01'))


def _crear_factura_desde_venta(venta, usuario, cfg):
    """Crea una FacturaSRI a partir de una Venta existente."""
    if not venta.cliente:
        raise ValueError('La venta debe tener un cliente asignado para emitir factura.')

    items_venta = list(venta.items.select_related('producto').all())
    iva_pct = cfg.iva_porcentaje
    iva_factor = Decimal(iva_pct) / Decimal(100)
    factor_con_iva = Decimal(1) + iva_factor

    # Los precios de venta YA INCLUYEN el IVA. Desglosamos hacia adentro:
    # base = precio / (1 + IVA), de modo que base + iva == precio (el total no cambia).
    subtotal_iva = Decimal('0')
    subtotal_0   = Decimal('0')
    iva_valor    = Decimal('0')
    items_factura = []
    for idx, iv in enumerate(items_venta):
        # Precio unitario sin IVA (4 decimales = max del campo y del XML SRI)
        precio_base_unit = (Decimal(str(iv.precio_unitario)) / factor_con_iva).quantize(Decimal('0.0001'))
        base = _round_money(precio_base_unit * Decimal(str(iv.cantidad)))
        # IVA por ítem (igual cálculo que xml_generator) — al sumar nos da el
        # iva_valor total. Así detalles y totales del XML coinciden exacto.
        iva_item = _round_money(base * iva_factor)
        items_factura.append({
            'orden':           idx + 1,
            'descripcion':     str(iv.producto)[:300],
            'cantidad':        Decimal(str(iv.cantidad)),
            'precio_unitario': precio_base_unit,
            'descuento':       Decimal('0'),
            'aplica_iva':      True,
            'subtotal':        base,
        })
        subtotal_iva += base
        iva_valor    += iva_item

    iva_valor = _round_money(iva_valor)  # ya está, pero garantizamos
    total     = _round_money(subtotal_0 + subtotal_iva + iva_valor)

    # Tomar y avanzar el siguiente secuencial atómicamente
    with transaction.atomic():
        cfg_locked = ConfiguracionSRI.objects.select_for_update().get(pk=cfg.pk)
        secuencial = cfg_locked.siguiente_secuencial
        cfg_locked.siguiente_secuencial += 1
        cfg_locked.save(update_fields=['siguiente_secuencial'])

        numero = f'{cfg_locked.establecimiento}-{cfg_locked.punto_emision}-{secuencial:09d}'
        factura = FacturaSRI.objects.create(
            venta=venta,
            cliente=venta.cliente,
            numero_factura=numero,
            fecha_emision=venta.fecha.date(),
            ambiente=cfg_locked.ambiente,
            estado=FacturaSRI.BORRADOR,
            subtotal_0=subtotal_0,
            subtotal_iva=subtotal_iva,
            iva_porcentaje=iva_pct,
            iva_valor=iva_valor,
            total=total,
            creada_por=usuario,
        )
        for d in items_factura:
            ItemFacturaSRI.objects.create(factura=factura, **d)
    return factura


@login_required
@requiere_no_bodeguero
def emitir_factura_venta(request, venta_pk):
    """Botón 'Emitir factura electrónica' desde una venta."""
    cfg = ConfiguracionSRI.get_singleton()
    if not cfg or not cfg.ruc:
        messages.error(request, 'Configura primero los datos del emisor en SRI → Configuración.')
        return redirect('configuracion_sri')
    if not cfg.cert_configurado:
        messages.error(request, 'Carga el certificado .p12 antes de emitir.')
        return redirect('configuracion_sri')

    venta = get_object_or_404(Venta, pk=venta_pk)

    # Si ya tiene factura, redirige al detalle
    if hasattr(venta, 'factura_sri') and venta.factura_sri:
        return redirect('detalle_factura', pk=venta.factura_sri.pk)

    try:
        factura = _crear_factura_desde_venta(venta, request.user, cfg)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect('lista_facturas')

    return _emitir_factura(request, factura, cfg)


@login_required
@requiere_no_bodeguero
def reemitir_factura(request, pk):
    factura = get_object_or_404(FacturaSRI, pk=pk)
    cfg = ConfiguracionSRI.get_singleton()
    if not cfg:
        messages.error(request, 'Configuración SRI no encontrada.')
        return redirect('lista_facturas')
    if factura.estado not in (FacturaSRI.BORRADOR, FacturaSRI.RECHAZADA, FacturaSRI.EMITIDA):
        messages.error(request, f'No se puede emitir una factura en estado {factura.estado}.')
        return redirect('detalle_factura', pk=factura.pk)
    return _emitir_factura(request, factura, cfg)


def _emitir_factura(request, factura, cfg):
    """Núcleo del flujo de emisión: clave → XML → firma → SRI → autorización."""
    cliente = factura.cliente
    items   = list(factura.items.all())

    # Descifrar .p12
    try:
        p12_b64     = descifrar_dato(cfg.certificado_p12)
        p12_password = descifrar_dato(cfg.clave_certificado)
    except Exception:
        logger.exception('Error al descifrar certificado SRI (factura %s)', factura.pk)
        messages.error(request, 'No se pudo leer el certificado. Verifica la contraseña en Configuración SRI.')
        return redirect('detalle_factura', pk=factura.pk)

    tipo_emision = '2' if cfg.contingencia_activa else '1'

    # Si la factura fue RECHAZADA antes, el SRI ya registró ese secuencial y no
    # lo acepta de nuevo (ERROR 45 SECUENCIAL REGISTRADO). Tomamos uno nuevo.
    if factura.estado == FacturaSRI.RECHAZADA:
        from django.db import transaction as _tx
        with _tx.atomic():
            cfg_locked = ConfiguracionSRI.objects.select_for_update().get(pk=cfg.pk)
            nuevo_seq = cfg_locked.siguiente_secuencial
            cfg_locked.siguiente_secuencial += 1
            cfg_locked.save(update_fields=['siguiente_secuencial'])
        factura.numero_factura = f'{cfg_locked.establecimiento}-{cfg_locked.punto_emision}-{nuevo_seq:09d}'
        # Limpiar datos del intento anterior para no arrastrar inconsistencias
        factura.clave_acceso = None
        factura.xml_firmado = ''
        factura.sri_respuesta = ''
        factura.sri_numero_autorizacion = ''
        factura.sri_fecha_autorizacion = None
        factura.estado = FacturaSRI.BORRADOR
        factura.save()
        # Refrescar cfg con valores nuevos para que el resto del flujo lea bien
        cfg = cfg_locked

    estab        = cfg.establecimiento
    pto          = cfg.punto_emision
    secuencial   = int(factura.numero_factura.split('-')[-1])
    serie        = f'{estab}{pto}'

    # 1. Clave de acceso
    clave = generar_clave_acceso(
        factura.fecha_emision, cfg.ruc, cfg.ambiente, secuencial,
        tipo_emision=tipo_emision, serie=serie,
    )
    factura.clave_acceso = clave

    # 2. Generar XML + 3. Firmar
    try:
        xml_sin = generar_xml(factura, items, cfg, cliente, tipo_emision=tipo_emision)
        xml_firmado = firmar_xml(xml_sin, p12_b64, p12_password)
    except Exception:
        logger.exception('Error al firmar XML SRI (factura %s)', factura.pk)
        messages.error(request, 'No se pudo firmar el comprobante. Revisa el certificado o intenta de nuevo.')
        return redirect('detalle_factura', pk=factura.pk)

    factura.xml_firmado = xml_firmado
    factura.estado = FacturaSRI.EMITIDA
    factura.save(update_fields=['clave_acceso', 'xml_firmado', 'estado'])

    # 4. Enviar al SRI (recepción)
    rec = enviar_comprobante(
        xml_firmado,
        cfg.ambiente,
        timeout=SRI_INTERACTIVE_TIMEOUT,
        retry_delays=SRI_INTERACTIVE_RETRY_DELAYS,
    )
    factura.sri_intentos_recepcion += 1
    if rec['contingencia']:
        factura.es_contingencia = True
        factura.sri_respuesta = f'CONTINGENCIA: {rec["mensajes"][0]["mensaje"] if rec["mensajes"] else "SRI no disponible"}'
        factura.save(update_fields=['es_contingencia', 'sri_respuesta', 'sri_intentos_recepcion'])
        messages.warning(
            request,
            f'⚠️ El SRI está caído en este momento y no respondió. '
            f'La factura {factura.numero_factura} quedó GUARDADA en modo contingencia '
            f'y se autorizará automáticamente cuando el SRI vuelva. '
            f'No la reemitas: ya quedó registrada.'
        )
        return redirect('detalle_factura', pk=factura.pk)

    if rec['estado'] == 'DEVUELTA':
        err = ' | '.join([f'[{m["tipo"]}] {m["mensaje"]}' for m in rec['mensajes']]) or 'Devuelta por el SRI.'
        factura.estado = FacturaSRI.RECHAZADA
        factura.sri_respuesta = err
        factura.save(update_fields=['estado', 'sri_respuesta', 'sri_intentos_recepcion'])
        # Si el error es por fecha, dar contexto adicional con la fecha realmente enviada
        err_lower = err.lower()
        if 'fecha' in err_lower:
            messages.error(
                request,
                f'SRI devolvió la factura: {err}\n\n'
                f'🕒 Fecha enviada: {factura.fecha_emision.strftime("%d/%m/%Y")}. '
                f'Verifica que el reloj del servidor sea la fecha real actual (Configuración → Hora y fecha en Windows).'
            )
        else:
            messages.error(request, f'SRI devolvió la factura: {err}')
        return redirect('detalle_factura', pk=factura.pk)

    factura.save(update_fields=['sri_intentos_recepcion'])

    # 5. Consultar autorización
    aut = consultar_autorizacion(
        clave,
        cfg.ambiente,
        timeout=SRI_INTERACTIVE_TIMEOUT,
        retry_delays=SRI_INTERACTIVE_RETRY_DELAYS,
    )
    if aut['contingencia']:
        factura.sri_respuesta = 'Recibido por SRI — autorización pendiente'
        factura.save(update_fields=['sri_respuesta'])
        messages.warning(
            request,
            f'⚠️ El SRI recibió la factura {factura.numero_factura} pero está caído '
            f'para confirmar la autorización. Quedó PENDIENTE y se autorizará '
            f'automáticamente cuando el SRI vuelva. No la reemitas.'
        )
        return redirect('detalle_factura', pk=factura.pk)

    if aut['estado'] == 'AUTORIZADO':
        factura.estado = FacturaSRI.AUTORIZADA
        factura.sri_numero_autorizacion = aut['numero_autorizacion'] or ''
        if aut['fecha_autorizacion']:
            try:
                fa = parse_datetime(aut['fecha_autorizacion']) or datetime.fromisoformat(aut['fecha_autorizacion'])
                factura.sri_fecha_autorizacion = fa
            except (ValueError, TypeError):
                logger.warning('Fecha de autorización SRI no parseable: %r', aut['fecha_autorizacion'])
        factura.sri_respuesta = f'AUTORIZADO | Nº {aut["numero_autorizacion"]} | {aut["fecha_autorizacion"]}'
        factura.es_contingencia = False
        factura.save()
        messages.success(request, 'Factura autorizada por el SRI.')
        _enviar_factura_si_corresponde(request, factura)
        return redirect('detalle_factura', pk=factura.pk)

    err = ' | '.join([f'[{m["tipo"]}] {m["mensaje"]}' for m in aut['mensajes']]) or 'Rechazado por el SRI.'
    factura.estado = FacturaSRI.RECHAZADA
    factura.sri_respuesta = err
    factura.save(update_fields=['estado', 'sri_respuesta'])
    messages.error(request, f'SRI rechazó la factura en autorización: {err}')
    return redirect('detalle_factura', pk=factura.pk)


# ── DESCARGAS ─────────────────────────────────────────────────

@login_required
@requiere_no_bodeguero
def descargar_xml(request, pk):
    factura = get_object_or_404(FacturaSRI, pk=pk)
    if not factura.xml_firmado:
        messages.error(request, 'Esta factura aún no tiene XML firmado.')
        return redirect('detalle_factura', pk=pk)
    resp = HttpResponse(factura.xml_firmado, content_type='application/xml')
    nombre = factura.clave_acceso or f'factura_{factura.pk}'
    resp['Content-Disposition'] = f'attachment; filename="{nombre}.xml"'
    return resp


@login_required
@requiere_no_bodeguero
def descargar_ride(request, pk):
    factura = get_object_or_404(FacturaSRI, pk=pk)
    cfg = ConfiguracionSRI.get_singleton()
    if not cfg:
        messages.error(request, 'Configuración SRI no encontrada.')
        return redirect('detalle_factura', pk=pk)
    pdf_bytes = generar_ride_pdf(factura, factura.items.all(), cfg, factura.cliente)
    resp = HttpResponse(pdf_bytes, content_type='application/pdf')
    nombre = factura.clave_acceso or f'factura_{factura.pk}'
    resp['Content-Disposition'] = f'inline; filename="RIDE_{nombre}.pdf"'
    return resp


# ── VERIFICAR / REINTENTAR ────────────────────────────────────

@login_required
@requiere_no_bodeguero
def verificar_autorizacion(request, pk):
    """Reconsulta al SRI por una factura emitida pero no autorizada."""
    factura = get_object_or_404(FacturaSRI, pk=pk)
    cfg = ConfiguracionSRI.get_singleton()
    if factura.estado == FacturaSRI.AUTORIZADA:
        messages.info(request, 'La factura ya está autorizada.')
        return redirect('detalle_factura', pk=pk)

    aut = consultar_autorizacion(factura.clave_acceso, cfg.ambiente)
    if aut['contingencia']:
        messages.warning(request, 'SRI no disponible para verificar.')
        return redirect('detalle_factura', pk=pk)

    if aut['estado'] == 'AUTORIZADO':
        factura.estado = FacturaSRI.AUTORIZADA
        factura.sri_numero_autorizacion = aut['numero_autorizacion'] or ''
        if aut['fecha_autorizacion']:
            try:
                fa = parse_datetime(aut['fecha_autorizacion']) or datetime.fromisoformat(aut['fecha_autorizacion'])
                factura.sri_fecha_autorizacion = fa
            except (ValueError, TypeError):
                logger.warning('Fecha de autorización SRI no parseable: %r', aut['fecha_autorizacion'])
        factura.sri_respuesta = f'AUTORIZADO | Nº {aut["numero_autorizacion"]}'
        factura.save()
        messages.success(request, 'Factura autorizada.')
        _enviar_factura_si_corresponde(request, factura)
    else:
        messages.error(request, f'Estado actual SRI: {aut["estado"]}')
    return redirect('detalle_factura', pk=pk)


# ── EMAIL — auto-envío al autorizar + reenvío manual ──────────


def _enviar_factura_si_corresponde(request, factura):
    """
    Hook llamado justo después de que la factura quedó AUTORIZADA.
    Intenta enviar el email al cliente. Si no hay email del cliente o
    EMAIL no está configurado, hace nada silenciosamente (la factura
    queda autorizada igual; el dueño puede reenviar manualmente).
    Errores se logean pero NO interrumpen la respuesta al cajero.
    """
    from .email import enviar_factura_por_email

    if not (factura.cliente.email or '').strip():
        return  # sin email del cliente — no notificamos al cajero, es normal

    try:
        ok, msg_resultado = enviar_factura_por_email(factura, request=request)
    except Exception:
        logger.exception('Error inesperado enviando email factura %s', factura.pk)
        return

    if ok:
        messages.info(request, f'📧 {msg_resultado}')
    else:
        # No mostramos error grande al cajero — solo info, la factura ya
        # está autorizada, el envío es secundario.
        messages.warning(request, f'No se pudo enviar email de la factura: {msg_resultado}')


@login_required
@requiere_no_bodeguero
def reenviar_email_factura(request, pk):
    """Reenvía manualmente el email de la factura al cliente."""
    from .email import enviar_factura_por_email

    factura = get_object_or_404(FacturaSRI, pk=pk)

    if factura.estado != FacturaSRI.AUTORIZADA:
        messages.error(request, 'Solo se puede enviar email de facturas autorizadas.')
        return redirect('detalle_factura', pk=pk)

    try:
        ok, msg_resultado = enviar_factura_por_email(factura, request=request)
    except Exception as exc:
        logger.exception('Error inesperado reenviando email factura %s', factura.pk)
        messages.error(request, f'Error de envío: {type(exc).__name__}: {exc}')
        return redirect('detalle_factura', pk=pk)

    if ok:
        messages.success(request, f'📧 {msg_resultado}')
    else:
        messages.error(request, msg_resultado)
    return redirect('detalle_factura', pk=pk)
