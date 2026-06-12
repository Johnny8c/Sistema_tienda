from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q
from django.shortcuts import render
from django.utils import timezone

from apps.usuarios.decorators import requiere_dueno
from apps.deudores.models import Adelanto, Deuda, Pago
from apps.ventas.models import Venta


def _hoy():
    # localdate() = fecha en America/Guayaquil. Con now().date() (UTC), después
    # de las 19:00 de Ecuador "hoy" ya era mañana y los reportes del día
    # salían vacíos o con las ventas de la noche en el día equivocado.
    return timezone.localdate()


def _buckets_antiguedad(deudas_pendientes):
    hoy = _hoy()
    buckets = {'0-30': [], '31-60': [], '61-90': [], '90+': []}
    totales = {'0-30': Decimal('0'), '31-60': Decimal('0'), '61-90': Decimal('0'), '90+': Decimal('0')}

    for d in deudas_pendientes:
        dias = (hoy - d.fecha_creacion.date()).days
        if dias <= 30:
            key = '0-30'
        elif dias <= 60:
            key = '31-60'
        elif dias <= 90:
            key = '61-90'
        else:
            key = '90+'
        buckets[key].append(d)
        totales[key] += d.saldo_pendiente

    return buckets, totales


@login_required
@requiere_dueno
def index_reportes(request):
    return render(request, 'reportes/index.html')


@login_required
@requiere_dueno
def antiguedad_cartera(request):
    deudas = Deuda.objects.filter(
        estado=Deuda.PENDIENTE
    ).select_related('cliente').order_by('fecha_creacion')

    buckets, totales = _buckets_antiguedad(deudas)
    total_general = sum(totales.values())

    buckets_meta = [
        ('0-30',  'success', '0–30 días'),
        ('31-60', 'warning', '31–60 días'),
        ('61-90', 'orange',  '61–90 días'),
        ('90+',   'danger',  '90+ días'),
    ]
    ctx = {
        'buckets': buckets,
        'totales': totales,
        'total_general': total_general,
        'buckets_meta': buckets_meta,
        'hoy': _hoy(),
    }
    return render(request, 'reportes/antiguedad_cartera.html', ctx)


@login_required
@requiere_dueno
def adelantos_por_vencer(request):
    from datetime import timedelta
    from apps.configuracion.models import ConfiguracionGeneral
    cfg = ConfiguracionGeneral.objects.first()
    dias_alerta = cfg.dias_alerta_vencimiento if cfg else 7

    hoy = _hoy()
    limite_proximo = hoy + timedelta(days=dias_alerta)

    adelantos = Adelanto.objects.filter(
        estado=Adelanto.ACTIVO
    ).select_related('cliente', 'vendedor').order_by('fecha_limite')

    vencidos = [a for a in adelantos if a.fecha_limite and a.fecha_limite < hoy]
    proximos = [a for a in adelantos
                if a.fecha_limite and hoy <= a.fecha_limite <= limite_proximo]
    mas_lejanos = [a for a in adelantos
                   if a.fecha_limite and a.fecha_limite > limite_proximo]
    sin_fecha = [a for a in adelantos if not a.fecha_limite]

    total_saldo = adelantos.aggregate(t=Sum('saldo_pendiente'))['t'] or Decimal('0')
    total_recibido = sum(
        (a.total - a.saldo_pendiente) for a in adelantos
    )

    ctx = {
        'vencidos': vencidos,
        'proximos': proximos,
        'mas_lejanos': mas_lejanos,
        'sin_fecha': sin_fecha,
        'total_saldo': total_saldo,
        'total_recibido': total_recibido,
        'hoy': hoy,
        'dias_alerta': dias_alerta,
    }
    return render(request, 'reportes/adelantos_por_vencer.html', ctx)


@login_required
@requiere_dueno
def top_deudores(request):
    top = (
        Deuda.objects
        .filter(estado=Deuda.PENDIENTE)
        .values('cliente__id', 'cliente__nombre', 'cliente__cedula_ruc', 'cliente__telefono')
        .annotate(total_deuda=Sum('saldo_pendiente'), num_deudas=Count('id'))
        .order_by('-total_deuda')[:20]
    )
    total_cartera = Deuda.objects.filter(
        estado=Deuda.PENDIENTE
    ).aggregate(t=Sum('saldo_pendiente'))['t'] or Decimal('0')

    ctx = {'top': top, 'total_cartera': total_cartera}
    return render(request, 'reportes/top_deudores.html', ctx)


@login_required
@requiere_dueno
def cierre_caja(request):
    fecha_str = request.GET.get('fecha', str(_hoy()))
    try:
        from datetime import date
        fecha = date.fromisoformat(fecha_str)
    except ValueError:
        fecha = _hoy()

    ventas_contado = Venta.objects.filter(
        fecha__date=fecha, tipo_pago=Venta.CONTADO
    ).select_related('vendedor')

    # Solo abonos POSITIVOS son ingresos. Los negativos (reembolsos) se separan.
    abonos_adelanto = Pago.objects.filter(
        tipo=Pago.TIPO_ADELANTO, fecha__date=fecha, monto__gt=0
    ).select_related('vendedor')
    abonos_deuda = Pago.objects.filter(
        tipo=Pago.TIPO_DEUDA, fecha__date=fecha, monto__gt=0
    ).select_related('vendedor')
    reembolsos = Pago.objects.filter(
        fecha__date=fecha, monto__lt=0
    ).select_related('vendedor')

    from apps.facturacion.reporting import iva_cobrado
    from apps.facturacion.models import FacturaSRI
    total_contado = ventas_contado.aggregate(t=Sum('total'))['t'] or Decimal('0')
    # IVA cobrado del día (solo ventas contado con factura SRI autorizada).
    # No entra en total_dia: el efectivo en caja es el base; el IVA se
    # informa aparte para conciliación tributaria.
    total_iva_cobrado = iva_cobrado(ventas_contado)

    # Desglose del contado: cuánto se vendió con factura SRI autorizada vs
    # nota de venta (misma definición de "facturado" que iva_cobrado). Las
    # facturas pendientes/contingencia aún cuentan como nota hasta autorizarse.
    total_facturado = ventas_contado.aggregate(
        t=Sum('total', filter=Q(factura_sri__estado=FacturaSRI.AUTORIZADA))
    )['t'] or Decimal('0')
    total_notas_venta = total_contado - total_facturado
    num_facturado = ventas_contado.filter(
        factura_sri__estado=FacturaSRI.AUTORIZADA
    ).count()
    num_notas = ventas_contado.count() - num_facturado
    total_abonos_adelanto = abonos_adelanto.aggregate(t=Sum('monto'))['t'] or Decimal('0')
    total_abonos_deuda = abonos_deuda.aggregate(t=Sum('monto'))['t'] or Decimal('0')
    total_reembolsos = reembolsos.aggregate(t=Sum('monto'))['t'] or Decimal('0')   # negativo
    total_dia = total_contado + total_abonos_adelanto + total_abonos_deuda + total_reembolsos

    # Desglose por vendedor
    def por_vendedor(qs, campo_monto):
        resultado = {}
        for item in qs:
            nombre = item.vendedor.get_full_name() or item.vendedor.username
            monto = getattr(item, campo_monto)
            resultado[nombre] = resultado.get(nombre, Decimal('0')) + monto
        return resultado

    ctx = {
        'fecha': fecha,
        'ventas_contado': ventas_contado,
        'abonos_adelanto': abonos_adelanto,
        'abonos_deuda': abonos_deuda,
        'reembolsos': reembolsos,
        'total_contado': total_contado,
        'total_abonos_adelanto': total_abonos_adelanto,
        'total_abonos_deuda': total_abonos_deuda,
        'total_reembolsos': total_reembolsos,
        'total_dia': total_dia,
        'total_iva_cobrado': total_iva_cobrado,
        'total_facturado': total_facturado,
        'total_notas_venta': total_notas_venta,
        'num_facturado': num_facturado,
        'num_notas': num_notas,
        'ventas_por_vendedor': por_vendedor(ventas_contado, 'total'),
        'abonos_por_vendedor': {
            k: v for k, v in {
                **{k: v for k, v in por_vendedor(abonos_adelanto, 'monto').items()},
            }.items()
        },
    }
    return render(request, 'reportes/cierre_caja.html', ctx)
