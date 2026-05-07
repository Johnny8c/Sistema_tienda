from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from apps.usuarios.decorators import requiere_no_bodeguero
from .models import Cliente
from .services import validar_cedula_o_ruc


@login_required
@requiere_no_bodeguero
def lista_clientes(request):
    from django.db.models import Sum, Count, Q
    q = request.GET.get('q', '')
    clientes = Cliente.objects.filter(activo=True).annotate(
        cant_ventas=Count('venta', distinct=True),
        total_comprado=Sum('venta__total'),
        adelantos_activos=Count('adelantos', filter=Q(adelantos__estado='activo'), distinct=True),
        deudas_pendientes=Count('deudas', filter=Q(deudas__estado='pendiente'), distinct=True),
        deuda_total=Sum('deudas__saldo_pendiente', filter=Q(deudas__estado='pendiente')),
    ).order_by('nombre')
    if q:
        clientes = clientes.filter(nombre__icontains=q) | clientes.filter(cedula_ruc__icontains=q)
    return render(request, 'clientes/lista.html', {'clientes': clientes, 'q': q})


@login_required
@requiere_no_bodeguero
def crear_cliente(request):
    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        cedula_ruc = request.POST.get('cedula_ruc', '').strip()
        telefono = request.POST.get('telefono', '').strip()
        email = request.POST.get('email', '').strip()
        direccion = request.POST.get('direccion', '').strip()

        if not nombre or not cedula_ruc:
            messages.error(request, 'Nombre y cédula/RUC son obligatorios.')
            return render(request, 'clientes/form.html', {'accion': 'Crear'})

        if not validar_cedula_o_ruc(cedula_ruc):
            messages.error(request, 'Cédula o RUC inválido.')
            return render(request, 'clientes/form.html', {'accion': 'Crear'})

        if Cliente.objects.filter(cedula_ruc=cedula_ruc).exists():
            messages.error(request, 'Ya existe un cliente con esa cédula/RUC.')
            return render(request, 'clientes/form.html', {'accion': 'Crear'})

        Cliente.objects.create(
            nombre=nombre,
            cedula_ruc=cedula_ruc,
            telefono=telefono,
            email=email,
            direccion=direccion,
        )
        messages.success(request, f'Cliente {nombre} creado correctamente.')
        return redirect('lista_clientes')

    return render(request, 'clientes/form.html', {'accion': 'Crear'})


@login_required
@requiere_no_bodeguero
def editar_cliente(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk, activo=True)
    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        telefono = request.POST.get('telefono', '').strip()
        email = request.POST.get('email', '').strip()
        direccion = request.POST.get('direccion', '').strip()

        if not nombre:
            messages.error(request, 'El nombre es obligatorio.')
            return render(request, 'clientes/form.html', {'accion': 'Editar', 'cliente': cliente})

        cliente.nombre = nombre
        cliente.telefono = telefono
        cliente.email = email
        cliente.direccion = direccion
        cliente.save()
        messages.success(request, 'Cliente actualizado.')
        return redirect('lista_clientes')

    return render(request, 'clientes/form.html', {'accion': 'Editar', 'cliente': cliente})


@login_required
@requiere_no_bodeguero
@require_POST
def api_crear_cliente(request):
    """Endpoint AJAX para crear cliente rápido desde el POS."""
    nombre     = request.POST.get('nombre', '').strip()
    cedula_ruc = request.POST.get('cedula_ruc', '').strip()
    telefono   = request.POST.get('telefono', '').strip()
    email      = request.POST.get('email', '').strip()

    if not nombre or not cedula_ruc:
        return JsonResponse({'ok': False, 'error': 'Nombre y cédula/RUC son obligatorios.'}, status=400)
    if not validar_cedula_o_ruc(cedula_ruc):
        return JsonResponse({'ok': False, 'error': 'Cédula o RUC inválido.'}, status=400)
    if Cliente.objects.filter(cedula_ruc=cedula_ruc).exists():
        return JsonResponse({'ok': False, 'error': f'Ya existe un cliente con cédula/RUC {cedula_ruc}.'}, status=400)

    cliente = Cliente.objects.create(
        nombre=nombre, cedula_ruc=cedula_ruc,
        telefono=telefono, email=email,
    )
    return JsonResponse({
        'ok':         True,
        'id':         cliente.pk,
        'nombre':     cliente.nombre,
        'cedula_ruc': cliente.cedula_ruc,
        'label':      f'{cliente.nombre} ({cliente.cedula_ruc})',
    })


@login_required
@requiere_no_bodeguero
def detalle_cliente(request, pk):
    from apps.deudores.models import Adelanto, Deuda, Pago
    from django.db.models import Sum, Q

    cliente = get_object_or_404(Cliente, pk=pk)
    adelantos = cliente.adelantos.order_by('-fecha_creacion')
    deudas = cliente.deudas.order_by('-fecha_creacion')

    ids_adelantos = list(adelantos.values_list('id', flat=True))
    ids_deudas = list(deudas.values_list('id', flat=True))
    pagos = Pago.objects.filter(
        Q(tipo=Pago.TIPO_ADELANTO, referencia_id__in=ids_adelantos) |
        Q(tipo=Pago.TIPO_DEUDA, referencia_id__in=ids_deudas)
    ).order_by('-fecha')

    ctx = {
        'cliente': cliente,
        'adelantos': adelantos,
        'deudas': deudas,
        'pagos': pagos,
        'adelantos_activos': adelantos.filter(estado=Adelanto.ACTIVO).count(),
        'total_deuda': deudas.filter(estado=Deuda.PENDIENTE).aggregate(
            t=Sum('saldo_pendiente')
        )['t'] or 0,
    }
    return render(request, 'clientes/detalle.html', ctx)
