import json
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone

from apps.usuarios.decorators import requiere_no_bodeguero, requiere_dueno
from apps.clientes.models import Cliente
from apps.inventario.models import Producto
from .models import Adelanto, Deuda, Pago
from .services import (
    crear_adelanto, registrar_abono_adelanto, completar_adelanto, cancelar_adelanto,
    crear_venta_credito, registrar_abono_deuda, saldar_deuda, condonar_deuda,
)
from .exceptions import (
    SaldoInsuficienteError, AbonoExcedeSaldoError, EstadoInvalidoError,
    StockInsuficienteError, PermisoInsuficienteError,
)


def _productos_json():
    return json.dumps([
        {
            'id': p.pk, 'nombre': p.nombre, 'talla': p.talla, 'color': p.color,
            'precio': str(p.precio), 'stock_disponible': p.stock_disponible,
            'codigo_barras': p.codigo_barras or '',
        }
        for p in Producto.objects.filter(activo=True)
    ])


# --- Adelantos ---

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
    return render(request, 'deudores/adelantos/lista.html', {
        'adelantos': qs, 'q': q, 'estado': estado, 'hoy': timezone.now().date(),
    })


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
            return render(request, 'deudores/adelantos/crear.html', {
                'clientes': clientes, 'productos': productos, 'productos_json': _productos_json(),
            })

        items = [
            {'producto_id': int(pid), 'cantidad': int(cant)}
            for pid, cant in zip(producto_ids, cantidades) if pid and int(cant) > 0
        ]
        try:
            adelanto = crear_adelanto(
                cliente_id=int(cliente_id),
                items=items,
                monto_inicial=Decimal(monto_inicial),
                fecha_limite=fecha_limite or None,
                vendedor=request.user,
            )
            messages.success(request, f'Apartado #{adelanto.pk} creado correctamente.')
            return redirect('detalle_adelanto', pk=adelanto.pk)
        except (StockInsuficienteError, SaldoInsuficienteError) as e:
            messages.error(request, str(e))

    return render(request, 'deudores/adelantos/crear.html', {
        'clientes': clientes, 'productos': productos, 'productos_json': _productos_json(),
    })


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
    monto = request.POST.get('monto', '0')
    forma_pago = request.POST.get('forma_pago', 'efectivo')
    try:
        registrar_abono_adelanto(pk, Decimal(monto), forma_pago, request.user)
        messages.success(request, f'Abono de ${monto} registrado.')
    except (AbonoExcedeSaldoError, EstadoInvalidoError) as e:
        messages.error(request, str(e))
    return redirect('detalle_adelanto', pk=pk)


@login_required
@requiere_no_bodeguero
def completar_adelanto_view(request, pk):
    if request.method != 'POST':
        return redirect('detalle_adelanto', pk=pk)
    try:
        completar_adelanto(pk, request.user)
        messages.success(request, 'Apartado completado. Venta generada.')
    except (SaldoInsuficienteError, EstadoInvalidoError) as e:
        messages.error(request, str(e))
    return redirect('detalle_adelanto', pk=pk)


@login_required
@requiere_dueno
def cancelar_adelanto_view(request, pk):
    if request.method != 'POST':
        return redirect('detalle_adelanto', pk=pk)
    motivo = request.POST.get('motivo', '')
    try:
        cancelar_adelanto(pk, motivo, request.user)
        messages.success(request, 'Apartado cancelado. Saldo transferido como crédito a favor del cliente.')
    except (EstadoInvalidoError, PermisoInsuficienteError) as e:
        messages.error(request, str(e))
    return redirect('detalle_adelanto', pk=pk)


# --- Deudas ---

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
        for d in pendientes:
            dias = (hoy - d.fecha_creacion.date()).days
            en_rango = dias >= dias_min and (dias_max is None or dias <= dias_max)
            if en_rango:
                total += d.saldo_pendiente
        return total

    return render(request, 'deudores/deudas/lista.html', {
        'deudas': qs, 'q': q, 'estado': estado,
        'bucket_0_30': bucket_sum(0, 30),
        'bucket_31_60': bucket_sum(31, 60),
        'bucket_61_90': bucket_sum(61, 90),
        'bucket_90_mas': bucket_sum(91),
    })


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
    monto = request.POST.get('monto', '0')
    forma_pago = request.POST.get('forma_pago', 'efectivo')
    try:
        registrar_abono_deuda(pk, Decimal(monto), forma_pago, request.user)
        messages.success(request, f'Abono de ${monto} registrado.')
    except (AbonoExcedeSaldoError, EstadoInvalidoError) as e:
        messages.error(request, str(e))
    return redirect('detalle_deuda', pk=pk)


@login_required
@requiere_no_bodeguero
def saldar_deuda_view(request, pk):
    if request.method != 'POST':
        return redirect('detalle_deuda', pk=pk)
    try:
        saldar_deuda(pk, request.user)
        messages.success(request, 'Deuda saldada completamente.')
    except (EstadoInvalidoError,) as e:
        messages.error(request, str(e))
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
    except (EstadoInvalidoError, PermisoInsuficienteError) as e:
        messages.error(request, str(e))
    return redirect('detalle_deuda', pk=pk)


# --- POS ---

@login_required
@requiere_no_bodeguero
def pos(request):
    clientes = Cliente.objects.filter(activo=True).order_by('nombre')
    return render(request, 'pos/index.html', {
        'clientes': clientes,
        'productos_json': _productos_json(),
    })


@login_required
@requiere_no_bodeguero
def procesar_venta(request):
    if request.method != 'POST':
        return redirect('pos')

    tipo = request.POST.get('tipo_venta', 'contado')
    cliente_id = request.POST.get('cliente_id') or None
    items_json = request.POST.get('items_json', '[]')

    try:
        items = json.loads(items_json)
        if not items:
            messages.error(request, 'Agrega al menos un producto.')
            return redirect('pos')

        if tipo == 'apartado':
            monto_inicial = Decimal(request.POST.get('monto_inicial', '0'))
            fecha_limite = request.POST.get('fecha_limite') or None
            adelanto = crear_adelanto(
                cliente_id=int(cliente_id),
                items=items,
                monto_inicial=monto_inicial,
                fecha_limite=fecha_limite,
                vendedor=request.user,
            )
            messages.success(request, f'Apartado #{adelanto.pk} creado.')
            return redirect('detalle_adelanto', pk=adelanto.pk)

        elif tipo == 'credito':
            plazo_dias = int(request.POST.get('plazo_dias', 30))
            deuda = crear_venta_credito(
                cliente_id=int(cliente_id),
                items=items,
                plazo_dias=plazo_dias,
                vendedor=request.user,
            )
            messages.success(request, f'Venta a crédito registrada. Deuda #{deuda.pk} creada.')
            return redirect('detalle_deuda', pk=deuda.pk)

        else:
            from apps.ventas.models import Venta, ItemVenta
            from apps.inventario.models import Producto as Prod
            from django.db import transaction

            with transaction.atomic():
                # Validar stock disponible (descontando reservados) antes de crear nada
                for i in items:
                    prod = Prod.objects.select_for_update().get(pk=i['producto_id'])
                    if prod.stock_disponible < i['cantidad']:
                        raise StockInsuficienteError(
                            f'"{prod.nombre}" tiene solo {prod.stock_disponible} unidades disponibles '
                            f'({prod.stock_reservado} reservadas en apartados). '
                            f'No se puede vender {i["cantidad"]}.'
                        )

                total = sum(
                    Prod.objects.get(pk=i['producto_id']).precio * i['cantidad']
                    for i in items
                )
                venta = Venta.objects.create(
                    cliente_id=int(cliente_id) if cliente_id else None,
                    tipo_pago=Venta.CONTADO,
                    total=total,
                    vendedor=request.user,
                )
                for i in items:
                    prod = Prod.objects.select_for_update().get(pk=i['producto_id'])
                    ItemVenta.objects.create(
                        venta=venta, producto=prod,
                        cantidad=i['cantidad'], precio_unitario=prod.precio,
                    )
                    prod.stock -= i['cantidad']
                    prod.save(update_fields=['stock'])

            return redirect('nota_venta', pk=venta.pk)

    except (StockInsuficienteError, SaldoInsuficienteError, ValueError) as e:
        messages.error(request, str(e))
        return redirect('pos')
