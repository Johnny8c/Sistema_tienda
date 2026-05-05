"""
Vistas del módulo de facturación electrónica SRI.
"""
import base64
from datetime import datetime
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db import transaction
from django.utils.dateparse import parse_datetime

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
    estado = request.GET.get('estado', '')
    q      = request.GET.get('q', '')
    facturas = FacturaSRI.objects.select_related('cliente').order_by('-creada_en')
    if estado:
        facturas = facturas.filter(estado=estado)
    if q:
        facturas = facturas.filter(cliente__nombre__icontains=q)
    return render(request, 'facturacion/lista.html', {
        'facturas': facturas,
        'estado_sel': estado,
        'q': q,
        'estados': FacturaSRI.ESTADOS,
    })


@login_required
@requiere_no_bodeguero
def detalle_factura(request, pk):
    factura = get_object_or_404(FacturaSRI, pk=pk)
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

    # Suponemos que todos aplican IVA por defecto (configurable después)
    subtotal_iva = Decimal('0')
    subtotal_0   = Decimal('0')
    items_factura = []
    for idx, iv in enumerate(items_venta):
        base = _round_money(Decimal(str(iv.precio_unitario)) * Decimal(str(iv.cantidad)))
        items_factura.append({
            'orden':           idx + 1,
            'descripcion':     str(iv.producto)[:300],
            'cantidad':        Decimal(str(iv.cantidad)),
            'precio_unitario': Decimal(str(iv.precio_unitario)),
            'descuento':       Decimal('0'),
            'aplica_iva':      True,
            'subtotal':        base,
        })
        subtotal_iva += base

    iva_valor = _round_money(subtotal_iva * Decimal(iva_pct) / Decimal(100))
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
    except Exception as e:
        messages.error(request, f'Error al descifrar certificado: {e}')
        return redirect('detalle_factura', pk=factura.pk)

    tipo_emision = '2' if cfg.contingencia_activa else '1'
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
    except Exception as e:
        messages.error(request, f'Error al firmar el comprobante: {e}')
        return redirect('detalle_factura', pk=factura.pk)

    factura.xml_firmado = xml_firmado
    factura.estado = FacturaSRI.EMITIDA
    factura.save(update_fields=['clave_acceso', 'xml_firmado', 'estado'])

    # 4. Enviar al SRI (recepción)
    rec = enviar_comprobante(xml_firmado, cfg.ambiente)
    factura.sri_intentos_recepcion += 1
    if rec['contingencia']:
        factura.es_contingencia = True
        factura.sri_respuesta = f'CONTINGENCIA: {rec["mensajes"][0]["mensaje"] if rec["mensajes"] else "SRI no disponible"}'
        factura.save(update_fields=['es_contingencia', 'sri_respuesta', 'sri_intentos_recepcion'])
        messages.warning(request, 'SRI no disponible. Factura en modo contingencia — se reintentará.')
        return redirect('detalle_factura', pk=factura.pk)

    if rec['estado'] == 'DEVUELTA':
        err = ' | '.join([f'[{m["tipo"]}] {m["mensaje"]}' for m in rec['mensajes']]) or 'Devuelta por el SRI.'
        factura.estado = FacturaSRI.RECHAZADA
        factura.sri_respuesta = err
        factura.save(update_fields=['estado', 'sri_respuesta', 'sri_intentos_recepcion'])
        messages.error(request, f'SRI devolvió la factura: {err}')
        return redirect('detalle_factura', pk=factura.pk)

    factura.save(update_fields=['sri_intentos_recepcion'])

    # 5. Consultar autorización
    aut = consultar_autorizacion(clave, cfg.ambiente)
    if aut['contingencia']:
        factura.sri_respuesta = 'Recibido por SRI — autorización pendiente'
        factura.save(update_fields=['sri_respuesta'])
        messages.info(request, 'Comprobante enviado. La autorización está pendiente.')
        return redirect('detalle_factura', pk=factura.pk)

    if aut['estado'] == 'AUTORIZADO':
        factura.estado = FacturaSRI.AUTORIZADA
        factura.sri_numero_autorizacion = aut['numero_autorizacion'] or ''
        if aut['fecha_autorizacion']:
            try:
                fa = parse_datetime(aut['fecha_autorizacion']) or datetime.fromisoformat(aut['fecha_autorizacion'])
                factura.sri_fecha_autorizacion = fa
            except Exception:
                pass
        factura.sri_respuesta = f'AUTORIZADO | Nº {aut["numero_autorizacion"]} | {aut["fecha_autorizacion"]}'
        factura.es_contingencia = False
        factura.save()
        messages.success(request, 'Factura autorizada por el SRI.')
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
            except Exception:
                pass
        factura.sri_respuesta = f'AUTORIZADO | Nº {aut["numero_autorizacion"]}'
        factura.save()
        messages.success(request, 'Factura autorizada.')
    else:
        messages.error(request, f'Estado actual SRI: {aut["estado"]}')
    return redirect('detalle_factura', pk=pk)
