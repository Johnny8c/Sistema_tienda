"""
Cifrado AES-256-GCM para almacenar el .p12 + parsing del certificado.
Puerto de p12Crypto.js
"""
import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import pkcs12

ALGORITHM   = 'aes-256-gcm'
IV_LEN      = 12
TAG_LEN     = 16
ENC_PREFIX  = 'enc:'


def _system_key():
    hex_key = os.environ.get('SRI_P12_ENCRYPTION_KEY', '')
    if not hex_key or len(hex_key) != 64:
        return None
    return bytes.fromhex(hex_key)


def cifrar_dato(plaintext: str) -> str:
    key = _system_key()
    if not key:
        # Sin clave configurada, devolvemos el dato tal cual (modo dev)
        return plaintext
    iv = os.urandom(IV_LEN)
    aesgcm = AESGCM(key)
    # AESGCM.encrypt returns ciphertext+tag concatenated
    ct_with_tag = aesgcm.encrypt(iv, plaintext.encode('utf-8'), None)
    enc       = ct_with_tag[:-TAG_LEN]
    auth_tag  = ct_with_tag[-TAG_LEN:]
    combined  = iv + auth_tag + enc
    return ENC_PREFIX + base64.b64encode(combined).decode('ascii')


def descifrar_dato(stored: str) -> str:
    if not stored:
        return stored
    if not stored.startswith(ENC_PREFIX):
        return stored
    key = _system_key()
    if not key:
        raise RuntimeError('SRI_P12_ENCRYPTION_KEY no configurada — no se puede descifrar el certificado.')

    combined = base64.b64decode(stored[len(ENC_PREFIX):])
    iv         = combined[:IV_LEN]
    auth_tag   = combined[IV_LEN:IV_LEN + TAG_LEN]
    ciphertext = combined[IV_LEN + TAG_LEN:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(iv, ciphertext + auth_tag, None).decode('utf-8')


def extraer_info_certificado(p12_base64: str, password: str):
    """
    Devuelve dict {titular, vencimiento, dias_para_vencer} o None.
    """
    try:
        p12_bytes = base64.b64decode(p12_base64)
        priv, cert, addl = pkcs12.load_key_and_certificates(p12_bytes, password.encode('utf-8'))
        if cert is None:
            return None
        titular_attrs = []
        for rdn in cert.subject.rdns:
            for attr in rdn:
                short = _short_name(attr.oid.dotted_string)
                titular_attrs.append(f'{short}={attr.value}')
        titular = ', '.join(titular_attrs)
        vencimiento = cert.not_valid_after_utc
        from datetime import datetime, timezone
        ahora = datetime.now(timezone.utc)
        dias = int((vencimiento - ahora).total_seconds() // 86400)
        return {
            'titular':           titular,
            'vencimiento':       vencimiento,
            'dias_para_vencer':  dias,
        }
    except Exception as e:
        print(f'[p12Crypto] Error extrayendo info del cert: {e}')
        return None


def validar_p12(p12_base64: str, password: str):
    """Levanta excepción si el .p12 o la clave son inválidos."""
    try:
        p12_bytes = base64.b64decode(p12_base64)
        pkcs12.load_key_and_certificates(p12_bytes, password.encode('utf-8'))
    except ValueError as e:
        msg = str(e)
        if 'mac' in msg.lower() or 'invalid password' in msg.lower() or 'incorrect' in msg.lower():
            raise ValueError('Contraseña del certificado incorrecta.')
        raise ValueError(f'Archivo P12 inválido o corrupto: {msg}')
    except Exception as e:
        raise ValueError(f'Error leyendo el certificado: {e}')


_OID_TO_SHORT = {
    '2.5.4.3':  'CN',
    '2.5.4.4':  'SN',
    '2.5.4.5':  'serialNumber',
    '2.5.4.6':  'C',
    '2.5.4.7':  'L',
    '2.5.4.8':  'ST',
    '2.5.4.9':  'STREET',
    '2.5.4.10': 'O',
    '2.5.4.11': 'OU',
    '2.5.4.12': 'T',
    '2.5.4.42': 'GN',
    '2.5.4.43': 'INITIALS',
    '2.5.4.44': 'generationQualifier',
    '2.5.4.46': 'DNQUALIFIER',
    '2.5.4.97': 'organizationIdentifier',
    '0.9.2342.19200300.100.1.1':  'UID',
    '0.9.2342.19200300.100.1.25': 'DC',
    '1.2.840.113549.1.9.1':       'EMAILADDRESS',
}


def _short_name(oid_dotted: str) -> str:
    return _OID_TO_SHORT.get(oid_dotted, oid_dotted)
