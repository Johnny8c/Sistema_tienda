from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from apps.usuarios.decorators import requiere_no_bodeguero
from .models import Venta


@login_required
@requiere_no_bodeguero
def nota_venta(request, pk):
    venta = get_object_or_404(Venta, pk=pk)
    return render(request, 'ventas/nota_venta.html', {'venta': venta})
