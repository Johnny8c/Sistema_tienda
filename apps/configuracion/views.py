import logging
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash

from apps.usuarios.decorators import requiere_dueno
from .models import ConfiguracionGeneral

logger = logging.getLogger(__name__)


@login_required
@requiere_dueno
def panel(request):
    """Panel central de configuración."""
    cfg = ConfiguracionGeneral.get_singleton()
    return render(request, 'configuracion/panel.html', {'cfg': cfg})


@login_required
@requiere_dueno
def datos_negocio(request):
    import re
    cfg = ConfiguracionGeneral.get_singleton()

    if request.method == 'GET' and cfg.logo:
        try:
            if not cfg.logo.storage.exists(cfg.logo.name):
                logger.warning('Logo huérfano detectado (%s). Limpiando referencia.', cfg.logo.name)
                cfg.logo = None
                cfg.save(update_fields=['logo'])
        except Exception:
            logger.exception('No se pudo verificar la existencia del logo')

    if request.method == 'POST':
        cfg.nombre_negocio     = request.POST.get('nombre_negocio', '').strip() or 'Sistema Tienda'
        cfg.slogan             = request.POST.get('slogan', '').strip()
        cfg.direccion          = request.POST.get('direccion', '').strip()
        cfg.telefono           = request.POST.get('telefono', '').strip()
        cfg.email              = request.POST.get('email', '').strip()
        cfg.sitio_web          = request.POST.get('sitio_web', '').strip()
        cfg.mensaje_nota_venta = request.POST.get('mensaje_nota_venta', '').strip()

        color = (request.POST.get('color_primario', '') or '').strip().upper()
        if re.match(r'^#[0-9A-F]{6}$', color):
            cfg.color_primario = color

        if request.POST.get('quitar_logo') == '1' and cfg.logo:
            cfg.logo.delete(save=False)
            cfg.logo = None
        nuevo_logo = request.FILES.get('logo')
        if nuevo_logo:
            # Limite duro de 5 MB: ya viene comprimido por el JS del cliente,
            # esto cubre el caso de un atacante saltandose el navegador.
            if nuevo_logo.size > 5 * 1024 * 1024:
                messages.error(request, 'El logo no puede pesar más de 5 MB.')
                return redirect('config_datos_negocio')
            if not (nuevo_logo.content_type or '').startswith('image/'):
                messages.error(request, 'El logo debe ser una imagen.')
                return redirect('config_datos_negocio')
            cfg.logo = nuevo_logo
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

            # Booleanos (checkbox -> presente/ausente en POST)
            cfg.permitir_vender_sin_stock = request.POST.get('permitir_vender_sin_stock') == 'on'
            cfg.cliente_obligatorio_venta = request.POST.get('cliente_obligatorio_venta') == 'on'
            cfg.sonido_escaneo            = request.POST.get('sonido_escaneo') == 'on'
            cfg.imprimir_auto_nota        = request.POST.get('imprimir_auto_nota') == 'on'
            cfg.mostrar_logo_en_nota      = request.POST.get('mostrar_logo_en_nota') == 'on'
            cfg.mostrar_vendedor_en_nota  = request.POST.get('mostrar_vendedor_en_nota') == 'on'

            modo = request.POST.get('precio_fuera_rango_modo', 'advertir')
            if modo in dict(ConfiguracionGeneral.PRECIO_RANGO_OPCIONES):
                cfg.precio_fuera_rango_modo = modo

            cfg.save()
            messages.success(request, 'Preferencias guardadas.')
        except ValueError:
            messages.error(request, 'Valores inválidos. Ingresa números enteros.')
        return redirect('config_preferencias')

    return render(request, 'configuracion/preferencias.html', {'cfg': cfg})


@login_required
def mi_cuenta(request):
    """Editar perfil propio + cambiar contraseña. Disponible para todos los roles."""
    from django.db.models import Sum, Count
    user = request.user

    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion == 'perfil':
            user.first_name = request.POST.get('first_name', '').strip()
            user.last_name  = request.POST.get('last_name', '').strip()
            user.save(update_fields=['first_name', 'last_name'])
            messages.success(request, 'Perfil actualizado.')

        elif accion == 'password':
            from django.contrib.auth.password_validation import validate_password
            from django.core.exceptions import ValidationError as DjangoValidationError

            actual = request.POST.get('password_actual', '')
            nueva  = request.POST.get('password_nueva', '')
            confirma = request.POST.get('password_confirma', '')

            if not user.check_password(actual):
                messages.error(request, 'La contraseña actual es incorrecta.')
            elif nueva != confirma:
                messages.error(request, 'Las contraseñas no coinciden.')
            elif nueva == actual:
                messages.error(request, 'La nueva contraseña no puede ser igual a la actual.')
            else:
                try:
                    validate_password(nueva, user=user)
                except DjangoValidationError as e:
                    for err in e.messages:
                        messages.error(request, err)
                else:
                    user.set_password(nueva)
                    user.save()
                    update_session_auth_hash(request, user)
                    messages.success(request, 'Contraseña actualizada correctamente.')

        return redirect('config_mi_cuenta')

    # Estadísticas de actividad según rol
    stats = {}
    try:
        from apps.ventas.models import Venta
        agg_ventas = Venta.objects.filter(vendedor=user).aggregate(
            cnt=Count('id'), total=Sum('total')
        )
        stats['ventas_count'] = agg_ventas['cnt'] or 0
        stats['ventas_total'] = agg_ventas['total'] or 0
    except Exception:
        logger.exception('No se pudieron calcular stats de ventas para %s', user.username)
        stats['ventas_count'] = 0
        stats['ventas_total'] = 0

    try:
        from apps.proveedores.models import Compra
        agg_compras = Compra.objects.filter(registrado_por=user).aggregate(
            cnt=Count('id'), total=Sum('total')
        )
        stats['compras_count'] = agg_compras['cnt'] or 0
        stats['compras_total'] = agg_compras['total'] or 0
    except Exception:
        logger.exception('No se pudieron calcular stats de compras para %s', user.username)
        stats['compras_count'] = 0
        stats['compras_total'] = 0

    return render(request, 'configuracion/mi_cuenta.html', {'stats': stats})
