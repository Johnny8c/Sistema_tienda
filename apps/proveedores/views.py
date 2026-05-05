import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from apps.usuarios.decorators import requiere_dueno, requiere_no_vendedor
from apps.inventario.models import Producto
from .models import Proveedor, Compra, ItemCompra


# ── Proveedores ───────────────────────────────────────────────────────────────

@requiere_no_vendedor
def lista_proveedores(request):
    proveedores = Proveedor.objects.filter(activo=True)
    return render(request, 'proveedores/lista.html', {'proveedores': proveedores})


@requiere_dueno
def crear_proveedor(request):
    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        if not nombre:
            messages.error(request, 'El nombre es obligatorio.')
            return render(request, 'proveedores/form_proveedor.html', {'accion': 'Crear', 'post': request.POST})
        Proveedor.objects.create(
            nombre=nombre,
            ruc=request.POST.get('ruc', '').strip(),
            telefono=request.POST.get('telefono', '').strip(),
            email=request.POST.get('email', '').strip(),
            direccion=request.POST.get('direccion', '').strip(),
            contacto=request.POST.get('contacto', '').strip(),
        )
        messages.success(request, f'Proveedor "{nombre}" creado.')
        return redirect('lista_proveedores')
    return render(request, 'proveedores/form_proveedor.html', {'accion': 'Crear'})


@requiere_dueno
def editar_proveedor(request, pk):
    proveedor = get_object_or_404(Proveedor, pk=pk)
    if request.method == 'POST':
        proveedor.nombre = request.POST.get('nombre', proveedor.nombre).strip()
        proveedor.ruc = request.POST.get('ruc', '').strip()
        proveedor.telefono = request.POST.get('telefono', '').strip()
        proveedor.email = request.POST.get('email', '').strip()
        proveedor.direccion = request.POST.get('direccion', '').strip()
        proveedor.contacto = request.POST.get('contacto', '').strip()
        proveedor.save()
        messages.success(request, 'Proveedor actualizado.')
        return redirect('lista_proveedores')
    return render(request, 'proveedores/form_proveedor.html', {'accion': 'Editar', 'proveedor': proveedor})


# ── Compras ───────────────────────────────────────────────────────────────────

@requiere_no_vendedor
def lista_compras(request):
    compras = Compra.objects.select_related('proveedor', 'registrado_por').all()
    return render(request, 'proveedores/lista_compras.html', {'compras': compras})


@requiere_no_vendedor
def crear_compra(request):
    proveedores = Proveedor.objects.filter(activo=True)
    productos = Producto.objects.filter(activo=True).order_by('nombre')
    productos_json = json.dumps([
        {'id': p.id, 'nombre': str(p), 'precio': str(p.precio)}
        for p in productos
    ])

    if request.method == 'POST':
        proveedor_id = request.POST.get('proveedor_id')
        fecha = request.POST.get('fecha')
        numero_factura = request.POST.get('numero_factura', '').strip()
        notas = request.POST.get('notas', '').strip()
        items_json = request.POST.get('items_json', '[]')
        estado = request.POST.get('estado', Compra.PENDIENTE)

        try:
            items = json.loads(items_json)
            if not items:
                messages.error(request, 'Agrega al menos un producto.')
                return render(request, 'proveedores/form_compra.html', {
                    'proveedores': proveedores, 'productos_json': productos_json, 'post': request.POST
                })

            # Validar items antes de abrir transacción
            errores = []
            for item in items:
                cantidad = int(item.get('cantidad', 0))
                precio = Decimal(str(item.get('precio_unitario', 0)))
                if cantidad <= 0:
                    errores.append('La cantidad debe ser mayor a 0.')
                if precio <= 0:
                    errores.append('El precio unitario debe ser mayor a 0.')
            if errores:
                for e in errores:
                    messages.error(request, e)
                return render(request, 'proveedores/form_compra.html', {
                    'proveedores': proveedores, 'productos_json': productos_json,
                })

            with transaction.atomic():
                compra = Compra.objects.create(
                    proveedor_id=int(proveedor_id),
                    fecha=fecha,
                    numero_factura=numero_factura,
                    notas=notas,
                    estado=estado,
                    registrado_por=request.user,
                    total=0,
                )
                total = Decimal('0')
                for item in items:
                    prod = Producto.objects.select_for_update().get(pk=item['producto_id'])
                    cantidad = int(item['cantidad'])
                    precio = Decimal(str(item['precio_unitario']))
                    ItemCompra.objects.create(
                        compra=compra, producto=prod,
                        cantidad=cantidad, precio_unitario=precio,
                    )
                    prod.stock += cantidad
                    prod.save(update_fields=['stock'])
                    total += precio * cantidad

                compra.total = total
                compra.save(update_fields=['total'])

            messages.success(request, f'Compra #{compra.pk} registrada. Stock actualizado.')
            return redirect('lista_compras')

        except Exception as e:
            messages.error(request, f'Error al registrar: {e}')

    return render(request, 'proveedores/form_compra.html', {
        'proveedores': proveedores, 'productos_json': productos_json,
    })


@requiere_no_vendedor
def detalle_compra(request, pk):
    compra = get_object_or_404(Compra, pk=pk)
    return render(request, 'proveedores/detalle_compra.html', {'compra': compra})


@requiere_dueno
def marcar_pagada(request, pk):
    compra = get_object_or_404(Compra, pk=pk)
    if request.method == 'POST':
        compra.estado = Compra.PAGADA
        compra.save(update_fields=['estado'])
        messages.success(request, f'Compra #{pk} marcada como pagada.')
    return redirect('detalle_compra', pk=pk)
