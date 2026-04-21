from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Sum
from django.utils import timezone


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
