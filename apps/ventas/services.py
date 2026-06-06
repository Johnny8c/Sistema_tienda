"""
Servicios de ventas: lógica de negocio extraída del view procesar_venta.

`crear_venta_contado()` valida stock, precio (según preferencias del sistema)
y registra la venta + items + descuento de stock dentro de una transacción.
"""
from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.deudores.exceptions import StockInsuficienteError
from apps.inventario.models import Producto

from .models import ItemVenta, Venta


def _parse_cantidad(raw_value, nombre_producto):
    try:
        cantidad = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Cantidad inválida para "{nombre_producto}".') from exc

    if cantidad <= 0:
        raise ValueError(f'Cantidad inválida para "{nombre_producto}".')

    return cantidad


def _parse_precio_unitario(raw_value, precio_default, nombre_producto):
    valor = precio_default if raw_value in (None, '') else raw_value

    try:
        precio = Decimal(str(valor).strip().replace(',', '.'))
    except InvalidOperation as exc:
        raise ValueError(f'Precio unitario inválido para "{nombre_producto}".') from exc

    if precio <= 0:
        raise ValueError(f'Precio unitario inválido para "{nombre_producto}".')

    return precio


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

    productos_locked = {}
    items_resueltos = []
    total = Decimal('0')

    for item in items:
        producto_id = item.get('producto_id')
        if not producto_id:
            raise ValueError('Hay un producto inválido en el carrito.')

        prod = productos_locked.get(producto_id)
        if prod is None:
            try:
                # of=('self',) bloquea solo la fila de Producto. Sin esto,
                # Postgres rechaza FOR UPDATE porque select_related('catalogo')
                # genera LEFT OUTER JOIN sobre una FK nullable.
                prod = (
                    Producto.objects
                    .select_related('catalogo')
                    .select_for_update(of=('self',))
                    .get(pk=producto_id)
                )
            except Producto.DoesNotExist as exc:
                raise ValueError('Hay un producto inválido o ya no disponible en el carrito.') from exc
            productos_locked[producto_id] = prod

        cant = _parse_cantidad(item.get('cantidad'), prod.nombre)
        pu = _parse_precio_unitario(item.get('precio_unitario'), prod.precio, prod.nombre)

        if prod.stock_disponible < cant and not cfg_gen.permitir_vender_sin_stock:
            raise StockInsuficienteError(
                f'"{prod.nombre}" tiene solo {prod.stock_disponible} unidades disponibles '
                f'({prod.stock_reservado} reservadas en apartados). '
                f'No se puede vender {cant}.'
            )

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

        items_resueltos.append({'prod': prod, 'cantidad': cant, 'pu': pu})
        total += pu * cant

    venta = Venta.objects.create(
        cliente_id=int(cliente_id) if cliente_id else None,
        tipo_pago=Venta.CONTADO,
        forma_pago=forma_pago,
        total=total,
        vendedor=vendedor,
    )
    for item in items_resueltos:
        ItemVenta.objects.create(
            venta=venta,
            producto=item['prod'],
            cantidad=item['cantidad'],
            precio_unitario=item['pu'],
        )
        item['prod'].stock -= item['cantidad']
        item['prod'].save(update_fields=['stock'])
        # La etiqueta impresa se va con la prenda vendida: descontar el snapshot
        # para que al reponer stock se detecte que faltan etiquetas nuevas.
        from apps.inventario.models import EtiquetaImpresa
        EtiquetaImpresa.descontar_por_venta(item['prod'].codigo_barras, item['cantidad'])

    return venta
