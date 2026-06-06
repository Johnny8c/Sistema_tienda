"""
Cliente SOAP del SRI con reintentos exponenciales.
Puerto de sriClient.js
"""
import base64
import re
import time
import requests
import xml.etree.ElementTree as ET

ENDPOINTS = {
    'pruebas': {
        'host':              'celcer.sri.gob.ec',
        'path_recepcion':    '/comprobantes-electronicos-ws/RecepcionComprobantesOffline',
        'path_autorizacion': '/comprobantes-electronicos-ws/AutorizacionComprobantesOffline',
    },
    'produccion': {
        'host':              'cel.sri.gob.ec',
        'path_recepcion':    '/comprobantes-electronicos-ws/RecepcionComprobantesOffline',
        'path_autorizacion': '/comprobantes-electronicos-ws/AutorizacionComprobantesOffline',
    },
}

RETRY_DELAYS = [2, 5, 10]   # segundos


def _soap_request(host, path, soap_body, timeout=30):
    url = f'https://{host}{path}'
    headers = {
        'Content-Type': 'text/xml; charset=utf-8',
        'SOAPAction':   '',
    }
    resp = requests.post(url, data=soap_body.encode('utf-8'), headers=headers, timeout=timeout)
    if resp.status_code >= 500:
        raise RuntimeError(f'SRI HTTP {resp.status_code}')
    return resp.text


def _soap_request_retry(host, path, soap_body, timeout=30, retry_delays=None):
    retry_delays = RETRY_DELAYS if retry_delays is None else list(retry_delays)
    last_err = None
    for attempt in range(len(retry_delays) + 1):
        try:
            data = _soap_request(host, path, soap_body, timeout)
            return {'data': data, 'contingencia': False, 'error': None}
        except Exception as e:
            last_err = e
            print(f'[SRI] Intento {attempt + 1}/{len(retry_delays) + 1} fallido: {e}')
            if attempt < len(retry_delays):
                time.sleep(retry_delays[attempt])
    print('[SRI] Todos los reintentos agotados — modo contingencia')
    return {'data': None, 'contingencia': True, 'error': last_err}


def _extract_tag(xml, tag):
    pattern = rf'<(?:[^:>]+:)?{tag}[^>]*>([\s\S]*?)<\/(?:[^:>]+:)?{tag}>'
    m = re.search(pattern, xml or '', re.IGNORECASE)
    return m.group(1).strip() if m else None


def _extract_all_tags(xml, tag):
    pattern = rf'<(?:[^:>]+:)?{tag}(?=[\s>])[^>]*>([\s\S]*?)<\/(?:[^:>]+:)?{tag}>'
    return [m.strip() for m in re.findall(pattern, xml or '', flags=re.IGNORECASE)]


def _local(tag):
    """Nombre local de un tag ElementTree, sin el namespace {...}."""
    return tag.rsplit('}', 1)[-1]


def _parse_mensajes(xml_str):
    """Extrae los mensajes de error del SRI con un parser XML real.

    La respuesta del SRI anida dos <mensaje>: el bloque de error (que tiene
    <identificador>) contiene un <mensaje> de texto y un <informacionAdicional>.
    Una regex no-greedy cortaba en el primer </mensaje> y perdía el
    informacionAdicional (que dice EXACTAMENTE qué elemento falla). Acá
    recorremos el árbol y tomamos solo los bloques que tienen <identificador>.
    """
    out = []
    try:
        root = ET.fromstring(xml_str or '')
    except ET.ParseError:
        return out
    for el in root.iter():
        if _local(el.tag) != 'mensaje':
            continue
        hijos = {_local(c.tag): (c.text or '').strip() for c in el}
        if 'identificador' not in hijos:
            continue  # es el <mensaje> de texto interno, no el bloque de error
        texto = hijos.get('mensaje', '')
        info  = hijos.get('informacionAdicional', '')
        out.append({
            'tipo':          hijos.get('tipo') or 'ERROR',
            'mensaje':       f'{texto}: {info}' if info else texto,
            'identificador': hijos.get('identificador', ''),
        })
    return out


def enviar_comprobante(xml_firmado: str, ambiente: str, timeout=30, retry_delays=None):
    """
    Envía el XML firmado al SRI (recepción).
    Retorna {estado, contingencia, mensajes, raw}.
    """
    ep = ENDPOINTS.get(ambiente, ENDPOINTS['produccion'])
    xml_b64 = base64.b64encode(xml_firmado.encode('utf-8')).decode('ascii')

    envelope = (
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ec="http://ec.gob.sri.ws.recepcion">'
            '<soap:Header/>'
            '<soap:Body>'
                '<ec:validarComprobante>'
                    f'<xml>{xml_b64}</xml>'
                '</ec:validarComprobante>'
            '</soap:Body>'
        '</soap:Envelope>'
    )

    res = _soap_request_retry(
        ep['host'],
        ep['path_recepcion'],
        envelope,
        timeout=timeout,
        retry_delays=retry_delays,
    )
    if res['contingencia']:
        return {
            'estado':       'CONTINGENCIA',
            'contingencia': True,
            'mensajes':     [{'tipo': 'ERROR', 'mensaje': str(res['error'] or 'SRI no disponible'), 'identificador': ''}],
            'raw':          None,
        }

    data = res['data']
    estado = _extract_tag(data, 'estado') or 'ERROR'
    mensajes = _parse_mensajes(data)
    return {'estado': estado, 'contingencia': False, 'mensajes': mensajes, 'raw': data}


def consultar_autorizacion(clave_acceso: str, ambiente: str, timeout=30, retry_delays=None):
    """
    Consulta autorización al SRI.
    Retorna {estado, contingencia, numeroAutorizacion, fechaAutorizacion, mensajes, raw}.
    """
    ep = ENDPOINTS.get(ambiente, ENDPOINTS['produccion'])

    envelope = (
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ec="http://ec.gob.sri.ws.autorizacion">'
            '<soap:Header/>'
            '<soap:Body>'
                '<ec:autorizacionComprobante>'
                    f'<claveAccesoComprobante>{clave_acceso}</claveAccesoComprobante>'
                '</ec:autorizacionComprobante>'
            '</soap:Body>'
        '</soap:Envelope>'
    )

    res = _soap_request_retry(
        ep['host'],
        ep['path_autorizacion'],
        envelope,
        timeout=timeout,
        retry_delays=retry_delays,
    )
    if res['contingencia']:
        return {
            'estado':              'CONTINGENCIA',
            'contingencia':        True,
            'numero_autorizacion': None,
            'fecha_autorizacion':  None,
            'mensajes':            [],
            'raw':                 None,
        }

    data = res['data']
    aut_xml = _extract_tag(data, 'autorizacion') or data
    estado              = _extract_tag(aut_xml, 'estado') or 'ERROR'
    numero_autorizacion = _extract_tag(aut_xml, 'numeroAutorizacion')
    fecha_autorizacion  = _extract_tag(aut_xml, 'fechaAutorizacion')

    mensajes = _parse_mensajes(aut_xml)

    return {
        'estado':              estado,
        'contingencia':        False,
        'numero_autorizacion': numero_autorizacion,
        'fecha_autorizacion':  fecha_autorizacion,
        'mensajes':            mensajes,
        'raw':                 data,
    }
