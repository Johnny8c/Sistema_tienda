from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.inventario.models import Producto
from apps.ventas.models import Venta, ItemVenta
from apps.usuarios.models import Usuario

from .models import Adelanto, AdelantoItem, Deuda, Pago
from .exceptions import (
    SaldoInsuficienteError,
    AbonoExcedeSaldoError,
    EstadoInvalidoError,
    StockInsuficienteError,
    PermisoInsuficienteError,
)


def _calcular_total_items(items: list) -> Decimal:
    total = Decimal('0.00')
    for item in items:
        producto = Producto.objects.get(pk=item['producto_id'])
        total += producto.precio * item['cantidad']
    return total


@transaction.atomic
def crear_adelanto(cliente_id: int, items: list, monto_inicial: Decimal,
                   fecha_limite, vendedor: Usuario) -> Adelanto:
    cliente = Cliente.objects.get(pk=cliente_id)
    total = _calcular_total_items(items)

    if monto_inicial > total:
        raise SaldoInsuficienteError('El monto inicial no puede superar el total del apartado.')

    for item in items:
        producto = Producto.objects.select_for_update().get(pk=item['producto_id'])
        if producto.stock_disponible < item['cantidad']:
            raise StockInsuficienteError(
                f'Stock insuficiente para {producto.nombre}. '
                f'Disponible: {producto.stock_disponible}, solicitado: {item["cantidad"]}.'
            )

    adelanto = Adelanto.objects.create(
        cliente=cliente,
        total=total,
        saldo_pendiente=total - monto_inicial,
        fecha_limite=fecha_limite,
        vendedor=vendedor,
    )

    for item in items:
        producto = Producto.objects.select_for_update().get(pk=item['producto_id'])
        AdelantoItem.objects.create(
            adelanto=adelanto,
            producto=producto,
            cantidad=item['cantidad'],
            precio_unitario=producto.precio,
        )
        producto.stock_reservado += item['cantidad']
        producto.save(update_fields=['stock_reservado'])

    if monto_inicial > 0:
        Pago.objects.create(
            tipo=Pago.TIPO_ADELANTO,
            referencia_id=adelanto.id,
            monto=monto_inicial,
            forma_pago=Pago.EFECTIVO,
            vendedor=vendedor,
        )

    return adelanto


@transaction.atomic
def registrar_abono_adelanto(adelanto_id: int, monto: Decimal,
                             forma_pago: str, vendedor: Usuario) -> Pago:
    adelanto = Adelanto.objects.select_for_update().get(pk=adelanto_id)

    if adelanto.estado != Adelanto.ACTIVO:
        raise EstadoInvalidoError(
            f'No se puede abonar a un adelanto en estado "{adelanto.estado}".'
        )
    if monto > adelanto.saldo_pendiente:
        raise AbonoExcedeSaldoError(
            f'El abono (${monto}) supera el saldo pendiente (${adelanto.saldo_pendiente}).'
        )

    adelanto.saldo_pendiente -= monto
    adelanto.save(update_fields=['saldo_pendiente'])

    return Pago.objects.create(
        tipo=Pago.TIPO_ADELANTO,
        referencia_id=adelanto_id,
        monto=monto,
        forma_pago=forma_pago,
        vendedor=vendedor,
    )


@transaction.atomic
def completar_adelanto(adelanto_id: int, vendedor: Usuario) -> Venta:
    adelanto = Adelanto.objects.select_for_update().get(pk=adelanto_id)

    if adelanto.estado != Adelanto.ACTIVO:
        raise EstadoInvalidoError(
            f'Solo se puede completar un adelanto activo. Estado actual: "{adelanto.estado}".'
        )
    if adelanto.saldo_pendiente > 0:
        raise SaldoInsuficienteError(
            f'El adelanto aún tiene saldo pendiente de ${adelanto.saldo_pendiente}.'
        )

    venta = Venta.objects.create(
        cliente=adelanto.cliente,
        tipo_pago=Venta.ADELANTO_COMPLETADO,
        total=adelanto.total,
        vendedor=vendedor,
    )

    for item in adelanto.items.select_related('producto').all():
        ItemVenta.objects.create(
            venta=venta,
            producto=item.producto,
            cantidad=item.cantidad,
            precio_unitario=item.precio_unitario,
        )
        producto = Producto.objects.select_for_update().get(pk=item.producto_id)
        producto.stock -= item.cantidad
        producto.stock_reservado -= item.cantidad
        producto.save(update_fields=['stock', 'stock_reservado'])

    adelanto.estado = Adelanto.COMPLETADO
    adelanto.save(update_fields=['estado'])

    return venta


@transaction.atomic
def cancelar_adelanto(adelanto_id: int, motivo: str, vendedor: Usuario,
                      tipo_devolucion: str = 'saldo_favor',
                      forma_pago: str = 'efectivo') -> Adelanto:
    """
    Cancela un adelanto y maneja el dinero ya pagado según tipo_devolucion:
      - 'saldo_favor': se acredita al saldo a favor del cliente (default)
      - 'reembolso':   se devuelve el dinero (se registra como pago de salida)
    """
    if not vendedor.es_dueno():
        raise PermisoInsuficienteError('Solo el dueño puede cancelar apartados.')

    adelanto = Adelanto.objects.select_for_update().get(pk=adelanto_id)

    if adelanto.estado != Adelanto.ACTIVO:
        raise EstadoInvalidoError(
            f'Solo se puede cancelar un adelanto activo. Estado actual: "{adelanto.estado}".'
        )

    monto_pagado = adelanto.total - adelanto.saldo_pendiente

    # Liberar stock reservado
    for item in adelanto.items.select_related('producto').all():
        producto = Producto.objects.select_for_update().get(pk=item.producto_id)
        producto.stock_reservado -= item.cantidad
        producto.save(update_fields=['stock_reservado'])

    # Manejar el dinero ya pagado
    nota_devolucion = ''
    if monto_pagado > 0:
        if tipo_devolucion == 'reembolso':
            # Registrar como movimiento de SALIDA en Pago (monto negativo)
            Pago.objects.create(
                tipo=Pago.TIPO_ADELANTO,
                referencia_id=adelanto.pk,
                monto=-monto_pagado,
                forma_pago=forma_pago,
                vendedor=vendedor,
                notas=f'REEMBOLSO por cancelación de apartado #{adelanto.pk}: {motivo}',
            )
            nota_devolucion = f'Reembolso de ${monto_pagado} ({forma_pago}).'
        else:
            # saldo a favor
            cliente = Cliente.objects.select_for_update().get(pk=adelanto.cliente_id)
            cliente.saldo_a_favor += monto_pagado
            cliente.save(update_fields=['saldo_a_favor'])
            nota_devolucion = f'${monto_pagado} acreditado como saldo a favor.'

    adelanto.estado = Adelanto.CANCELADO
    adelanto.notas = f'Cancelado: {motivo}. {nota_devolucion}'.strip()
    adelanto.save(update_fields=['estado', 'notas'])

    return adelanto


@transaction.atomic
def crear_venta_credito(cliente_id: int, items: list,
                        plazo_dias: int, vendedor: Usuario) -> Deuda:
    cliente = Cliente.objects.get(pk=cliente_id)
    total = _calcular_total_items(items)

    for item in items:
        producto = Producto.objects.select_for_update().get(pk=item['producto_id'])
        if producto.stock_disponible < item['cantidad']:
            raise StockInsuficienteError(
                f'Stock insuficiente para {producto.nombre}. '
                f'Disponible: {producto.stock_disponible}, solicitado: {item["cantidad"]}.'
            )

    venta = Venta.objects.create(
        cliente=cliente,
        tipo_pago=Venta.CREDITO,
        total=total,
        vendedor=vendedor,
    )

    for item in items:
        producto = Producto.objects.select_for_update().get(pk=item['producto_id'])
        ItemVenta.objects.create(
            venta=venta,
            producto=producto,
            cantidad=item['cantidad'],
            precio_unitario=producto.precio,
        )
        producto.stock -= item['cantidad']
        producto.save(update_fields=['stock'])

    fecha_vencimiento = None
    if plazo_dias:
        fecha_vencimiento = (timezone.now() + timezone.timedelta(days=plazo_dias)).date()

    deuda = Deuda.objects.create(
        cliente=cliente,
        venta=venta,
        monto_original=total,
        saldo_pendiente=total,
        fecha_vencimiento=fecha_vencimiento,
        vendedor=vendedor,
    )

    venta.deuda_id = deuda.id
    venta.save(update_fields=['deuda_id'])

    return deuda


@transaction.atomic
def registrar_abono_deuda(deuda_id: int, monto: Decimal,
                          forma_pago: str, vendedor: Usuario) -> Pago:
    deuda = Deuda.objects.select_for_update().get(pk=deuda_id)

    if deuda.estado != Deuda.PENDIENTE:
        raise EstadoInvalidoError(
            f'No se puede abonar a una deuda en estado "{deuda.estado}".'
        )
    if monto > deuda.saldo_pendiente:
        raise AbonoExcedeSaldoError(
            f'El abono (${monto}) supera el saldo pendiente (${deuda.saldo_pendiente}).'
        )

    deuda.saldo_pendiente -= monto
    if deuda.saldo_pendiente == 0:
        deuda.estado = Deuda.SALDADA
    deuda.save(update_fields=['saldo_pendiente', 'estado'])

    return Pago.objects.create(
        tipo=Pago.TIPO_DEUDA,
        referencia_id=deuda_id,
        monto=monto,
        forma_pago=forma_pago,
        vendedor=vendedor,
    )


@transaction.atomic
def saldar_deuda(deuda_id: int, vendedor: Usuario) -> Deuda:
    deuda = Deuda.objects.select_for_update().get(pk=deuda_id)

    if deuda.estado != Deuda.PENDIENTE:
        raise EstadoInvalidoError(
            f'Solo se puede saldar una deuda pendiente. Estado actual: "{deuda.estado}".'
        )

    if deuda.saldo_pendiente > 0:
        Pago.objects.create(
            tipo=Pago.TIPO_DEUDA,
            referencia_id=deuda_id,
            monto=deuda.saldo_pendiente,
            forma_pago=Pago.EFECTIVO,
            vendedor=vendedor,
        )

    deuda.saldo_pendiente = Decimal('0.00')
    deuda.estado = Deuda.SALDADA
    deuda.save(update_fields=['saldo_pendiente', 'estado'])

    return deuda


@transaction.atomic
def condonar_deuda(deuda_id: int, motivo: str, vendedor: Usuario) -> Deuda:
    if not vendedor.es_dueno():
        raise PermisoInsuficienteError('Solo el dueño puede condonar deudas.')

    deuda = Deuda.objects.select_for_update().get(pk=deuda_id)

    if deuda.estado != Deuda.PENDIENTE:
        raise EstadoInvalidoError(
            f'Solo se puede condonar una deuda pendiente. Estado actual: "{deuda.estado}".'
        )

    deuda.estado = Deuda.CONDONADA
    deuda.save(update_fields=['estado'])

    return deuda
