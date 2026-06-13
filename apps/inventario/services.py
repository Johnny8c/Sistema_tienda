"""Servicios de inventario: bitácora de movimientos.

`registrar_movimiento()` es el ÚNICO punto que escribe MovimientoInventario y
mantiene `Producto.stock_anterior`. Lo llaman todos los flujos que cambian
stock o reservas: ajuste manual, ventas (contado/crédito), apartados
(reserva/entrega/cancelación), compras a proveedor y creación de variantes.
"""
from .models import MovimientoInventario, Producto


def registrar_movimiento(producto, tipo, *, stock_anterior, stock_nuevo,
                         usuario=None, reservado_anterior=None,
                         reservado_nuevo=None, referencia='', nota=''):
    """Crea un registro de auditoría y actualiza Producto.stock_anterior.

    Args:
        producto: la variante (Producto) afectada.
        tipo: una de MovimientoInventario.* (CREACION, AJUSTE, VENTA, ...).
        stock_anterior / stock_nuevo: stock físico antes y después. Para
            movimientos que solo cambian reservas (apartado/cancelación),
            pasar el mismo valor en ambos y llenar reservado_*.
        usuario: quién lo hizo (None = sistema).
        referencia: texto corto que enlaza al documento ('Venta #12').
        nota: detalle opcional legible.

    Debe llamarse dentro de la misma transacción que aplicó el cambio.
    """
    MovimientoInventario.objects.create(
        producto=producto,
        codigo_barras=(producto.codigo_barras or ''),
        nombre_producto=str(producto)[:250],
        tipo=tipo,
        stock_anterior=stock_anterior,
        stock_nuevo=stock_nuevo,
        reservado_anterior=reservado_anterior,
        reservado_nuevo=reservado_nuevo,
        usuario=usuario,
        referencia=referencia,
        nota=nota,
    )
    # "Stock anterior" de la pantalla de ajuste: solo cambia cuando se movió el
    # stock físico (un apartado, que solo reserva, no lo altera).
    if stock_nuevo != stock_anterior and producto.pk:
        Producto.objects.filter(pk=producto.pk).update(stock_anterior=stock_anterior)
        producto.stock_anterior = stock_anterior
