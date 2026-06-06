"""
Servicios de cálculo de dashboards. Extraído de views.py para mantener
las vistas delgadas y las queries probables/reutilizables.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum, Count, F
from django.utils import timezone

# Imports locales se hacen lazy para evitar ciclos en apps.


def agrupar_ventas_por_forma_pago(ventas_qs):
    """Devuelve [{forma, label, n, total, pct, icono, color}, ...] para gráficos."""
    METAS = {
        'efectivo':      ('Efectivo',           'bi-cash-coin',    '#10B981'),
        'tarjeta':       ('Tarjeta',            'bi-credit-card',  '#4F46E5'),
        'transferencia': ('QR / Transferencia', 'bi-qr-code',      '#0EA5E9'),
    }
    raw = ventas_qs.values('forma_pago').annotate(
        total=Sum('total'), n=Count('id')
    ).order_by('-total')
    total_general = sum(r['total'] or 0 for r in raw) or Decimal('1')
    out = []
    for r in raw:
        label, icono, color = METAS.get(
            r['forma_pago'],
            (r['forma_pago'].title(), 'bi-currency-dollar', '#94A3B8')
        )
        t = r['total'] or Decimal('0')
        out.append({
            'forma': r['forma_pago'], 'label': label,
            'n': r['n'], 'total': t,
            'pct': int((t / total_general) * 100) if total_general > 0 else 0,
            'icono': icono, 'color': color,
        })
    return out


def datos_dashboard_dueno():
    """Computa todos los datos para el dashboard del dueño (vista global).
    Devuelve un dict listo para pasar como contexto al template."""
    from apps.deudores.models import Adelanto, Deuda
    from apps.ventas.models import Venta, ItemVenta
    from apps.inventario.models import Producto
    from apps.clientes.models import Cliente
    from apps.configuracion.models import ConfiguracionGeneral

    cfg = ConfiguracionGeneral.objects.first()
    stock_minimo = cfg.stock_minimo_alerta if cfg else 5
    dias_alerta = cfg.dias_alerta_vencimiento if cfg else 7

    hoy = timezone.now().date()
    inicio_mes = hoy.replace(day=1)

    # Ventas hoy / mes
    ventas_hoy_qs    = Venta.objects.filter(fecha__date=hoy)
    total_ventas_hoy = ventas_hoy_qs.aggregate(t=Sum('total'))['t'] or 0
    tickets_hoy      = ventas_hoy_qs.count()
    ticket_promedio  = (total_ventas_hoy / tickets_hoy) if tickets_hoy else 0
    ventas_mes_qs    = Venta.objects.filter(fecha__date__gte=inicio_mes)
    total_ventas_mes = ventas_mes_qs.aggregate(t=Sum('total'))['t'] or 0

    # IVA cobrado (solo ventas con factura SRI autorizada). Informativo:
    # NO se suma a las ventas, que siguen en precio base.
    from apps.facturacion.reporting import iva_cobrado, total_facturado
    iva_cobrado_hoy = iva_cobrado(ventas_hoy_qs)
    iva_cobrado_mes = iva_cobrado(ventas_mes_qs)

    # Desglose facturas vs notas de venta (misma regla que iva_cobrado).
    # Cada par suma su total respectivo (mes -> total_ventas_mes, hoy -> hoy).
    facturado_mes   = total_facturado(ventas_mes_qs)
    notas_venta_mes = total_ventas_mes - facturado_mes
    facturado_hoy   = total_facturado(ventas_hoy_qs)
    notas_venta_hoy = total_ventas_hoy - facturado_hoy

    # Por cobrar / adelantos
    total_por_cobrar = (Deuda.objects.filter(estado=Deuda.PENDIENTE)
                        .aggregate(t=Sum('saldo_pendiente'))['t'] or 0)
    adelantos_activos_qs = Adelanto.objects.filter(estado=Adelanto.ACTIVO)
    adelantos_activos = adelantos_activos_qs.count()
    total_en_adelantos = (adelantos_activos_qs
                          .aggregate(t=Sum('total') - Sum('saldo_pendiente'))['t'] or 0)

    # Inventario
    variantes_activas = Producto.objects.filter(activo=True)
    stock_bajo_count = variantes_activas.filter(stock__gt=0, stock__lte=stock_minimo).count()
    sin_stock_count  = variantes_activas.filter(stock=0).count()
    valor_inventario = sum((Decimal(str(v.precio)) * v.stock) for v in variantes_activas)
    total_clientes   = Cliente.objects.filter(activo=True).count()

    # Ventas últimos 7 días (gráfico)
    ventas_7d = []
    max_dia = Decimal('0')
    for i in range(6, -1, -1):
        d = hoy - timedelta(days=i)
        total_d = Venta.objects.filter(fecha__date=d).aggregate(t=Sum('total'))['t'] or Decimal('0')
        if total_d > max_dia:
            max_dia = total_d
        ventas_7d.append({'fecha': d, 'dia': d.strftime('%a').lower()[:3], 'total': total_d})
    for d in ventas_7d:
        d['pct'] = int((d['total'] / max_dia * 100)) if max_dia > 0 else 0

    # Top productos últimos 30 días
    inicio_30d = hoy - timedelta(days=30)
    top_productos = (ItemVenta.objects
                     .filter(venta__fecha__date__gte=inicio_30d)
                     .values('producto__catalogo__nombre')
                     .annotate(
                         unidades=Sum('cantidad'),
                         ingreso=Sum(F('cantidad') * F('precio_unitario'))
                     )
                     .order_by('-unidades')[:5])

    # Listas resumen
    stock_critico = (variantes_activas
                     .filter(stock__gt=0, stock__lte=stock_minimo)
                     .select_related('catalogo')
                     .order_by('stock')[:6])
    top_deudores = (Deuda.objects.filter(estado=Deuda.PENDIENTE)
                    .select_related('cliente')
                    .order_by('-saldo_pendiente')[:5])
    ultimas_ventas = (Venta.objects
                      .select_related('cliente', 'vendedor')
                      .order_by('-fecha')[:5])
    adelantos_proximos = (Adelanto.objects.filter(
                              estado=Adelanto.ACTIVO,
                              fecha_limite__lte=hoy + timedelta(days=dias_alerta),
                          )
                          .select_related('cliente')
                          .order_by('fecha_limite')[:5])

    return {
        'total_ventas_hoy':   total_ventas_hoy,
        'tickets_hoy':        tickets_hoy,
        'ticket_promedio':    ticket_promedio,
        'total_ventas_mes':   total_ventas_mes,
        'iva_cobrado_hoy':    iva_cobrado_hoy,
        'iva_cobrado_mes':    iva_cobrado_mes,
        'facturado_mes':      facturado_mes,
        'notas_venta_mes':    notas_venta_mes,
        'facturado_hoy':      facturado_hoy,
        'notas_venta_hoy':    notas_venta_hoy,
        'total_por_cobrar':   total_por_cobrar,
        'adelantos_activos':  adelantos_activos,
        'total_en_adelantos': total_en_adelantos,
        'stock_bajo_count':   stock_bajo_count,
        'sin_stock_count':    sin_stock_count,
        'valor_inventario':   valor_inventario,
        'total_clientes':     total_clientes,
        'ventas_7d':          ventas_7d,
        'top_productos':      top_productos,
        'stock_critico':      stock_critico,
        'top_deudores':       top_deudores,
        'ultimas_ventas':     ultimas_ventas,
        'adelantos_proximos': adelantos_proximos,
        'stock_minimo':       stock_minimo,
        'ventas_por_forma':   agrupar_ventas_por_forma_pago(ventas_hoy_qs),
    }
