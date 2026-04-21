from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.usuarios.decorators import requiere_no_bodeguero
from .models import Cliente
from .services import validar_cedula_o_ruc


@login_required
@requiere_no_bodeguero
def lista_clientes(request):
    q = request.GET.get('q', '')
    clientes = Cliente.objects.filter(activo=True)
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
def detalle_cliente(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    return render(request, 'clientes/detalle.html', {'cliente': cliente})
