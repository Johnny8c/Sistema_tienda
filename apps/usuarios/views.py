from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum
from django.utils import timezone
from .models import Usuario
from .decorators import requiere_dueno


def vista_login(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('dashboard')
        messages.error(request, 'Usuario o contraseña incorrectos.')
    return render(request, 'usuarios/login.html')


def vista_logout(request):
    logout(request)
    return redirect('login')


@login_required
def vista_dashboard(request):
    """
    Dispatcher según rol:
    - Dueño  → dashboard global (con opción ?empleado=X para ver el de un empleado)
    - Vendedor → dashboard con sus propios datos
    - Bodeguero → dashboard de inventario
    """
    user = request.user

    # El dueño puede ver el dashboard de un empleado específico via ?empleado=X
    if user.es_dueno():
        empleado_id = request.GET.get('empleado')
        if empleado_id:
            try:
                empleado = Usuario.objects.get(pk=int(empleado_id))
                if empleado.es_vendedor():
                    return _dashboard_vendedor(request, empleado, viendo_como_dueno=True)
                if empleado.es_bodeguero():
                    return _dashboard_bodeguero(request, empleado, viendo_como_dueno=True)
            except (Usuario.DoesNotExist, ValueError):
                pass
        return _dashboard_dueno(request)

    if user.es_vendedor():
        return _dashboard_vendedor(request, user)

    if user.es_bodeguero():
        return _dashboard_bodeguero(request, user)

    return _dashboard_dueno(request)


def _empleados_seleccionables():
    """Lista de empleados que el dueño puede ver — vendedores y bodegueros activos."""
    return Usuario.objects.filter(
        is_active=True,
        rol__in=[Usuario.ROL_VENDEDOR, Usuario.ROL_BODEGUERO],
    ).order_by('rol', 'first_name', 'username')


def _agrupar_por_forma_pago(ventas_qs):
    """Devuelve [{forma, label, n, total, pct, icono, color}, ...] para gráficos."""
    from django.db.models import Sum, Count
    from decimal import Decimal
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
        label, icono, color = METAS.get(r['forma_pago'], (r['forma_pago'].title(), 'bi-currency-dollar', '#94A3B8'))
        t = r['total'] or Decimal('0')
        out.append({
            'forma': r['forma_pago'], 'label': label,
            'n': r['n'], 'total': t,
            'pct': int((t / total_general) * 100) if total_general > 0 else 0,
            'icono': icono, 'color': color,
        })
    return out


# ── DASHBOARD DUEÑO (vista global) ─────────────────────────────

def _dashboard_dueno(request):
    from datetime import timedelta
    from decimal import Decimal
    from django.db.models import Sum, Count, F
    from apps.deudores.models import Adelanto, Deuda
    from apps.ventas.models import Venta, ItemVenta
    from apps.inventario.models import Producto
    from apps.clientes.models import Cliente
    from apps.configuracion.models import ConfiguracionGeneral

    cfg = ConfiguracionGeneral.objects.first()
    stock_minimo = cfg.stock_minimo_alerta if cfg else 5

    hoy = timezone.now().date()
    inicio_mes = hoy.replace(day=1)

    ventas_hoy_qs   = Venta.objects.filter(fecha__date=hoy)
    total_ventas_hoy = ventas_hoy_qs.aggregate(t=Sum('total'))['t'] or 0
    tickets_hoy     = ventas_hoy_qs.count()
    ticket_promedio = (total_ventas_hoy / tickets_hoy) if tickets_hoy else 0

    total_ventas_mes = Venta.objects.filter(
        fecha__date__gte=inicio_mes
    ).aggregate(t=Sum('total'))['t'] or 0

    total_por_cobrar = Deuda.objects.filter(
        estado=Deuda.PENDIENTE
    ).aggregate(t=Sum('saldo_pendiente'))['t'] or 0

    adelantos_activos = Adelanto.objects.filter(estado=Adelanto.ACTIVO).count()
    total_en_adelantos = Adelanto.objects.filter(
        estado=Adelanto.ACTIVO
    ).aggregate(t=Sum('total') - Sum('saldo_pendiente'))['t'] or 0

    variantes_activas = Producto.objects.filter(activo=True)
    stock_bajo_count = variantes_activas.filter(stock__gt=0, stock__lte=stock_minimo).count()
    sin_stock_count  = variantes_activas.filter(stock=0).count()
    valor_inventario = sum((Decimal(str(v.precio)) * v.stock) for v in variantes_activas)
    total_clientes   = Cliente.objects.filter(activo=True).count()

    ventas_7d = []
    max_dia = Decimal('0')
    for i in range(6, -1, -1):
        d = hoy - timedelta(days=i)
        total_d = Venta.objects.filter(fecha__date=d).aggregate(t=Sum('total'))['t'] or Decimal('0')
        if total_d > max_dia: max_dia = total_d
        ventas_7d.append({'fecha': d, 'dia': d.strftime('%a').lower()[:3], 'total': total_d})
    for d in ventas_7d:
        d['pct'] = int((d['total'] / max_dia * 100)) if max_dia > 0 else 0

    inicio_30d = hoy - timedelta(days=30)
    top_productos = (ItemVenta.objects.filter(venta__fecha__date__gte=inicio_30d)
        .values('producto__catalogo__nombre')
        .annotate(unidades=Sum('cantidad'), ingreso=Sum(F('cantidad') * F('precio_unitario')))
        .order_by('-unidades')[:5])

    stock_critico = variantes_activas.filter(stock__gt=0, stock__lte=stock_minimo) \
        .select_related('catalogo').order_by('stock')[:6]
    top_deudores = Deuda.objects.filter(estado=Deuda.PENDIENTE) \
        .select_related('cliente').order_by('-saldo_pendiente')[:5]
    ultimas_ventas = Venta.objects.select_related('cliente', 'vendedor').order_by('-fecha')[:5]

    # Ventas de hoy agrupadas por forma de pago
    ventas_por_forma = _agrupar_por_forma_pago(ventas_hoy_qs)

    return render(request, 'usuarios/dashboard.html', {
        'total_ventas_hoy':   total_ventas_hoy,
        'tickets_hoy':        tickets_hoy,
        'ticket_promedio':    ticket_promedio,
        'total_ventas_mes':   total_ventas_mes,
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
        'adelantos_proximos': Adelanto.objects.filter(
            estado=Adelanto.ACTIVO,
            fecha_limite__lte=hoy + timedelta(days=cfg.dias_alerta_vencimiento if cfg else 7),
        ).select_related('cliente').order_by('fecha_limite')[:5],
        'stock_minimo':       stock_minimo,
        'ventas_por_forma':   ventas_por_forma,
        'empleados_disponibles': _empleados_seleccionables(),
    })


# ── DASHBOARD VENDEDOR (datos filtrados por vendedor) ──────────

def _dashboard_vendedor(request, vendedor, viendo_como_dueno=False):
    from datetime import timedelta
    from decimal import Decimal
    from django.db.models import Sum, F
    from apps.deudores.models import Adelanto, Deuda
    from apps.ventas.models import Venta, ItemVenta
    from apps.configuracion.models import ConfiguracionGeneral
    cfg = ConfiguracionGeneral.objects.first()

    hoy = timezone.now().date()
    inicio_mes = hoy.replace(day=1)

    ventas_hoy_qs    = Venta.objects.filter(vendedor=vendedor, fecha__date=hoy)
    total_ventas_hoy = ventas_hoy_qs.aggregate(t=Sum('total'))['t'] or 0
    tickets_hoy      = ventas_hoy_qs.count()
    ticket_promedio  = (total_ventas_hoy / tickets_hoy) if tickets_hoy else 0

    total_ventas_mes = Venta.objects.filter(
        vendedor=vendedor, fecha__date__gte=inicio_mes
    ).aggregate(t=Sum('total'))['t'] or 0

    total_ventas_total = Venta.objects.filter(vendedor=vendedor) \
        .aggregate(t=Sum('total'))['t'] or 0

    # Sus deudas y adelantos
    sus_deudas = Deuda.objects.filter(vendedor=vendedor, estado=Deuda.PENDIENTE)
    total_por_cobrar = sus_deudas.aggregate(t=Sum('saldo_pendiente'))['t'] or 0
    cant_deudas = sus_deudas.count()

    adelantos_activos = Adelanto.objects.filter(
        vendedor=vendedor, estado=Adelanto.ACTIVO
    ).count()

    # Ventas últimos 7 días (suyas)
    ventas_7d = []
    max_dia = Decimal('0')
    for i in range(6, -1, -1):
        d = hoy - timedelta(days=i)
        total_d = Venta.objects.filter(
            vendedor=vendedor, fecha__date=d
        ).aggregate(t=Sum('total'))['t'] or Decimal('0')
        if total_d > max_dia: max_dia = total_d
        ventas_7d.append({'fecha': d, 'dia': d.strftime('%a').lower()[:3], 'total': total_d})
    for d in ventas_7d:
        d['pct'] = int((d['total'] / max_dia * 100)) if max_dia > 0 else 0

    # Top productos que vendió
    inicio_30d = hoy - timedelta(days=30)
    top_productos = (ItemVenta.objects
        .filter(venta__vendedor=vendedor, venta__fecha__date__gte=inicio_30d)
        .values('producto__catalogo__nombre')
        .annotate(unidades=Sum('cantidad'), ingreso=Sum(F('cantidad') * F('precio_unitario')))
        .order_by('-unidades')[:5])

    # Sus últimas ventas y adelantos
    ultimas_ventas = Venta.objects.filter(vendedor=vendedor) \
        .select_related('cliente').order_by('-fecha')[:5]
    sus_top_deudores = sus_deudas.select_related('cliente').order_by('-saldo_pendiente')[:5]
    sus_apartados = Adelanto.objects.filter(
        vendedor=vendedor, estado=Adelanto.ACTIVO,
        fecha_limite__lte=hoy + timedelta(days=cfg.dias_alerta_vencimiento if cfg else 7)
    ).select_related('cliente').order_by('fecha_limite')[:5]

    # Ventas de hoy del vendedor por forma de pago
    ventas_por_forma = _agrupar_por_forma_pago(ventas_hoy_qs)

    return render(request, 'usuarios/dashboard_vendedor.html', {
        'empleado':           vendedor,
        'viendo_como_dueno':  viendo_como_dueno,
        'total_ventas_hoy':   total_ventas_hoy,
        'tickets_hoy':        tickets_hoy,
        'ticket_promedio':    ticket_promedio,
        'total_ventas_mes':   total_ventas_mes,
        'total_ventas_total': total_ventas_total,
        'total_por_cobrar':   total_por_cobrar,
        'cant_deudas':        cant_deudas,
        'adelantos_activos':  adelantos_activos,
        'ventas_7d':          ventas_7d,
        'top_productos':      top_productos,
        'ultimas_ventas':     ultimas_ventas,
        'sus_top_deudores':   sus_top_deudores,
        'sus_apartados':      sus_apartados,
        'ventas_por_forma':   ventas_por_forma,
        'empleados_disponibles': _empleados_seleccionables() if viendo_como_dueno else None,
    })


# ── DASHBOARD BODEGUERO (datos de inventario) ──────────────────

def _dashboard_bodeguero(request, bodeguero, viendo_como_dueno=False):
    from datetime import timedelta
    from decimal import Decimal
    from django.db.models import Sum, F
    from apps.ventas.models import ItemVenta
    from apps.inventario.models import Producto, CatalogoProducto
    from apps.configuracion.models import ConfiguracionGeneral

    cfg = ConfiguracionGeneral.objects.first()
    stock_minimo = cfg.stock_minimo_alerta if cfg else 5

    hoy = timezone.now().date()

    variantes_activas = Producto.objects.filter(activo=True)
    total_variantes  = variantes_activas.count()
    total_catalogo   = CatalogoProducto.objects.filter(activo=True).count()
    sin_stock_count  = variantes_activas.filter(stock=0).count()
    stock_bajo_count = variantes_activas.filter(stock__gt=0, stock__lte=stock_minimo).count()
    stock_total_unidades = variantes_activas.aggregate(t=Sum('stock'))['t'] or 0
    valor_inventario = sum((Decimal(str(v.precio)) * v.stock) for v in variantes_activas)

    # Productos sin stock (para reposición urgente)
    sin_stock = variantes_activas.filter(stock=0).select_related('catalogo')[:8]
    # Productos con stock bajo
    stock_critico = variantes_activas.filter(stock__gt=0, stock__lte=stock_minimo) \
        .select_related('catalogo').order_by('stock')[:8]

    # Top productos vendidos (qué reponer primero)
    inicio_30d = hoy - timedelta(days=30)
    top_vendidos = (ItemVenta.objects
        .filter(venta__fecha__date__gte=inicio_30d)
        .values('producto__catalogo__nombre')
        .annotate(unidades=Sum('cantidad'))
        .order_by('-unidades')[:5])

    return render(request, 'usuarios/dashboard_bodeguero.html', {
        'empleado':           bodeguero,
        'viendo_como_dueno':  viendo_como_dueno,
        'total_variantes':    total_variantes,
        'total_catalogo':     total_catalogo,
        'sin_stock_count':    sin_stock_count,
        'stock_bajo_count':   stock_bajo_count,
        'stock_total_unidades': stock_total_unidades,
        'valor_inventario':   valor_inventario,
        'sin_stock':          sin_stock,
        'stock_critico':      stock_critico,
        'top_vendidos':       top_vendidos,
        'stock_minimo':       stock_minimo,
        'empleados_disponibles': _empleados_seleccionables() if viendo_como_dueno else None,
    })


# ── Gestión de empleados (solo dueño) ─────────────────────────────────────────

@requiere_dueno
def lista_empleados(request):
    from django.db.models import Sum, Count
    empleados = (Usuario.objects.exclude(pk=request.user.pk)
                 .annotate(
                     cant_ventas=Count('venta', distinct=True),
                     total_vendido=Sum('venta__total'),
                 )
                 .order_by('rol', 'first_name', 'username'))
    return render(request, 'usuarios/empleados/lista.html', {'empleados': empleados})


@requiere_dueno
def crear_empleado(request):
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError as DjangoValidationError

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        rol = request.POST.get('rol', Usuario.ROL_VENDEDOR)
        password = request.POST.get('password', '').strip()

        errores = []
        if not username:
            errores.append('El nombre de usuario es obligatorio.')
        elif ' ' in username:
            errores.append('El usuario no puede contener espacios.')
        elif Usuario.objects.filter(username=username).exists():
            errores.append(f'El usuario "{username}" ya existe.')
        if not password:
            errores.append('La contraseña es obligatoria.')
        else:
            tmp_user = Usuario(username=username, first_name=first_name, last_name=last_name)
            try:
                validate_password(password, user=tmp_user)
            except DjangoValidationError as e:
                errores.extend(e.messages)
        if errores:
            for e in errores:
                messages.error(request, e)
            return render(request, 'usuarios/empleados/form.html', {
                'accion': 'Crear', 'roles': Usuario.ROLES,
                'f_username': username, 'f_fname': first_name,
                'f_lname': last_name, 'f_rol': rol,
            })

        Usuario.objects.create_user(
            username=username,
            first_name=first_name,
            last_name=last_name,
            password=password,
            rol=rol,
        )
        messages.success(request, f'Empleado "{username}" creado correctamente.')
        return redirect('lista_empleados')

    return render(request, 'usuarios/empleados/form.html', {
        'accion': 'Crear', 'roles': Usuario.ROLES,
        'f_username': '', 'f_fname': '', 'f_lname': '', 'f_rol': '',
    })


@requiere_dueno
def editar_empleado(request, pk):
    empleado = get_object_or_404(Usuario, pk=pk)
    if empleado == request.user:
        messages.error(request, 'No puedes editar tu propio perfil aquí.')
        return redirect('lista_empleados')

    if request.method == 'POST':
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError

        empleado.first_name = request.POST.get('first_name', '').strip()
        empleado.last_name = request.POST.get('last_name', '').strip()
        empleado.rol = request.POST.get('rol', empleado.rol)
        empleado.is_active = 'is_active' in request.POST

        nueva_password = request.POST.get('password', '').strip()
        if nueva_password:
            try:
                validate_password(nueva_password, user=empleado)
            except DjangoValidationError as e:
                for err in e.messages:
                    messages.error(request, err)
                return render(request, 'usuarios/empleados/form.html', {
                    'accion': 'Editar', 'empleado': empleado, 'roles': Usuario.ROLES,
                    'f_username': empleado.username, 'f_fname': empleado.first_name,
                    'f_lname': empleado.last_name, 'f_rol': empleado.rol,
                })
            empleado.set_password(nueva_password)

        empleado.save()
        messages.success(request, f'Empleado "{empleado.username}" actualizado.')
        return redirect('lista_empleados')

    return render(request, 'usuarios/empleados/form.html', {
        'accion': 'Editar', 'empleado': empleado, 'roles': Usuario.ROLES,
        'f_username': empleado.username, 'f_fname': empleado.first_name,
        'f_lname': empleado.last_name, 'f_rol': empleado.rol,
    })


@requiere_dueno
def toggle_empleado(request, pk):
    empleado = get_object_or_404(Usuario, pk=pk)
    if empleado == request.user:
        messages.error(request, 'No puedes desactivarte a ti mismo.')
        return redirect('lista_empleados')
    if request.method == 'POST':
        empleado.is_active = not empleado.is_active
        empleado.save()
        estado = 'activado' if empleado.is_active else 'desactivado'
        messages.success(request, f'"{empleado.username}" {estado}.')
    return redirect('lista_empleados')


@requiere_dueno
def eliminar_empleado(request, pk):
    empleado = get_object_or_404(Usuario, pk=pk)
    if empleado == request.user:
        messages.error(request, 'No puedes eliminarte a ti mismo.')
        return redirect('lista_empleados')
    if empleado.is_superuser:
        messages.error(request, 'No se puede eliminar al superusuario.')
        return redirect('lista_empleados')
    if request.method == 'POST':
        nombre = empleado.get_full_name() or empleado.username
        try:
            empleado.delete()
            messages.success(request, f'Empleado "{nombre}" eliminado correctamente.')
        except Exception:
            messages.error(
                request,
                f'No se puede eliminar a "{nombre}" porque tiene ventas u otros '
                f'registros asociados. Puedes desactivarlo en su lugar.'
            )
    return redirect('lista_empleados')
