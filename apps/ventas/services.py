"""
Servicios de ventas: lógica de negocio extraída del view procesar_venta.

`crear_venta_contado()` valida stock, precio (según preferencias del sistema)
y registra la venta + items + descuento de stock dentro de una transacción.
"""
from decimal import Decimal
from django.db import transaction

from apps.deudores.exceptions import StockInsuficienteError
from apps.inventario.models import Producto
from .models import Venta, ItemVenta


@transaction.atomic
def crear_venta_contado(*, items, cliente_id, vendedor, forma_pago, cfg_gen):
    """
    Crea una venta al contado con sus ItemVenta y descuenta stock.

    Args:
        items: list de dicts {producto_id, cantidad, precio_unitario}
        cliente_id: int | None
        vendedor: Usuario
        forma_pago: 'efectivo' | 'tarjeta' | 'transferencia'
        cfg_gen: ConfiguracionGeneral (singleton, ya cargado)

    Returns:
        Venta creada.

    Raises:
        StockInsuficienteError: stock < cantidad y permitir_vender_sin_stock=False
        ValueError: precio inválido o fuera de rango (modo bloquear)
    """
    if not items:
        raise ValueError('Agrega al menos un producto.')

    # Validar y bloquear filas de productos antes de crear nada
    productos_locked = {}
    for i in items:
        prod = (Producto.objects
                .select_related('catalogo')
                .select_for_update()
                .get(pk=i['producto_id']))
        productos_locked[prod.pk] = prod

        cant = i['cantidad']
        if prod.stock_disponible < cant and not cfg_gen.permitir_vender_sin_stock:
            raise StockInsuficienteError(
                f'"{prod.nombre}" tiene solo {prod.stock_disponible} unidades disponibles '
                f'({prod.stock_reservado} reservadas en apartados). '
                f'No se puede vender {cant}.'
            )

        # Precio: del carrito si viene, sino del producto
        pu = Decimal(str(i.get('precio_unitario', prod.precio)))
        if pu <= 0:
            raise ValueError(f'Precio unitario inválido para "{prod.nombre}".')

        # Validar rango si la preferencia es bloquear
        if cfg_gen.precio_fuera_rango_modo == cfg_gen.PRECIO_RANGO_BLOQUEAR and prod.catalogo:
            if prod.catalogo.precio_minimo is not None and pu < prod.catalogo.precio_minimo:
                raise ValueError(
                    f'"{prod.nombre}" no se puede vender por debajo de '
                    f'${prod.catalogo.precio_minimo} (precio mínimo).'
                )
            if prod.catalogo.precio_maximo is not None and pu > prod.catalogo.precio_maximo:
                raise ValueError(
                    f'"{prod.nombre}" no se puede vender por encima de '
                    f'${prod.catalogo.precio_maximo} (precio máximo).'
                )

    # Calcular total con los precios resueltos (usando productos ya bloqueados)
    total = Decimal('0')
    items_resueltos = []
    for i in items:
        prod = productos_locked[i['producto_id']]
        pu = Decimal(str(i.get('precio_unitario', prod.precio)))
        items_resueltos.append({'prod': prod, 'cantidad': i['cantidad'], 'pu': pu})
        total += pu * i['cantidad']

    # Crear venta + items + descontar stock
    venta = Venta.objects.create(
        cliente_id=int(cliente_id) if cliente_id else None,
        tipo_pago=Venta.CONTADO,
        forma_pago=forma_pago,
        total=total,
        vendedor=vendedor,
    )
    for ir in items_resueltos:
        ItemVenta.objects.create(
            venta=venta,
            producto=ir['prod'],
            cantidad=ir['cantidad'],
            precio_unitario=ir['pu'],
        )
        ir['prod'].stock -= ir['cantidad']
        ir['prod'].save(update_fields=['stock'])

    return venta
