"""
Helpers de reporte para facturación.

Regla de negocio (confirmada con el dueño): el IVA solo se cobra cuando el
cliente pide factura; las ventas sin factura van al precio base. Por eso el
"IVA cobrado" se calcula a partir de las facturas SRI ligadas a las ventas.

Se cuentan únicamente las facturas AUTORIZADAS: es el IVA legalmente
declarado ante el SRI. Borradores, emitidas-no-autorizadas, rechazadas y
anuladas no suman.
"""
from decimal import Decimal

from django.db.models import Sum, Q

from .models import FacturaSRI


def iva_cobrado(ventas_qs):
    """Suma del IVA de las facturas SRI autorizadas ligadas a `ventas_qs`.

    `ventas_qs` es un queryset de ventas.Venta. Las ventas sin factura (o con
    factura no autorizada) aportan 0. Devuelve siempre un Decimal.
    """
    return ventas_qs.aggregate(
        v=Sum(
            'factura_sri__iva_valor',
            filter=Q(factura_sri__estado=FacturaSRI.AUTORIZADA),
        )
    )['v'] or Decimal('0')
