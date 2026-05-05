from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


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
