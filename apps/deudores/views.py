import json
import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.inventario.models import Producto
from apps.usuarios.decorators import requiere_dueno, requiere_no_bodeguero

from .exceptions import (
    AbonoExcedeSaldoError,
    EstadoInvalidoError,
    PermisoInsuficienteError,
    SaldoInsuficienteError,
    StockInsuficienteError,
)
from .models import Adelanto, Deuda, Pago
from .services import (
    cancelar_adelanto,
    completar_adelanto,
    condonar_deuda,
    crear_adelanto,
    crear_venta_credito,
    registrar_abono_adelanto,
    registrar_abono_deuda,
    saldar_deuda,
)

logger = logging.getLogger(__name__)


def _verificar_propietario_o_dueno(request, obj, redirect_name, pk):
    """Permite solo al vendedor que creo el objeto o al dueno operar sobre el.
    Devuelve un redirect a `redirect_name` con mensaje de error si no aplica,
    o None si esta autorizado. Asume que `obj` tiene campo `vendedor`."""
    user = request.user
    if user.es_dueno():
        return None
    if obj.vendedor_id == user.pk:
        return None
    messages.error(
        request,
        'No puedes operar sobre este registro porque pertenece a otro vendedor.'
    )
    return redirect(redirect_name, pk=pk)


def _productos_data():
    """Lista plana de productos. Se entrega al template como dato para
    json_script (escape-seguro contra XSS)."""
    return [
        {
            'id': p.pk,
            'nombre': p.nombre,
            'talla': p.talla,
            'color': p.color,
            'precio': str(p.precio),
            'stock_disponible': p.stock_disponible,
            'codigo_barras': p.codigo_barras or '',
            'precio_min': (
                str(p.catalogo.precio_minimo)
                if p.catalogo and p.catalogo.precio_minimo is not None
                else None
            ),
            'precio_max': (
                str(p.catalogo.precio_maximo)
                if p.catalogo and p.catalogo.precio_maximo is not None
                else None
            ),
        }
        for p in Producto.objects.select_related('catalogo').filter(activo=True)
    ]


@login_required
@requiere_no_bodeguero
def lista_adelantos(request):
    q = request.GET.get('q', '')
    estado = request.GET.get('estado', 'activo')
    qs = Adelanto.objects.select_related('cliente').order_by('-fecha_creacion')
    if estado:
        qs = qs.filter(estado=estado)
    if q:
        qs = qs.filter(Q(cliente__nombre__icontains=q) | Q(cliente__cedula_ruc__icontains=q))

    adelantos = list(qs)
    for adelanto in adelantos:
        adelanto.abonado = adelanto.total - adelanto.saldo_pendiente
        adelanto.pct_pagado = int((adelanto.abonado / adelanto.total) * 100) if adelanto.total else 0

    return render(
        request,
        'deudores/adelantos/lista.html',
        {'adelantos': adelantos, 'q': q, 'estado': estado, 'hoy': timezone.now().date()},
    )


@login_required
@requiere_no_bodeguero
def crear_adelanto_view(request):
    clientes = Cliente.objects.filter(activo=True).order_by('nombre')
    productos = Producto.objects.filter(activo=True)

    if request.method == 'POST':
        cliente_id = request.POST.get('cliente_id')
        monto_inicial = request.POST.get('monto_inicial', '0')
        fecha_limite = request.POST.get('fecha_limite') or None
        producto_ids = request.POST.getlist('producto_id')
        cantidades = request.POST.getlist('cantidad')

        if not cliente_id or not producto_ids:
            messages.error(request, 'Selecciona un cliente y al menos un producto.')
            return render(
                request,
                'deudores/adelantos/crear.html',
                {'clientes': clientes, 'productos': productos, 'productos_data': _productos_data()},
            )

        items = [
            {'producto_id': int(pid), 'cantidad': int(cant)}
            for pid, cant in zip(producto_ids, cantidades)
            if pid and int(cant) > 0
        ]
        try:
            adelanto = crear_adelanto(
                cliente_id=int(cliente_id),
                items=items,
                monto_inicial=Decimal(monto_inicial),
                fecha_limite=fecha_limite,
                vendedor=request.user,
            )
            messages.success(request, f'Apartado #{adelanto.pk} creado correctamente.')
            return redirect('detalle_adelanto', pk=adelanto.pk)
        except (SaldoInsuficienteError, StockInsuficienteError) as exc:
            messages.error(request, str(exc))

    return render(
        request,
        'deudores/adelantos/crear.html',
        {'clientes': clientes, 'productos': productos, 'productos_data': _productos_data()},
    )


@login_required
@requiere_no_bodeguero
def detalle_adelanto(request, pk):
    adelanto = get_object_or_404(Adelanto.objects.select_related('cliente', 'vendedor'), pk=pk)
    pagos = Pago.objects.filter(tipo=Pago.TIPO_ADELANTO, referencia_id=pk).order_by('fecha')
    return render(request, 'deudores/adelantos/detalle.html', {'adelanto': adelanto, 'pagos': pagos})


@login_required
@requiere_no_bodeguero
def abonar_adelanto(request, pk):
    if request.method != 'POST':
        return redirect('detalle_adelanto', pk=pk)

    adelanto = get_object_or_404(Adelanto, pk=pk)
    bloqueo = _verificar_propietario_o_dueno(request, adelanto, 'detalle_adelanto', pk)
    if bloqueo:
        return bloqueo

    monto = request.POST.get('monto', '0')
    forma_pago = request.POST.get('forma_pago', 'efectivo')
    try:
        registrar_abono_adelanto(pk, Decimal(monto), forma_pago, request.user)
        messages.success(request, f'Abono de ${monto} registrado.')
    except (AbonoExcedeSaldoError, EstadoInvalidoError) as exc:
        messages.error(request, str(exc))
    return redirect('detalle_adelanto', pk=pk)


@login_required
@requiere_no_bodeguero
def completar_adelanto_view(request, pk):
    if request.method != 'POST':
        return redirect('detalle_adelanto', pk=pk)

    adelanto = get_object_or_404(Adelanto, pk=pk)
    bloqueo = _verificar_propietario_o_dueno(request, adelanto, 'detalle_adelanto', pk)
    if bloqueo:
        return bloqueo

    try:
        completar_adelanto(pk, request.user)
        messages.success(request, 'Apartado completado. Venta generada.')
    except (EstadoInvalidoError, SaldoInsuficienteError) as exc:
        messages.error(request, str(exc))
    return redirect('detalle_adelanto', pk=pk)


@login_required
@requiere_dueno
def cancelar_adelanto_view(request, pk):
    if request.method != 'POST':
        return redirect('detalle_adelanto', pk=pk)

    motivo = request.POST.get('motivo', '')
    tipo_devolucion = request.POST.get('tipo_devolucion', 'saldo_favor')
    forma_pago = request.POST.get('forma_pago', 'efectivo')
    if tipo_devolucion not in ('saldo_favor', 'reembolso'):
        tipo_devolucion = 'saldo_favor'
    if forma_pago not in ('efectivo', 'tarjeta', 'transferencia'):
        forma_pago = 'efectivo'

    try:
        cancelar_adelanto(
            pk,
            motivo,
            request.user,
            tipo_devolucion=tipo_devolucion,
            forma_pago=forma_pago,
        )
        if tipo_devolucion == 'reembolso':
            messages.success(request, 'Apartado cancelado. Reembolso registrado en el cierre de caja.')
        else:
            messages.success(request, 'Apartado cancelado. Saldo transferido como credito a favor del cliente.')
    except (EstadoInvalidoError, PermisoInsuficienteError) as exc:
        messages.error(request, str(exc))
    return redirect('detalle_adelanto', pk=pk)


@login_required
@requiere_no_bodeguero
def lista_deudas(request):
    q = request.GET.get('q', '')
    estado = request.GET.get('estado', 'pendiente')
    qs = Deuda.objects.select_related('cliente').order_by('-fecha_creacion')
    if estado:
        qs = qs.filter(estado=estado)
    if q:
        qs = qs.filter(Q(cliente__nombre__icontains=q) | Q(cliente__cedula_ruc__icontains=q))

    pendientes = qs.filter(estado=Deuda.PENDIENTE)

    def bucket_sum(dias_min, dias_max=None):
        hoy = timezone.now().date()
        total = Decimal('0')
        for deuda in pendientes:
            dias = (hoy - deuda.fecha_creacion.date()).days
            en_rango = dias >= dias_min and (dias_max is None or dias <= dias_max)
            if en_rango:
                total += deuda.saldo_pendiente
        return total

    deudas = list(qs)
    for deuda in deudas:
        deuda.abonado = deuda.monto_original - deuda.saldo_pendiente
        deuda.pct_pagado = int((deuda.abonado / deuda.monto_original) * 100) if deuda.monto_original else 0

    return render(
        request,
        'deudores/deudas/lista.html',
        {
            'deudas': deudas,
            'q': q,
            'estado': estado,
            'hoy': timezone.now().date(),
            'bucket_0_30': bucket_sum(0, 30),
            'bucket_31_60': bucket_sum(31, 60),
            'bucket_61_90': bucket_sum(61, 90),
            'bucket_90_mas': bucket_sum(91),
        },
    )


@login_required
@requiere_no_bodeguero
def detalle_deuda(request, pk):
    deuda = get_object_or_404(Deuda.objects.select_related('cliente', 'vendedor'), pk=pk)
    pagos = Pago.objects.filter(tipo=Pago.TIPO_DEUDA, referencia_id=pk).order_by('fecha')
    return render(request, 'deudores/deudas/detalle.html', {'deuda': deuda, 'pagos': pagos})


@login_required
@requiere_no_bodeguero
def abonar_deuda(request, pk):
    if request.method != 'POST':
        return redirect('detalle_deuda', pk=pk)

    deuda = get_object_or_404(Deuda, pk=pk)
    bloqueo = _verificar_propietario_o_dueno(request, deuda, 'detalle_deuda', pk)
    if bloqueo:
        return bloqueo

    monto = request.POST.get('monto', '0')
    forma_pago = request.POST.get('forma_pago', 'efectivo')
    try:
        registrar_abono_deuda(pk, Decimal(monto), forma_pago, request.user)
        messages.success(request, f'Abono de ${monto} registrado.')
    except (AbonoExcedeSaldoError, EstadoInvalidoError) as exc:
        messages.error(request, str(exc))
    return redirect('detalle_deuda', pk=pk)


@login_required
@requiere_no_bodeguero
def saldar_deuda_view(request, pk):
    if request.method != 'POST':
        return redirect('detalle_deuda', pk=pk)

    deuda = get_object_or_404(Deuda, pk=pk)
    bloqueo = _verificar_propietario_o_dueno(request, deuda, 'detalle_deuda', pk)
    if bloqueo:
        return bloqueo

    try:
        saldar_deuda(pk, request.user)
        messages.success(request, 'Deuda saldada completamente.')
    except EstadoInvalidoError as exc:
        messages.error(request, str(exc))
    return redirect('detalle_deuda', pk=pk)


@login_required
@requiere_dueno
def condonar_deuda_view(request, pk):
    if request.method != 'POST':
        return redirect('detalle_deuda', pk=pk)

    motivo = request.POST.get('motivo', '')
    try:
        condonar_deuda(pk, motivo, request.user)
        messages.success(request, 'Deuda condonada.')
    except (EstadoInvalidoError, PermisoInsuficienteError) as exc:
        messages.error(request, str(exc))
    return redirect('detalle_deuda', pk=pk)


@login_required
@requiere_no_bodeguero
def pos(request):
    clientes = Cliente.objects.filter(activo=True).order_by('nombre')
    clientes_data = [
        {
            'id': cliente.pk,
            'nombre': cliente.nombre,
            'cedula_ruc': cliente.cedula_ruc,
            'telefono': cliente.telefono or '',
        }
        for cliente in clientes
    ]

    from apps.facturacion.models import ConfiguracionSRI
    cfg_sri = ConfiguracionSRI.get_singleton()
    iva_porcentaje = cfg_sri.iva_porcentaje if cfg_sri else 15

    return render(
        request,
        'pos/index.html',
        {
            'clientes': clientes,
            'clientes_data': clientes_data,
            'productos_data': _productos_data(),
            'iva_porcentaje': iva_porcentaje,
        },
    )


def _emitir_factura_si_corresponde(request, venta):
    """Emite factura SRI si el POS la solicito y la venta tiene cliente."""
    if request.POST.get('emitir_factura') != '1' or not venta.cliente_id:
        return None

    from apps.facturacion.models import ConfiguracionSRI
    from apps.facturacion.views import _crear_factura_desde_venta, _emitir_factura

    cfg = ConfiguracionSRI.get_singleton()
    if not cfg or not cfg.cert_configurado:
        messages.warning(
            request,
            f'Venta #{venta.pk} registrada pero no se pudo facturar al SRI: '
            'configura tus datos y certificado en SRI -> Configuracion.'
        )
        return None

    try:
        factura = _crear_factura_desde_venta(venta, request.user, cfg)
        return _emitir_factura(request, factura, cfg)
    except Exception:
        logger.exception('Fallo al emitir factura SRI desde venta %s', venta.pk)
        messages.warning(
            request,
            f'Venta #{venta.pk} registrada, pero la factura SRI no se pudo emitir. '
            'Puedes reintentarla desde Facturacion SRI.'
        )
        return None


def _redireccion_post_venta(venta, cfg_gen):
    response = redirect('nota_venta', pk=venta.pk)
    if cfg_gen.imprimir_auto_nota:
        response['Location'] += '?print=auto'
    return response


def _emitir_factura_pos_segura(request, venta):
    """Evita que un fallo inesperado del flujo SRI rompa el cobro del POS."""
    try:
        return _emitir_factura_si_corresponde(request, venta)
    except Exception as exc:
        logger.exception('Error inesperado cerrando la facturacion SRI para venta %s', venta.pk)
        messages.warning(
            request,
            f'Venta #{venta.pk} registrada, pero hubo un error cerrando la facturacion: '
            f'{type(exc).__name__}: {exc}'
        )
        return None


@login_required
@requiere_no_bodeguero
def procesar_venta(request):
    if request.method != 'POST':
        return redirect('pos')

    from apps.configuracion.models import ConfiguracionGeneral
    from apps.ventas.services import crear_venta_contado

    cfg_gen = ConfiguracionGeneral.get_singleton()
    tipo = request.POST.get('tipo_venta', 'contado')
    cliente_id = request.POST.get('cliente_id') or None
    items_json = request.POST.get('items_json', '[]')
    forma_pago = request.POST.get('forma_pago', 'efectivo')
    if forma_pago not in ('efectivo', 'tarjeta', 'transferencia'):
        forma_pago = 'efectivo'

    if tipo == 'contado' and not cliente_id and cfg_gen.cliente_obligatorio_venta:
        messages.error(request, 'La configuracion del sistema exige cliente en cada venta.')
        return redirect('pos')

    venta = None
    try:
        items = json.loads(items_json)
        if not items:
            messages.error(request, 'Agrega al menos un producto.')
            return redirect('pos')

        if tipo == 'apartado':
            adelanto = crear_adelanto(
                cliente_id=int(cliente_id),
                items=items,
                monto_inicial=Decimal(request.POST.get('monto_inicial', '0')),
                fecha_limite=request.POST.get('fecha_limite') or None,
                vendedor=request.user,
            )
            messages.success(request, f'Apartado #{adelanto.pk} creado.')
            return redirect('detalle_adelanto', pk=adelanto.pk)

        if tipo == 'credito':
            deuda = crear_venta_credito(
                cliente_id=int(cliente_id),
                items=items,
                plazo_dias=int(request.POST.get('plazo_dias', 30)),
                vendedor=request.user,
            )
            messages.success(request, f'Venta a credito registrada. Deuda #{deuda.pk} creada.')
            return redirect('detalle_deuda', pk=deuda.pk)

        venta = crear_venta_contado(
            items=items,
            cliente_id=cliente_id,
            vendedor=request.user,
            forma_pago=forma_pago,
            cfg_gen=cfg_gen,
        )

        respuesta_factura = _emitir_factura_pos_segura(request, venta)
        if respuesta_factura is not None:
            return respuesta_factura

        return _redireccion_post_venta(venta, cfg_gen)

    except (StockInsuficienteError, SaldoInsuficienteError, ValueError) as exc:
        messages.error(request, str(exc))
        return redirect('pos')
    except (InvalidOperation, TypeError, KeyError) as exc:
        messages.error(request, f'Hay valores invalidos en el carrito: {type(exc).__name__}: {exc}')
        return redirect('pos')
    except json.JSONDecodeError:
        messages.error(request, 'Carrito invalido. Intenta de nuevo.')
        return redirect('pos')
    except Exception as exc:
        logger.exception('Error inesperado procesando venta POS')
        if venta is not None:
            messages.warning(
                request,
                f'Venta #{venta.pk} registrada, pero hubo un error final: {type(exc).__name__}: {exc}'
            )
            return _redireccion_post_venta(venta, cfg_gen)
        messages.error(request, f'Error interno POS: {type(exc).__name__}: {exc}')
        return redirect('pos')
