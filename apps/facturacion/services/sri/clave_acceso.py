"""
Genera la clave de acceso de 49 dígitos según especificación SRI.
Puerto directo de claveAcceso.js
"""
import random
from datetime import datetime, date


def calcular_digito_modulo11(base48: str) -> str:
    digits = [int(c) for c in base48]
    factores = [2, 3, 4, 5, 6, 7]
    suma = 0
    for i in range(len(digits) - 1, -1, -1):
        suma += digits[i] * factores[(len(digits) - 1 - i) % 6]
    residuo = suma % 11
    if residuo == 0:
        return '0'
    if residuo == 1:
        return '1'
    return str(11 - residuo)


def generar_clave_acceso(fecha_emision, ruc, ambiente, secuencial,
                         tipo_emision='1', serie='001001'):
    """
    Estructura: ddmmyyyy(8) + tipoDoc(2) + RUC(13) + ambiente(1) +
                serie(6) + secuencial(9) + codNumerico(8) + tipoEmision(1) + digito(1)

    fecha_emision : date | datetime | str ISO 'YYYY-MM-DD'
    ruc           : str (13 dígitos)
    ambiente      : 'pruebas' | 'produccion'
    secuencial    : int
    tipo_emision  : '1' normal | '2' contingencia
    serie         : 6 dígitos = estab(3) + ptoEmi(3)
    """
    if isinstance(fecha_emision, (datetime, date)):
        fecha = fecha_emision if isinstance(fecha_emision, datetime) else datetime.combine(fecha_emision, datetime.min.time())
    else:
        fecha = datetime.fromisoformat(str(fecha_emision)[:10] + 'T12:00:00')

    dd      = f'{fecha.day:02d}'
    mm      = f'{fecha.month:02d}'
    yyyy    = f'{fecha.year}'
    fechaStr = f'{dd}{mm}{yyyy}'                              # 8

    tipo_comprobante = '01'                                   # 2
    ruc_str          = str(ruc).zfill(13)                     # 13
    ambiente_cod     = '2' if ambiente == 'produccion' else '1'  # 1
    serie_str        = serie.replace('-', '').zfill(6)[:6]    # 6
    secuencial_str   = str(secuencial).zfill(9)               # 9
    codigo_numerico  = f'{random.randint(0, 99999999):08d}'   # 8

    base = f'{fechaStr}{tipo_comprobante}{ruc_str}{ambiente_cod}{serie_str}{secuencial_str}{codigo_numerico}{tipo_emision}'
    return base + calcular_digito_modulo11(base)              # total = 49
