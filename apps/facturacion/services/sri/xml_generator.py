"""
Generador de XML factura v1.0.0 para el SRI.
Puerto directo de xmlGenerator.js — mantiene exactamente el mismo orden de tags.
"""
from decimal import Decimal
from datetime import datetime, date

from django.conf import settings


def _esc(s):
    if s is None:
        return ''
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _esc_attr(s):
    """Escapado para valores de atributo: ademas de &<>, las comillas."""
    return _esc(s).replace('"', '&quot;')


def _fmt2(n):
    return f'{Decimal(str(n or 0)):.2f}'


def _fmt6(n):
    return f'{Decimal(str(n or 0)):.6f}'


def _round_money(n):
    return (Decimal(str(n or 0))).quantize(Decimal('0.01'))


def _iva_codigo_porcentaje(pct):
    p = int(pct)
    return {0: '0', 5: '5', 12: '2', 14: '3', 15: '4'}.get(p, '4')


def _tipo_id_comprador(cedula):
    """Devuelve (tipo, id_normalizado, nombre_override_o_None)."""
    c = (cedula or '').strip()
    if not c:
        return ('07', '9999999999999', 'CONSUMIDOR FINAL')
    if len(c) == 13 and c.isdigit():
        return ('04', c, None)  # RUC
    if len(c) == 10 and c.isdigit():
        return ('05', c, None)  # Cédula
    return ('06', c, None)      # Pasaporte


def _campos_proveedor():
    """
    Campos del proveedor del sistema para infoAdicional.

    Resolucion NAC-DGERCGC26-00000027: el RUC del proveedor del software es
    obligatorio en todo comprobante. El resto son datos de contacto y se
    omiten si estan vacios en la configuracion.

    Devuelve una lista de (nombre, valor) en orden de prioridad: el campo
    obligatorio primero, para que sea el ultimo en descartarse si hubiera
    que recortar por el limite de 15 campoAdicional.
    """
    pares = [
        (settings.SRI_PROVEEDOR_CAMPO_RUC,      settings.SRI_PROVEEDOR_RUC),
        (settings.SRI_PROVEEDOR_CAMPO_NOMBRE,   settings.SRI_PROVEEDOR_NOMBRE),
        (settings.SRI_PROVEEDOR_CAMPO_EMAIL,    settings.SRI_PROVEEDOR_EMAIL),
        (settings.SRI_PROVEEDOR_CAMPO_TELEFONO, settings.SRI_PROVEEDOR_TELEFONO),
    ]
    return [(n.strip(), str(v).strip()) for n, v in pares if n and str(v).strip()]


def generar_xml(factura, items, configuracion, cliente, tipo_emision='1'):
    """
    factura       : FacturaSRI
    items         : iterable de ItemFacturaSRI
    configuracion : ConfiguracionSRI
    cliente       : Cliente
    tipo_emision  : '1' normal | '2' contingencia
    """
    ambiente = '2' if configuracion.ambiente == 'produccion' else '1'

    # Extraer estab/ptoEmi/secuencial del numero_factura "001-001-000000001"
    parts = (factura.numero_factura or '001-001-000000001').split('-')
    estab     = (parts[0] if len(parts) > 0 else '001').zfill(3)
    ptoEmi    = (parts[1] if len(parts) > 1 else '001').zfill(3)
    secuencial = (parts[2] if len(parts) > 2 else '000000001').zfill(9)

    # Fecha dd/mm/yyyy
    fe = factura.fecha_emision
    if isinstance(fe, str):
        fe = datetime.fromisoformat(fe[:10]).date()
    fechaStr = f'{fe.day:02d}/{fe.month:02d}/{fe.year}'

    # Comprador
    tipoId, idComp, nombreOverride = _tipo_id_comprador(getattr(cliente, 'cedula_ruc', ''))
    nombre_full = nombreOverride or (cliente.nombre or '').strip().upper() or 'CONSUMIDOR FINAL'
    nombreComp = _esc(nombre_full)

    # Totales
    subtotal0   = Decimal(str(factura.subtotal_0 or 0))
    subtotalIva = Decimal(str(factura.subtotal_iva or 0))
    ivaValor    = Decimal(str(factura.iva_valor or 0))
    total       = Decimal(str(factura.total or 0))
    totalSinImp = subtotal0 + subtotalIva
    ivaCode     = _iva_codigo_porcentaje(factura.iva_porcentaje)

    # totalConImpuestos
    parts_imp = ['<totalConImpuestos>']
    if subtotal0 > 0:
        parts_imp.append(
            f'<totalImpuesto><codigo>2</codigo><codigoPorcentaje>0</codigoPorcentaje>'
            f'<baseImponible>{_fmt2(subtotal0)}</baseImponible><valor>0.00</valor></totalImpuesto>'
        )
    if subtotalIva > 0:
        parts_imp.append(
            f'<totalImpuesto><codigo>2</codigo><codigoPorcentaje>{ivaCode}</codigoPorcentaje>'
            f'<baseImponible>{_fmt2(subtotalIva)}</baseImponible><valor>{_fmt2(ivaValor)}</valor></totalImpuesto>'
        )
    parts_imp.append('</totalConImpuestos>')
    totalConImp = ''.join(parts_imp)

    # Detalles
    iva_pct = int(factura.iva_porcentaje or 15)
    parts_det = ['<detalles>']
    for idx, item in enumerate(items):
        base       = Decimal(str(item.subtotal or 0))
        aplica_iva = bool(item.aplica_iva)
        item_iva_valor = _round_money(base * Decimal(iva_pct) / Decimal(100)) if aplica_iva else Decimal('0')
        item_iva_code  = ivaCode if aplica_iva else '0'
        item_tarifa    = _fmt2(iva_pct) if aplica_iva else '0.00'
        parts_det.append(
            '<detalle>'
            f'<codigoPrincipal>{str(idx + 1).zfill(3)}</codigoPrincipal>'
            f'<descripcion>{_esc(item.descripcion)}</descripcion>'
            f'<cantidad>{_fmt6(item.cantidad)}</cantidad>'
            f'<precioUnitario>{_fmt6(item.precio_unitario)}</precioUnitario>'
            f'<descuento>{_fmt2(item.descuento)}</descuento>'
            f'<precioTotalSinImpuesto>{_fmt2(base)}</precioTotalSinImpuesto>'
            '<impuestos><impuesto>'
            '<codigo>2</codigo>'
            f'<codigoPorcentaje>{item_iva_code}</codigoPorcentaje>'
            f'<tarifa>{item_tarifa}</tarifa>'
            f'<baseImponible>{_fmt2(base)}</baseImponible>'
            f'<valor>{_fmt2(item_iva_valor)}</valor>'
            '</impuesto></impuestos>'
            '</detalle>'
        )
    parts_det.append('</detalles>')
    detalles = ''.join(parts_det)

    # Info adicional — (nombre, valor) para poder controlar duplicados y el tope de 15
    campos = []
    if cliente.telefono:
        campos.append(('Telefono', str(cliente.telefono)))
    if cliente.email:
        campos.append(('Email', str(cliente.email)))
    campos.append(('NumeroFactura', str(factura.numero_factura or '')))

    # Datos del proveedor del sistema (Res. NAC-DGERCGC26-00000027).
    # Idempotente: si el nombre ya esta presente no se agrega de nuevo.
    ya_presentes = {n for n, _ in campos}
    for nombre, valor in _campos_proveedor():
        if nombre not in ya_presentes:
            campos.append((nombre, valor))
            ya_presentes.add(nombre)

    # Blindaje del tope del XSD (max 15). En la practica nunca se alcanza, pero
    # si pasara se recorta desde el final SIN sacrificar el campo obligatorio:
    # el RUC del proveedor se fuerza en la ultima ranura disponible.
    tope = settings.SRI_MAX_CAMPOS_ADICIONALES
    if len(campos) > tope:
        obligatorio = next(
            (c for c in campos if c[0] == settings.SRI_PROVEEDOR_CAMPO_RUC), None
        )
        campos = campos[:tope]
        if obligatorio and obligatorio not in campos:
            campos[-1] = obligatorio

    info_adicional = '<infoAdicional>{}</infoAdicional>'.format(''.join(
        f'<campoAdicional nombre="{_esc_attr(n)}">{_esc(v)}</campoAdicional>'
        for n, v in campos
    ))

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<factura id="comprobante" version="1.0.0">'
            '<infoTributaria>'
                f'<ambiente>{ambiente}</ambiente>'
                f'<tipoEmision>{tipo_emision}</tipoEmision>'
                f'<razonSocial>{_esc(configuracion.razon_social)}</razonSocial>'
                f'<nombreComercial>{_esc(configuracion.nombre_comercial or configuracion.razon_social)}</nombreComercial>'
                f'<ruc>{configuracion.ruc}</ruc>'
                f'<claveAcceso>{factura.clave_acceso}</claveAcceso>'
                '<codDoc>01</codDoc>'
                f'<estab>{estab}</estab>'
                f'<ptoEmi>{ptoEmi}</ptoEmi>'
                f'<secuencial>{secuencial}</secuencial>'
                f'<dirMatriz>{_esc(configuracion.direccion or "SIN DIRECCION")}</dirMatriz>'
            '</infoTributaria>'
            '<infoFactura>'
                f'<fechaEmision>{fechaStr}</fechaEmision>'
                f'<dirEstablecimiento>{_esc(configuracion.direccion or "SIN DIRECCION")}</dirEstablecimiento>'
                f'<obligadoContabilidad>{"SI" if configuracion.obligado_contabilidad else "NO"}</obligadoContabilidad>'
                f'<tipoIdentificacionComprador>{tipoId}</tipoIdentificacionComprador>'
                f'<razonSocialComprador>{nombreComp}</razonSocialComprador>'
                f'<identificacionComprador>{_esc(idComp)}</identificacionComprador>'
                f'<totalSinImpuestos>{_fmt2(totalSinImp)}</totalSinImpuestos>'
                '<totalDescuento>0.00</totalDescuento>'
                + totalConImp +
                '<propina>0.00</propina>'
                f'<importeTotal>{_fmt2(total)}</importeTotal>'
                '<moneda>DOLAR</moneda>'
                '<pagos><pago>'
                    '<formaPago>01</formaPago>'
                    f'<total>{_fmt2(total)}</total>'
                    '<plazo>0</plazo>'
                    '<unidadTiempo>dias</unidadTiempo>'
                '</pago></pagos>'
            '</infoFactura>'
            + detalles
            + info_adicional +
        '</factura>'
    )
    return xml
