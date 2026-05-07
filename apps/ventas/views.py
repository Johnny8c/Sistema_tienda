from datetime import datetime, timedelta
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Sum, Count, Q
from django.utils import timezone
from apps.usuarios.decorators import requiere_no_bodeguero
from apps.usuarios.models import Usuario
from .models import Venta


@login_required
@requiere_no_bodeguero
def nota_venta(request, pk):
    venta = get_object_or_404(Venta, pk=pk)
    # El vendedor solo puede ver sus propias notas
    if not request.user.es_dueno() and venta.vendedor_id != request.user.pk:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('No tienes permiso para ver esta venta.')
    return render(request, 'ventas/nota_venta.html', {'venta': venta})


@login_required
@requiere_no_bodeguero
def lista_ventas(request):
    """
    Lista de ventas con filtros.
    - Dueño: ve todas las ventas; puede filtrar por vendedor
    - Vendedor: ve solo sus propias ventas (forzado)
    """
    qs = Venta.objects.select_related('cliente', 'vendedor').order_by('-fecha')

    # Restricción por rol
    if not request.user.es_dueno():
        qs = qs.filter(vendedor=request.user)

    # Filtros desde GET
    fecha_desde = request.GET.get('desde', '')
    fecha_hasta = request.GET.get('hasta', '')
    tipo_pago   = request.GET.get('tipo_pago', '')
    vendedor_id = request.GET.get('vendedor', '')
    q           = request.GET.get('q', '').strip()

    if fecha_desde:
        try:
            d = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
            qs = qs.filter(fecha__date__gte=d)
        except ValueError:
            pass
    if fecha_hasta:
        try:
            d = datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
            qs = qs.filter(fecha__date__lte=d)
        except ValueError:
            pass
    if tipo_pago in ('contado', 'credito', 'adelanto_completado'):
        qs = qs.filter(tipo_pago=tipo_pago)
    if vendedor_id and request.user.es_dueno():
        qs = qs.filter(vendedor_id=vendedor_id)
    if q:
        qs = qs.filter(
            Q(cliente__nombre__icontains=q) |
            Q(cliente__cedula_ruc__icontains=q) |
            Q(pk__icontains=q)
        )

    # KPIs del filtro actual (sobre el queryset completo, antes de paginar)
    agg = qs.aggregate(total=Sum('total'), n=Count('id'))
    total_filtrado = agg['total'] or 0
    cant_filtrado  = agg['n'] or 0

    # Paginación: 50 ventas por página
    paginator = Paginator(qs, 50)
    page_obj  = paginator.get_page(request.GET.get('page'))

    # Lista de vendedores para el dropdown (solo dueño)
    vendedores = (Usuario.objects.filter(rol__in=[Usuario.ROL_VENDEDOR, Usuario.ROL_DUENO])
                  .order_by('first_name', 'username')) if request.user.es_dueno() else None

    return render(request, 'ventas/lista_ventas.html', {
        'ventas':         page_obj,           # iterable de 50, también expone .paginator y .number
        'page_obj':       page_obj,
        'total_filtrado': total_filtrado,
        'cant_filtrado':  cant_filtrado,
        'fecha_desde':    fecha_desde,
        'fecha_hasta':    fecha_hasta,
        'tipo_pago':      tipo_pago,
        'vendedor_id':    vendedor_id,
        'q':              q,
        'vendedores':     vendedores,
    })
