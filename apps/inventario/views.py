import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import CatalogoProducto, Producto

logger = logging.getLogger(__name__)


def _form_producto_data(post=None):
    """Devuelve un dict con todas las claves esperadas por form_producto.html.
    Evita VariableDoesNotExist en Django 6 cuando el dict está vacío."""
    keys = ['nombre', 'categoria', 'precio_base', 'precio_minimo', 'precio_maximo',
            'color', 'talla', 'precio', 'stock']
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

    catalogos = list(catalogos)
    for c in catalogos:
        activas = [v for v in c.variantes.all() if v.activo]
        c.tallas_unicas = list(dict.fromkeys(v.talla for v in activas if v.talla))
        c.colores_unicos = list(dict.fromkeys(v.color for v in activas if v.color))

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
        from decimal import Decimal, InvalidOperation
        nombre      = request.POST.get('nombre', '').strip()
        categoria   = request.POST.get('categoria', 'otro')
        descripcion = request.POST.get('descripcion', '').strip()
        precio_min  = (request.POST.get('precio_minimo', '') or '').strip()
        precio_max  = (request.POST.get('precio_maximo', '') or '').strip()
        # Primera variante
        color  = request.POST.get('color', '').strip()
        talla  = request.POST.get('talla', '').strip()
        stock  = (request.POST.get('stock', '') or '').strip() or '0'

        # Validaciones
        if not nombre:
            messages.error(request, 'El nombre es obligatorio.')
            return render(request, 'inventario/form_producto.html', {
                'accion': 'Crear', 'categorias': CatalogoProducto.CATEGORIAS,
                'f': _form_producto_data(request.POST),
            })
        try:
            pmin = Decimal(precio_min) if precio_min else None
            pmax = Decimal(precio_max) if precio_max else None
        except InvalidOperation:
            messages.error(request, 'Los precios deben ser números válidos.')
            return render(request, 'inventario/form_producto.html', {
                'accion': 'Crear', 'categorias': CatalogoProducto.CATEGORIAS,
                'f': _form_producto_data(request.POST),
            })
        if pmin is None or pmax is None:
            messages.error(request, 'Debes ingresar precio mínimo y máximo.')
            return render(request, 'inventario/form_producto.html', {
                'accion': 'Crear', 'categorias': CatalogoProducto.CATEGORIAS,
                'f': _form_producto_data(request.POST),
            })
        if pmin > pmax:
            messages.error(request, 'El precio mínimo no puede ser mayor al máximo.')
            return render(request, 'inventario/form_producto.html', {
                'accion': 'Crear', 'categorias': CatalogoProducto.CATEGORIAS,
                'f': _form_producto_data(request.POST),
            })

        # precio_base = promedio del rango (uso interno)
        pb = ((pmin + pmax) / 2).quantize(Decimal('0.01'))

        # Precio inicial de la variante = precio mínimo (o lo que el form mande)
        precio_var = (request.POST.get('precio', '') or '').strip() or str(pmin)

        catalogo = CatalogoProducto.objects.create(
            nombre=nombre, categoria=categoria,
            descripcion=descripcion, precio_base=pb,
            precio_minimo=pmin, precio_maximo=pmax,
            foto=request.FILES.get('foto') or None,
        )

        variante = Producto.objects.create(
            catalogo=catalogo, nombre=nombre,
            color=color, talla=talla,
            precio=precio_var, stock=int(stock or 0),
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
        from decimal import Decimal, InvalidOperation
        catalogo.descripcion = request.POST.get('descripcion', '').strip()
        pmin_str = (request.POST.get('precio_minimo', '') or '').strip()
        pmax_str = (request.POST.get('precio_maximo', '') or '').strip()
        try:
            pmin = Decimal(pmin_str) if pmin_str else None
            pmax = Decimal(pmax_str) if pmax_str else None
        except InvalidOperation:
            messages.error(request, 'Los precios deben ser números válidos.')
            return redirect('editar_producto', pk=catalogo.pk)
        if pmin is None or pmax is None:
            messages.error(request, 'Debes ingresar precio mínimo y máximo.')
            return redirect('editar_producto', pk=catalogo.pk)
        if pmin > pmax:
            messages.error(request, 'El precio mínimo no puede ser mayor al máximo.')
            return redirect('editar_producto', pk=catalogo.pk)
        catalogo.precio_minimo = pmin
        catalogo.precio_maximo = pmax
        catalogo.precio_base = ((pmin + pmax) / 2).quantize(Decimal('0.01'))
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
@require_POST
def desactivar_producto(request, pk):
    if not request.user.es_dueno():
        messages.error(request, 'Solo el dueño puede eliminar productos.')
        return redirect('lista_inventario')
    catalogo = get_object_or_404(CatalogoProducto, pk=pk)
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
        precio = (request.POST.get('precio', '') or '').strip() or str(catalogo.precio_base)
        stock  = (request.POST.get('stock', '') or '').strip() or '0'

        variante = Producto.objects.create(
            catalogo=catalogo, nombre=catalogo.nombre,
            color=color, talla=talla,
            precio=precio, stock=int(stock),
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
        nuevo_precio = (request.POST.get('precio', '') or '').strip()
        if nuevo_precio:
            variante.precio = nuevo_precio
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
@require_POST
def desactivar_variante(request, pk):
    if not request.user.es_dueno():
        messages.error(request, 'Solo el dueño puede eliminar variantes.')
        return redirect('lista_inventario')
    variante = get_object_or_404(Producto, pk=pk)
    catalogo_pk = variante.catalogo.pk if variante.catalogo else None
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

    # Normalización para tolerar desfase de layout en lectores USB (ES vs US):
    # los apóstrofes y comillas se interpretan a veces como guion.
    def _norm(s):
        if not s:
            return ''
        return (s.replace("'", '-')
                 .replace('´', '-')
                 .replace('`', '-')
                 .upper().strip())

    codigo_norm = _norm(codigo)

    try:
        # 1) Match exacto
        try:
            p = Producto.objects.select_related('catalogo').get(codigo_barras=codigo, activo=True)
        except Producto.DoesNotExist:
            # 2) Match normalizado: buscar entre productos activos
            p = None
            for prod in Producto.objects.select_related('catalogo').filter(activo=True).exclude(codigo_barras__isnull=True).exclude(codigo_barras=''):
                if _norm(prod.codigo_barras) == codigo_norm:
                    p = prod
                    break
            if p is None:
                raise Producto.DoesNotExist
        foto_url = ''
        if p.catalogo and p.catalogo.foto:
            try:
                foto_url = p.catalogo.foto.url
            except Exception:
                logger.exception('No se pudo resolver foto.url del producto %s', p.pk)
                foto_url = ''
        cat = p.catalogo
        return JsonResponse({
            'encontrado':      True,
            'nombre':          cat.nombre if cat else p.nombre,
            'categoria':       cat.get_categoria_display() if cat else '',
            'talla':           p.talla,
            'color':           p.color,
            'precio':          str(p.precio),
            'precio_minimo':   str(cat.precio_minimo) if cat and cat.precio_minimo is not None else None,
            'precio_maximo':   str(cat.precio_maximo) if cat and cat.precio_maximo is not None else None,
            'stock':           p.stock,
            'stock_reservado': p.stock_reservado,
            'stock_disponible': p.stock_disponible,
            'codigo':          p.codigo_barras,
            'foto_url':        foto_url,
            'catalogo_id':     cat.pk if cat else None,
            'producto_id':     p.pk,
        })
    except Producto.DoesNotExist:
        return JsonResponse({'encontrado': False, 'mensaje': 'Producto no encontrado'})


# ── Etiquetas pegables ────────────────────────────────────────

@login_required
def imprimir_etiquetas(request):
    """Página para configurar e imprimir lotes de etiquetas pegables.
    Genera vista previa de N copias por variante con código de barras."""
    import json
    from apps.configuracion.models import ConfiguracionGeneral

    if not request.user.puede_gestionar_inventario():
        messages.error(request, 'No tienes permiso para imprimir etiquetas.')
        return redirect('lista_inventario')

    cfg = ConfiguracionGeneral.get_singleton()

    # Pre-selección desde querystring: ?producto=<catalogo_pk>
    producto_id = request.GET.get('producto')
    variante_id = request.GET.get('variante')

    productos = (Producto.objects.filter(activo=True)
                 .select_related('catalogo')
                 .order_by('catalogo__nombre', 'talla', 'color'))

    productos_data = []
    for p in productos:
        productos_data.append({
            'id': p.pk,
            'catalogo_id': p.catalogo_id,
            'nombre': p.catalogo.nombre if p.catalogo else p.nombre,
            'categoria': p.catalogo.get_categoria_display() if p.catalogo else '',
            'talla': p.talla,
            'color': p.color,
            'precio': str(p.precio),
            'stock': p.stock,
            'stock_disponible': p.stock_disponible,
            'codigo_barras': p.codigo_barras or '',
        })

    logo_url = ''
    if cfg and cfg.logo:
        try:
            logo_url = cfg.logo.url
        except Exception:
            logger.exception('No se pudo resolver logo.url del negocio')
            logo_url = ''

    return render(request, 'inventario/etiquetas.html', {
        'productos_json': json.dumps(productos_data),
        'producto_preseleccionado': producto_id,
        'variante_preseleccionada': variante_id,
        'nombre_negocio': cfg.nombre_negocio if cfg else 'Sistema Tienda',
        'logo_url': logo_url,
    })
