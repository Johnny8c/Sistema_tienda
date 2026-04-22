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
    from apps.deudores.models import Adelanto, Deuda
    from apps.ventas.models import Venta

    hoy = timezone.now().date()

    ventas_hoy = Venta.objects.filter(fecha__date=hoy)
    total_ventas_hoy = ventas_hoy.aggregate(t=Sum('total'))['t'] or 0

    total_por_cobrar = Deuda.objects.filter(
        estado=Deuda.PENDIENTE
    ).aggregate(t=Sum('saldo_pendiente'))['t'] or 0

    adelantos_activos = Adelanto.objects.filter(estado=Adelanto.ACTIVO).count()

    total_en_adelantos = Adelanto.objects.filter(
        estado=Adelanto.ACTIVO
    ).aggregate(t=Sum('total') - Sum('saldo_pendiente'))['t'] or 0

    ctx = {
        'total_ventas_hoy': total_ventas_hoy,
        'total_por_cobrar': total_por_cobrar,
        'adelantos_activos': adelantos_activos,
        'total_en_adelantos': total_en_adelantos,
        'adelantos_proximos': Adelanto.objects.filter(
            estado=Adelanto.ACTIVO,
            fecha_limite__lte=hoy,
        ).select_related('cliente')[:5],
    }
    return render(request, 'usuarios/dashboard.html', ctx)


# ── Gestión de empleados (solo dueño) ─────────────────────────────────────────

@requiere_dueno
def lista_empleados(request):
    empleados = Usuario.objects.exclude(pk=request.user.pk).order_by('rol', 'username')
    return render(request, 'usuarios/empleados/lista.html', {'empleados': empleados})


@requiere_dueno
def crear_empleado(request):
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
        elif len(password) < 6:
            errores.append('La contraseña debe tener al menos 6 caracteres.')
        if errores:
            for e in errores:
                messages.error(request, e)
            return render(request, 'usuarios/empleados/form.html', {
                'accion': 'Crear', 'post': request.POST, 'roles': Usuario.ROLES
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
        'accion': 'Crear', 'roles': Usuario.ROLES
    })


@requiere_dueno
def editar_empleado(request, pk):
    empleado = get_object_or_404(Usuario, pk=pk)
    if empleado == request.user:
        messages.error(request, 'No puedes editar tu propio perfil aquí.')
        return redirect('lista_empleados')

    if request.method == 'POST':
        empleado.first_name = request.POST.get('first_name', '').strip()
        empleado.last_name = request.POST.get('last_name', '').strip()
        empleado.rol = request.POST.get('rol', empleado.rol)
        empleado.is_active = 'is_active' in request.POST
        empleado.save()

        nueva_password = request.POST.get('password', '').strip()
        if nueva_password:
            empleado.set_password(nueva_password)
            empleado.save()

        messages.success(request, f'Empleado "{empleado.username}" actualizado.')
        return redirect('lista_empleados')

    return render(request, 'usuarios/empleados/form.html', {
        'accion': 'Editar', 'empleado': empleado, 'roles': Usuario.ROLES
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
