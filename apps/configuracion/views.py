from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash

from apps.usuarios.decorators import requiere_dueno
from .models import ConfiguracionGeneral


@login_required
@requiere_dueno
def panel(request):
    """Panel central de configuración."""
    cfg = ConfiguracionGeneral.get_singleton()
    return render(request, 'configuracion/panel.html', {'cfg': cfg})


@login_required
@requiere_dueno
def datos_negocio(request):
    cfg = ConfiguracionGeneral.get_singleton()

    if request.method == 'POST':
        cfg.nombre_negocio     = request.POST.get('nombre_negocio', '').strip() or 'Sistema Tienda'
        cfg.slogan             = request.POST.get('slogan', '').strip()
        cfg.direccion          = request.POST.get('direccion', '').strip()
        cfg.telefono           = request.POST.get('telefono', '').strip()
        cfg.email              = request.POST.get('email', '').strip()
        cfg.sitio_web          = request.POST.get('sitio_web', '').strip()
        cfg.mensaje_nota_venta = request.POST.get('mensaje_nota_venta', '').strip()
        if request.FILES.get('logo'):
            cfg.logo = request.FILES['logo']
        cfg.save()
        messages.success(request, 'Datos del negocio actualizados.')
        return redirect('config_datos_negocio')

    return render(request, 'configuracion/datos_negocio.html', {'cfg': cfg})


@login_required
@requiere_dueno
def preferencias(request):
    cfg = ConfiguracionGeneral.get_singleton()

    if request.method == 'POST':
        try:
            cfg.stock_minimo_alerta = max(0, int(request.POST.get('stock_minimo_alerta', 5)))
            cfg.dias_alerta_vencimiento = max(0, int(request.POST.get('dias_alerta_vencimiento', 7)))
            cfg.save()
            messages.success(request, 'Preferencias guardadas.')
        except ValueError:
            messages.error(request, 'Valores inválidos. Ingresa números enteros.')
        return redirect('config_preferencias')

    return render(request, 'configuracion/preferencias.html', {'cfg': cfg})


@login_required
def mi_cuenta(request):
    """Editar perfil propio + cambiar contraseña. Disponible para todos los roles."""
    user = request.user

    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion == 'perfil':
            user.first_name = request.POST.get('first_name', '').strip()
            user.last_name  = request.POST.get('last_name', '').strip()
            user.save(update_fields=['first_name', 'last_name'])
            messages.success(request, 'Perfil actualizado.')

        elif accion == 'password':
            actual = request.POST.get('password_actual', '')
            nueva  = request.POST.get('password_nueva', '')
            confirma = request.POST.get('password_confirma', '')

            if not user.check_password(actual):
                messages.error(request, 'La contraseña actual es incorrecta.')
            elif len(nueva) < 6:
                messages.error(request, 'La nueva contraseña debe tener al menos 6 caracteres.')
            elif nueva != confirma:
                messages.error(request, 'Las contraseñas no coinciden.')
            else:
                user.set_password(nueva)
                user.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'Contraseña actualizada correctamente.')

        return redirect('config_mi_cuenta')

    return render(request, 'configuracion/mi_cuenta.html', {})
