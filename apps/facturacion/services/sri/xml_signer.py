"""
Firma XAdES-BES con RSA-SHA1 para SRI.
Puerto de xmlSigner.js manteniendo el mismo flujo:
  1. Construye XML completo con placeholders __SP_DIGEST__, __KI_DIGEST__,
     __DOC_DIGEST__, __SIG_VALUE__.
  2. Calcula digest SHA-1 sobre la canonicalización C14N (Inclusive) de:
     - factura sin Signature (enveloped-signature) → docDigest
     - KeyInfo                                      → keyInfoDigest
     - SignedProperties                             → spDigest
  3. Reemplaza los digests, canonicaliza SignedInfo y firma con RSA-SHA1.
"""
import base64
import hashlib
import random
import re
from datetime import datetime, timedelta, timezone
from lxml import etree

from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives import hashes


def _esc(s):
    if s is None:
        return ''
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _sha1_b64(data: bytes) -> str:
    return base64.b64encode(hashlib.sha1(data).digest()).decode('ascii')


def _canon_c14n(node) -> bytes:
    """C14N inclusivo (la versión que SRI/Apache Santuario validan)."""
    return etree.tostring(node, method='c14n', exclusive=False, with_comments=False)


# OIDs reconocidos por Java X500Principal
_JAVA_KNOWN_OIDS = {
    '2.5.4.3':  'CN',
    '2.5.4.4':  'SN',
    '2.5.4.5':  'SERIALNUMBER',
    '2.5.4.6':  'C',
    '2.5.4.7':  'L',
    '2.5.4.8':  'ST',
    '2.5.4.9':  'STREET',
    '2.5.4.10': 'O',
    '2.5.4.11': 'OU',
    '2.5.4.12': 'T',
    '2.5.4.42': 'GN',
    '2.5.4.43': 'INITIALS',
    '2.5.4.46': 'DNQUALIFIER',
    '0.9.2342.19200300.100.1.1':  'UID',
    '0.9.2342.19200300.100.1.25': 'DC',
    '1.2.840.113549.1.9.1':       'EMAILADDRESS',
}


def _esc_dn_value(v: str) -> str:
    s = '' if v is None else str(v)
    s = s.replace('\\', '\\\\') \
         .replace(',', '\\,') \
         .replace('+', '\\+') \
         .replace('"', '\\"') \
         .replace('<', '\\<') \
         .replace('>', '\\>') \
         .replace(';', '\\;')
    if s.startswith('#'):
        s = '\\' + s
    if s.startswith(' '):
        s = '\\' + s
    if s.endswith(' '):
        s = s[:-1] + '\\ '
    return s


def _value_as_hex(val: str) -> str:
    """RFC 4514 hex DER form: #0c <length> <UTF-8 bytes>"""
    buf = str(val).encode('utf-8')
    n = len(buf)
    if n < 128:
        len_hex = f'{n:02x}'
    else:
        lh = f'{n:x}'
        if len(lh) % 2:
            lh = '0' + lh
        num_bytes = len(lh) // 2
        len_hex = f'{(0x80 | num_bytes):02x}{lh}'
    return f'#0c{len_hex}{buf.hex()}'


def _format_issuer_name(cert):
    """Formato RFC 4514, orden inverso (leaf-to-root)."""
    rdns = list(cert.issuer.rdns)
    parts = []
    for rdn in reversed(rdns):
        for attr in rdn:
            oid = attr.oid.dotted_string
            short = _JAVA_KNOWN_OIDS.get(oid)
            if short:
                parts.append(f'{short}={_esc_dn_value(attr.value)}')
            else:
                parts.append(f'{oid}={_value_as_hex(attr.value)}')
    return ','.join(parts)


def _find_by_id(root, id_value):
    """Busca elemento con atributo Id o id == id_value (case-insensitive)."""
    for el in root.iter():
        if el.get('Id') == id_value or el.get('id') == id_value:
            return el
    return None


def firmar_xml(xml_str: str, p12_base64: str, password: str) -> str:
    """Firma XAdES-BES y devuelve el XML firmado."""
    p12_bytes = base64.b64decode(p12_base64)
    private_key, cert, addl = pkcs12.load_key_and_certificates(p12_bytes, password.encode('utf-8'))

    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise ValueError('La clave privada del certificado no es RSA.')

    # DER del cert (para X509Certificate y CertDigest)
    cert_der = cert.public_bytes(encoding=__import__('cryptography').hazmat.primitives.serialization.Encoding.DER)
    cert_b64 = base64.b64encode(cert_der).decode('ascii')
    cert_digest = _sha1_b64(cert_der)
    serial_decimal = str(cert.serial_number)
    issuer_name = _format_issuer_name(cert)

    # Modulus + exponent en base64
    pub_numbers = private_key.public_key().public_numbers()
    mod_hex = format(pub_numbers.n, 'x')
    if len(mod_hex) % 2:
        mod_hex = '0' + mod_hex
    modulus_b64 = base64.b64encode(bytes.fromhex(mod_hex)).decode('ascii')
    exp_hex = format(pub_numbers.e, 'x')
    if len(exp_hex) % 2:
        exp_hex = '0' + exp_hex
    exponent_b64 = base64.b64encode(bytes.fromhex(exp_hex)).decode('ascii')

    # SigningTime en hora Ecuador (UTC-5)
    ec_now = datetime.now(timezone.utc) - timedelta(hours=5)
    signing_time = ec_now.strftime('%Y-%m-%dT%H:%M:%S-05:00')

    rnd = lambda: random.randint(100000, 999999)
    sigId      = f'Signature{rnd()}'
    sigInfoId  = f'Signature-SignedInfo{rnd()}'
    sigValueId = f'SignatureValue{rnd()}'
    certInfoId = f'Certificate{rnd()}'
    objectId   = f'Signature-Object{rnd()}'
    spId       = f'{sigId}-SignedProperties'
    refDocId   = f'Reference-ID-{rnd()}'

    signature_block = (
        f'<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#" xmlns:etsi="http://uri.etsi.org/01903/v1.3.2#" Id="{sigId}">'
            f'<ds:SignedInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#" xmlns:etsi="http://uri.etsi.org/01903/v1.3.2#" Id="{sigInfoId}">'
                '<ds:CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"></ds:CanonicalizationMethod>'
                '<ds:SignatureMethod Algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1"></ds:SignatureMethod>'
                f'<ds:Reference Id="SignedPropertiesID" Type="http://uri.etsi.org/01903#SignedProperties" URI="#{spId}">'
                    '<ds:DigestMethod Algorithm="http://www.w3.org/2000/09/xmldsig#sha1"></ds:DigestMethod>'
                    '<ds:DigestValue>__SP_DIGEST__</ds:DigestValue>'
                '</ds:Reference>'
                f'<ds:Reference URI="#{certInfoId}">'
                    '<ds:DigestMethod Algorithm="http://www.w3.org/2000/09/xmldsig#sha1"></ds:DigestMethod>'
                    '<ds:DigestValue>__KI_DIGEST__</ds:DigestValue>'
                '</ds:Reference>'
                f'<ds:Reference Id="{refDocId}" URI="#comprobante">'
                    '<ds:Transforms>'
                        '<ds:Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"></ds:Transform>'
                    '</ds:Transforms>'
                    '<ds:DigestMethod Algorithm="http://www.w3.org/2000/09/xmldsig#sha1"></ds:DigestMethod>'
                    '<ds:DigestValue>__DOC_DIGEST__</ds:DigestValue>'
                '</ds:Reference>'
            '</ds:SignedInfo>'
            f'<ds:SignatureValue Id="{sigValueId}">__SIG_VALUE__</ds:SignatureValue>'
            f'<ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#" xmlns:etsi="http://uri.etsi.org/01903/v1.3.2#" Id="{certInfoId}">'
                '<ds:X509Data>'
                    f'<ds:X509Certificate>{cert_b64}</ds:X509Certificate>'
                '</ds:X509Data>'
                '<ds:KeyValue>'
                    '<ds:RSAKeyValue>'
                        f'<ds:Modulus>{modulus_b64}</ds:Modulus>'
                        f'<ds:Exponent>{exponent_b64}</ds:Exponent>'
                    '</ds:RSAKeyValue>'
                '</ds:KeyValue>'
            '</ds:KeyInfo>'
            f'<ds:Object Id="{objectId}">'
                f'<etsi:QualifyingProperties Target="#{sigId}">'
                    f'<etsi:SignedProperties xmlns:ds="http://www.w3.org/2000/09/xmldsig#" xmlns:etsi="http://uri.etsi.org/01903/v1.3.2#" Id="{spId}">'
                        '<etsi:SignedSignatureProperties>'
                            f'<etsi:SigningTime>{signing_time}</etsi:SigningTime>'
                            '<etsi:SigningCertificate>'
                                '<etsi:Cert>'
                                    '<etsi:CertDigest>'
                                        '<ds:DigestMethod Algorithm="http://www.w3.org/2000/09/xmldsig#sha1"></ds:DigestMethod>'
                                        f'<ds:DigestValue>{cert_digest}</ds:DigestValue>'
                                    '</etsi:CertDigest>'
                                    '<etsi:IssuerSerial>'
                                        f'<ds:X509IssuerName>{_esc(issuer_name)}</ds:X509IssuerName>'
                                        f'<ds:X509SerialNumber>{serial_decimal}</ds:X509SerialNumber>'
                                    '</etsi:IssuerSerial>'
                                '</etsi:Cert>'
                            '</etsi:SigningCertificate>'
                        '</etsi:SignedSignatureProperties>'
                        '<etsi:SignedDataObjectProperties>'
                            f'<etsi:DataObjectFormat ObjectReference="#{refDocId}">'
                                '<etsi:Description>contenido comprobante</etsi:Description>'
                                '<etsi:MimeType>text/xml</etsi:MimeType>'
                            '</etsi:DataObjectFormat>'
                        '</etsi:SignedDataObjectProperties>'
                    '</etsi:SignedProperties>'
                '</etsi:QualifyingProperties>'
            '</ds:Object>'
        '</ds:Signature>'
    )

    full_xml = xml_str.replace('</factura>', signature_block + '</factura>')

    parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
    doc = etree.fromstring(full_xml.encode('utf-8'), parser=parser)

    # 1. docDigest — factura sin Signature
    factura_el = _find_by_id(doc, 'comprobante')
    factura_clone = etree.fromstring(etree.tostring(factura_el))
    for ch in list(factura_clone):
        # remover ds:Signature
        if etree.QName(ch).localname == 'Signature':
            factura_clone.remove(ch)
    doc_canon  = _canon_c14n(factura_clone)
    doc_digest = _sha1_b64(doc_canon)

    # 2. KeyInfo digest
    key_info_el  = _find_by_id(doc, certInfoId)
    ki_canon     = _canon_c14n(key_info_el)
    ki_digest    = _sha1_b64(ki_canon)

    # 3. SignedProperties digest
    sp_el      = _find_by_id(doc, spId)
    sp_canon   = _canon_c14n(sp_el)
    sp_digest  = _sha1_b64(sp_canon)

    # Inyectar digests en el XML como string (para preservar el orden exacto)
    signed_xml = (
        full_xml
        .replace('__SP_DIGEST__',  sp_digest)
        .replace('__KI_DIGEST__',  ki_digest)
        .replace('__DOC_DIGEST__', doc_digest)
    )

    # 4. Re-parse, canonicalizar SignedInfo, firmar
    doc2 = etree.fromstring(signed_xml.encode('utf-8'), parser=parser)
    sig_info_el = _find_by_id(doc2, sigInfoId)
    si_canon = _canon_c14n(sig_info_el)
    signature = private_key.sign(si_canon, padding.PKCS1v15(), hashes.SHA1())
    sig_value = base64.b64encode(signature).decode('ascii')

    return signed_xml.replace('__SIG_VALUE__', sig_value)
