from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.http import JsonResponse


def requiere_rol(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if request.user.rol not in roles:
                messages.error(request, 'No tienes permiso para acceder a esta sección.')
                return redirect('dashboard')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def requiere_dueno(view_func):
    return requiere_rol('dueno')(view_func)


def requiere_no_bodeguero(view_func):
    return requiere_rol('dueno', 'vendedor')(view_func)


def requiere_no_vendedor(view_func):
    """Dueño + bodeguero — para gestión de inventario y compras."""
    return requiere_rol('dueno', 'bodeguero')(view_func)


# ── Versión para endpoints AJAX ───────────────────────────────────────
# requiere_rol / login_required redirigen al login cuando la sesión murió.
# En una pantalla normal eso está bien, pero en un fetch() el navegador
# sigue el redirect, recibe el HTML del login y `resp.json()` revienta con
# "Unexpected token '<'". El cajero ve "Error de red" y no entiende nada.
# Estos decoradores responden JSON siempre, con el estado HTTP correcto.

def requiere_rol_api(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({
                    'ok': False,
                    'error': 'Tu sesión expiró. Recarga la página (F5) e inicia sesión de nuevo.',
                    'sesion_expirada': True,
                }, status=401)
            if request.user.rol not in roles:
                return JsonResponse({
                    'ok': False,
                    'error': 'No tienes permiso para realizar esta acción.',
                }, status=403)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def requiere_no_bodeguero_api(view_func):
    return requiere_rol_api('dueno', 'vendedor')(view_func)
