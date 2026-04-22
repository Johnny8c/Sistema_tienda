from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from .models import Producto


@login_required
def lista_inventario(request):
    q = request.GET.get('q', '')
    productos = Producto.objects.filter(activo=True).order_by('nombre', 'talla', 'color')
    if q:
        productos = productos.filter(nombre__icontains=q)
    return render(request, 'inventario/lista.html', {'productos': productos, 'q': q})


@login_required
def crear_producto(request):
    if not request.user.es_dueno():
        messages.error(request, 'Solo el dueño puede agregar productos.')
        return redirect('lista_inventario')
    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        talla = request.POST.get('talla', '').strip()
        color = request.POST.get('color', '').strip()
        precio = request.POST.get('precio', '0')
        stock = request.POST.get('stock', '0')
        codigo = request.POST.get('codigo_barras', '').strip() or None
        if not nombre or not precio:
            messages.error(request, 'Nombre y precio son obligatorios.')
            return render(request, 'inventario/form_producto.html', {'accion': 'Agregar'})
        producto = Producto.objects.create(
            nombre=nombre, talla=talla, color=color,
            precio=precio, stock=int(stock),
            codigo_barras=codigo,
        )
        if not producto.codigo_barras:
            from .models import _generar_codigo
            producto.codigo_barras = f'TDA-{producto.id:06d}'
            producto.save(update_fields=['codigo_barras'])
        messages.success(request, f'Producto "{nombre}" agregado.')
        return redirect('lista_inventario')
    return render(request, 'inventario/form_producto.html', {'accion': 'Agregar'})


@login_required
def editar_producto(request, pk):
    if not request.user.es_dueno():
        messages.error(request, 'Solo el dueño puede editar productos.')
        return redirect('lista_inventario')
    producto = get_object_or_404(Producto, pk=pk)
    if request.method == 'POST':
        producto.nombre = request.POST.get('nombre', producto.nombre).strip()
        producto.talla = request.POST.get('talla', producto.talla).strip()
        producto.color = request.POST.get('color', producto.color).strip()
        producto.precio = request.POST.get('precio', producto.precio)
        producto.codigo_barras = request.POST.get('codigo_barras', '').strip() or None
        producto.save()
        messages.success(request, 'Producto actualizado.')
        return redirect('lista_inventario')
    return render(request, 'inventario/form_producto.html', {'accion': 'Editar', 'producto': producto})


@login_required
def ajustar_stock(request, pk):
    if not request.user.es_dueno():
        messages.error(request, 'Solo el dueño puede ajustar el stock.')
        return redirect('lista_inventario')
    producto = get_object_or_404(Producto, pk=pk)
    if request.method == 'POST':
        nuevo_stock = request.POST.get('stock', '').strip()
        if not nuevo_stock.isdigit():
            messages.error(request, 'Ingresa un número entero válido.')
        elif int(nuevo_stock) < producto.stock_reservado:
            messages.error(
                request,
                f'No puedes bajar el stock a {nuevo_stock}. '
                f'Hay {producto.stock_reservado} unidades reservadas en apartados activos.'
            )
        else:
            producto.stock = int(nuevo_stock)
            producto.save()
            messages.success(request, f'Stock actualizado a {nuevo_stock}.')
        return redirect('lista_inventario')
    return render(request, 'inventario/ajustar_stock.html', {'producto': producto})


@login_required
def desactivar_producto(request, pk):
    if not request.user.es_dueno():
        messages.error(request, 'Solo el dueño puede eliminar productos.')
        return redirect('lista_inventario')
    producto = get_object_or_404(Producto, pk=pk)
    if request.method == 'POST':
        producto.activo = False
        producto.save()
        messages.success(request, f'Producto "{producto.nombre}" desactivado.')
    return redirect('lista_inventario')


@login_required
def consultar_precio(request):
    """Página de consulta de precio por cámara (optimizada para celular)."""
    return render(request, 'inventario/consultar_precio.html')


@login_required
def api_buscar_codigo(request):
    """API JSON: devuelve info del producto dado su código de barras."""
    codigo = request.GET.get('codigo', '').strip()
    if not codigo:
        return JsonResponse({'encontrado': False})
    try:
        p = Producto.objects.get(codigo_barras=codigo, activo=True)
        return JsonResponse({
            'encontrado': True,
            'nombre': p.nombre,
            'talla': p.talla,
            'color': p.color,
            'precio': str(p.precio),
            'stock_disponible': p.stock_disponible,
            'codigo': p.codigo_barras,
        })
    except Producto.DoesNotExist:
        return JsonResponse({'encontrado': False, 'mensaje': 'Producto no encontrado'})
