from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from .models import CatalogoProducto, Producto


def _form_producto_data(post=None):
    """Devuelve un dict con todas las claves esperadas por form_producto.html.
    Evita VariableDoesNotExist en Django 6 cuando el dict está vacío."""
    keys = ['nombre', 'categoria', 'precio_base', 'color', 'talla', 'precio', 'stock']
    return {k: (post.get(k, '') if post else '') for k in keys}


# ── Inventario (catálogo) ──────────────────────────────────

@login_required
def lista_inventario(request):
    q = request.GET.get('q', '')
    cat = request.GET.get('cat', '')
    catalogos = CatalogoProducto.objects.filter(activo=True).prefetch_related('variantes')
    if q:
        catalogos = catalogos.filter(nombre__icontains=q)
    if cat:
        catalogos = catalogos.filter(categoria=cat)
    categorias = CatalogoProducto.CATEGORIAS
    return render(request, 'inventario/lista.html', {
        'catalogos': catalogos, 'q': q, 'cat': cat, 'categorias': categorias,
    })


@login_required
def detalle_producto(request, pk):
    catalogo = get_object_or_404(CatalogoProducto, pk=pk, activo=True)
    variantes = catalogo.variantes.filter(activo=True).order_by('color', 'talla')
    return render(request, 'inventario/detalle_producto.html', {
        'catalogo': catalogo, 'variantes': variantes,
    })


@login_required
def crear_producto(request):
    if not request.user.puede_gestionar_inventario():
        messages.error(request, 'No tienes permiso para agregar productos.')
        return redirect('lista_inventario')

    if request.method == 'POST':
        nombre      = request.POST.get('nombre', '').strip()
        categoria   = request.POST.get('categoria', 'otro')
        descripcion = request.POST.get('descripcion', '').strip()
        precio_base = request.POST.get('precio_base', '0')
        # Primera variante
        color  = request.POST.get('color', '').strip()
        talla  = request.POST.get('talla', '').strip()
        precio = request.POST.get('precio', precio_base)
        stock  = request.POST.get('stock', '0')

        if not nombre or not precio_base:
            messages.error(request, 'Nombre y precio son obligatorios.')
            return render(request, 'inventario/form_producto.html', {
                'accion': 'Crear', 'categorias': CatalogoProducto.CATEGORIAS,
                'f': _form_producto_data(request.POST),
            })

        catalogo = CatalogoProducto.objects.create(
            nombre=nombre, categoria=categoria,
            descripcion=descripcion, precio_base=precio_base,
            foto=request.FILES.get('foto') or None,
        )

        variante = Producto.objects.create(
            catalogo=catalogo, nombre=nombre,
            color=color, talla=talla,
            precio=precio, stock=int(stock or 0),
        )
        variante.codigo_barras = f'TDA-{variante.id:06d}'
        variante.save(update_fields=['codigo_barras'])

        messages.success(request, f'Producto "{nombre}" creado con su primera variante.')
        return redirect('detalle_producto', pk=catalogo.pk)

    return render(request, 'inventario/form_producto.html', {
        'accion': 'Crear', 'categorias': CatalogoProducto.CATEGORIAS,
        'f': _form_producto_data(),
    })


@login_required
def editar_producto(request, pk):
    if not request.user.puede_gestionar_inventario():
        messages.error(request, 'No tienes permiso para editar productos.')
        return redirect('lista_inventario')

    catalogo = get_object_or_404(CatalogoProducto, pk=pk)

    if request.method == 'POST':
        catalogo.nombre      = request.POST.get('nombre', catalogo.nombre).strip()
        catalogo.categoria   = request.POST.get('categoria', catalogo.categoria)
        catalogo.descripcion = request.POST.get('descripcion', '').strip()
        catalogo.precio_base = request.POST.get('precio_base', catalogo.precio_base)
        if request.FILES.get('foto'):
            catalogo.foto = request.FILES['foto']
        catalogo.save()
        # Sincronizar nombre en variantes
        catalogo.variantes.all().update(nombre=catalogo.nombre)
        messages.success(request, 'Producto actualizado.')
        return redirect('detalle_producto', pk=catalogo.pk)

    return render(request, 'inventario/form_producto.html', {
        'accion': 'Editar', 'catalogo': catalogo,
        'categorias': CatalogoProducto.CATEGORIAS,
        'f': _form_producto_data(),
    })


@login_required
def desactivar_producto(request, pk):
    if not request.user.es_dueno():
        messages.error(request, 'Solo el dueño puede eliminar productos.')
        return redirect('lista_inventario')
    catalogo = get_object_or_404(CatalogoProducto, pk=pk)
    if request.method == 'POST':
        catalogo.activo = False
        catalogo.save()
        catalogo.variantes.all().update(activo=False)
        messages.success(request, f'Producto "{catalogo.nombre}" desactivado.')
    return redirect('lista_inventario')


# ── Variantes ─────────────────────────────────────────────

@login_required
def agregar_variante(request, catalogo_pk):
    if not request.user.puede_gestionar_inventario():
        messages.error(request, 'No tienes permiso para agregar variantes.')
        return redirect('lista_inventario')

    catalogo = get_object_or_404(CatalogoProducto, pk=catalogo_pk, activo=True)

    if request.method == 'POST':
        color  = request.POST.get('color', '').strip()
        talla  = request.POST.get('talla', '').strip()
        precio = request.POST.get('precio', str(catalogo.precio_base))
        stock  = request.POST.get('stock', '0')

        variante = Producto.objects.create(
            catalogo=catalogo, nombre=catalogo.nombre,
            color=color, talla=talla,
            precio=precio, stock=int(stock or 0),
        )
        variante.codigo_barras = f'TDA-{variante.id:06d}'
        variante.save(update_fields=['codigo_barras'])

        messages.success(request, f'Variante {color} {talla} agregada.')
        return redirect('detalle_producto', pk=catalogo.pk)

    return render(request, 'inventario/form_variante.html', {
        'accion': 'Agregar', 'catalogo': catalogo,
        'f': {'color': '', 'talla': '', 'precio': catalogo.precio_base, 'stock': ''},
    })


@login_required
def editar_variante(request, pk):
    if not request.user.puede_gestionar_inventario():
        messages.error(request, 'No tienes permiso para editar variantes.')
        return redirect('lista_inventario')

    variante = get_object_or_404(Producto, pk=pk)
    catalogo = variante.catalogo

    if request.method == 'POST':
        variante.color  = request.POST.get('color', variante.color).strip()
        variante.talla  = request.POST.get('talla', variante.talla).strip()
        variante.precio = request.POST.get('precio', variante.precio)
        variante.save()
        messages.success(request, 'Variante actualizada.')
        return redirect('detalle_producto', pk=catalogo.pk)

    return render(request, 'inventario/form_variante.html', {
        'accion': 'Editar', 'catalogo': catalogo, 'variante': variante,
        'f': {'color': '', 'talla': '', 'precio': '', 'stock': ''},
    })


@login_required
def ajustar_stock(request, pk):
    if not request.user.puede_gestionar_inventario():
        messages.error(request, 'No tienes permiso para ajustar el stock.')
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
        if producto.catalogo:
            return redirect('detalle_producto', pk=producto.catalogo.pk)
        return redirect('lista_inventario')

    return render(request, 'inventario/ajustar_stock.html', {'producto': producto})


@login_required
def desactivar_variante(request, pk):
    if not request.user.es_dueno():
        messages.error(request, 'Solo el dueño puede eliminar variantes.')
        return redirect('lista_inventario')
    variante = get_object_or_404(Producto, pk=pk)
    catalogo_pk = variante.catalogo.pk if variante.catalogo else None
    if request.method == 'POST':
        variante.activo = False
        variante.save()
        messages.success(request, 'Variante desactivada.')
    if catalogo_pk:
        return redirect('detalle_producto', pk=catalogo_pk)
    return redirect('lista_inventario')


# ── Consultar precio / API ────────────────────────────────

@login_required
def consultar_precio(request):
    return render(request, 'inventario/consultar_precio.html')


@login_required
def api_buscar_codigo(request):
    codigo = request.GET.get('codigo', '').strip()
    if not codigo:
        return JsonResponse({'encontrado': False})
    try:
        p = Producto.objects.select_related('catalogo').get(codigo_barras=codigo, activo=True)
        foto_url = ''
        if p.catalogo and p.catalogo.foto:
            try:
                foto_url = p.catalogo.foto.url
            except Exception:
                foto_url = ''
        return JsonResponse({
            'encontrado':      True,
            'nombre':          p.catalogo.nombre if p.catalogo else p.nombre,
            'talla':           p.talla,
            'color':           p.color,
            'precio':          str(p.precio),
            'stock_disponible': p.stock_disponible,
            'codigo':          p.codigo_barras,
            'foto_url':        foto_url,
        })
    except Producto.DoesNotExist:
        return JsonResponse({'encontrado': False, 'mensaje': 'Producto no encontrado'})
