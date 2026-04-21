"""
Validación de cédula y RUC Ecuador — algoritmo Módulo 11 del SRI.
"""


def validar_cedula_ecuador(cedula: str) -> bool:
    cedula = cedula.strip()
    if not cedula.isdigit() or len(cedula) != 10:
        return False
    provincia = int(cedula[:2])
    if provincia < 1 or provincia > 24:
        return False
    coeficientes = [2, 1, 2, 1, 2, 1, 2, 1, 2]
    total = 0
    for i, coef in enumerate(coeficientes):
        valor = int(cedula[i]) * coef
        if valor >= 10:
            valor -= 9
        total += valor
    digito_verificador = (10 - (total % 10)) % 10
    return digito_verificador == int(cedula[9])


def validar_ruc_persona_natural(ruc: str) -> bool:
    """RUC de persona natural: cédula + 001."""
    if len(ruc) != 13:
        return False
    if not ruc.endswith('001'):
        return False
    return validar_cedula_ecuador(ruc[:10])


def validar_ruc_sociedad(ruc: str) -> bool:
    """RUC de sociedad privada: tercer dígito = 9."""
    if len(ruc) != 13 or not ruc.isdigit():
        return False
    provincia = int(ruc[:2])
    if provincia < 1 or provincia > 24:
        return False
    if int(ruc[2]) != 9:
        return False
    coeficientes = [4, 3, 2, 7, 6, 5, 4, 3, 2]
    total = sum(int(ruc[i]) * coeficientes[i] for i in range(9))
    residuo = total % 11
    digito = 0 if residuo == 0 else 11 - residuo
    return digito == int(ruc[9])


def validar_ruc_publico(ruc: str) -> bool:
    """RUC de entidad pública: tercer dígito = 6."""
    if len(ruc) != 13 or not ruc.isdigit():
        return False
    provincia = int(ruc[:2])
    if provincia < 1 or provincia > 24:
        return False
    if int(ruc[2]) != 6:
        return False
    coeficientes = [3, 2, 7, 6, 5, 4, 3, 2]
    total = sum(int(ruc[i]) * coeficientes[i] for i in range(8))
    residuo = total % 11
    digito = 0 if residuo == 0 else 11 - residuo
    return digito == int(ruc[8])


def validar_cedula_o_ruc(valor: str) -> bool:
    valor = valor.strip()
    if len(valor) == 10:
        return validar_cedula_ecuador(valor)
    if len(valor) == 13:
        return (
            validar_ruc_persona_natural(valor)
            or validar_ruc_sociedad(valor)
            or validar_ruc_publico(valor)
        )
    return False
