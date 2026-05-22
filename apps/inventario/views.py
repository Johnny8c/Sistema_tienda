import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, ProtectedError
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from apps.usuarios.decorators import requiere_no_vendedor
from .models import CatalogoProducto, Producto, Categoria

logger = logging.getLogger(__name__)


def _form_producto_data(post=None):
    """Devuelve un dict con todas las claves esperadas por form_producto.html.
    Evita VariableDoesNotExist en Django 6 cuando el dict está vacío."""
    keys = ['nombre', 'categoria', 'precio_base', 'precio_minimo', 'precio_maximo',
            'color', 'talla', 'precio', 'stock']
    return {k: (post.get(k, '') if post else '') for k in keys}


def _validar_foto(request, foto):
    """Valida tamano y tipo de una imagen subida. Devuelve mensaje de error o None."""
    if not foto:
        return None
    if foto.size > 5 * 1024 * 1024:
        return 'La imagen no puede pesar más de 5 MB.'
    if not (foto.content_type or '').startswith('image/'):
        return 'El archivo debe ser una imagen.'
    return None


# ── Inventario (catálogo) ──────────────────────────────────

@login_required
def lista_inventario(request):
    q = request.GET.get('q', '')
    cat = request.GET.get('cat', '')
    catalogos = (CatalogoProducto.objects.filter(activo=True)
                 .select_related('categoria')
                 .prefetch_related('variantes'))
    if q:
        catalogos = catalogos.filter(nombre__icontains=q)
    if cat:
        catalogos = catalogos.filter(categoria_id=cat)

    catalogos = list(catalogos)
    for c in catalogos:
        activas = [v for v in c.variantes.all() if v.activo]
        c.tallas_unicas = list(dict.fromkeys(v.talla for v in activas if v.talla))
        c.colores_unicos = list(dict.fromkeys(v.color for v in activas if v.color))

    categorias = Categoria.objects.filter(activo=True)
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

    categorias_activas = Categoria.objects.filter(activo=True)

    if request.method == 'POST':
        from decimal import Decimal, InvalidOperation
        nombre      = request.POST.get('nombre', '').strip()
        categoria_id = request.POST.get('categoria', '').strip()
        descripcion = request.POST.get('descripcion', '').strip()
        precio_min  = (request.POST.get('precio_minimo', '') or '').strip()
        precio_max  = (request.POST.get('precio_maximo', '') or '').strip()
        # Primera variante
        color  = request.POST.get('color', '').strip()
        talla  = request.POST.get('talla', '').strip()
        stock  = (request.POST.get('stock', '') or '').strip() or '0'

        categoria_obj = None
        if categoria_id:
            categoria_obj = categorias_activas.filter(pk=categoria_id).first()

        def _re_render():
            return render(request, 'inventario/form_producto.html', {
                'accion': 'Crear', 'categorias': categorias_activas,
                'f': _form_producto_data(request.POST),
            })

        if not nombre:
            messages.error(request, 'El nombre es obligatorio.')
            return _re_render()
        try:
            pmin = Decimal(precio_min) if precio_min else None
            pmax = Decimal(precio_max) if precio_max else None
        except InvalidOperation:
            messages.error(request, 'Los precios deben ser números válidos.')
            return _re_render()
        if pmin is None or pmax is None:
            messages.error(request, 'Debes ingresar precio mínimo y máximo.')
            return _re_render()
        if pmin > pmax:
            messages.error(request, 'El precio mínimo no puede ser mayor al máximo.')
            return _re_render()

        # precio_base = promedio del rango (uso interno)
        pb = ((pmin + pmax) / 2).quantize(Decimal('0.01'))

        # Precio inicial de la variante = precio mínimo (o lo que el form mande)
        precio_var = (request.POST.get('precio', '') or '').strip() or str(pmin)

        foto = request.FILES.get('foto')
        err = _validar_foto(request, foto)
        if err:
            messages.error(request, err)
            return _re_render()

        catalogo = CatalogoProducto.objects.create(
            nombre=nombre, categoria=categoria_obj,
            descripcion=descripcion, precio_base=pb,
            precio_minimo=pmin, precio_maximo=pmax,
            foto=foto or None,
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
        'accion': 'Crear', 'categorias': categorias_activas,
        'f': _form_producto_data(),
    })


@login_required
def editar_producto(request, pk):
    if not request.user.puede_gestionar_inventario():
        messages.error(request, 'No tienes permiso para editar productos.')
        return redirect('lista_inventario')

    catalogo = get_object_or_404(CatalogoProducto, pk=pk)
    categorias_activas = Categoria.objects.filter(activo=True)

    if request.method == 'POST':
        catalogo.nombre      = request.POST.get('nombre', catalogo.nombre).strip()
        cat_id = request.POST.get('categoria', '').strip()
        if cat_id:
            catalogo.categoria = categorias_activas.filter(pk=cat_id).first()
        else:
            catalogo.categoria = None
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
        nueva_foto = request.FILES.get('foto')
        if nueva_foto:
            err = _validar_foto(request, nueva_foto)
            if err:
                messages.error(request, err)
                return redirect('editar_producto', pk=catalogo.pk)
            catalogo.foto = nueva_foto
        catalogo.save()
        # Sincronizar nombre en variantes
        catalogo.variantes.all().update(nombre=catalogo.nombre)
        messages.success(request, 'Producto actualizado.')
        return redirect('detalle_producto', pk=catalogo.pk)

    return render(request, 'inventario/form_producto.html', {
        'accion': 'Editar', 'catalogo': catalogo,
        'categorias': categorias_activas,
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
            'categoria':       (cat.categoria.nombre if cat and cat.categoria else ''),
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
            'categoria': (p.catalogo.categoria.nombre if p.catalogo and p.catalogo.categoria else ''),
            'talla': p.talla,
            'color': p.color,
            'precio': str(p.precio),
            'stock': p.stock,
            'stock_disponible': p.stock_disponible,
            'codigo_barras': p.codigo_barras or '',
            # Fecha de ingreso (local America/Guayaquil) para filtrar "por día"
            'creado': timezone.localtime(p.creado_en).strftime('%Y-%m-%d') if p.creado_en else '',
        })

    logo_url = ''
    if cfg and cfg.logo:
        try:
            logo_url = cfg.logo.url
        except Exception:
            logger.exception('No se pudo resolver logo.url del negocio')
            logo_url = ''

    return render(request, 'inventario/etiquetas.html', {
        'productos_data': productos_data,
        'producto_preseleccionado': producto_id,
        'variante_preseleccionada': variante_id,
        'nombre_negocio': cfg.nombre_negocio if cfg else 'Sistema Tienda',
        'logo_url': logo_url,
    })


# ── Categorías (dueño + bodeguero) ─────────────────────────────

@login_required
@requiere_no_vendedor
def lista_categorias(request):
    categorias = (Categoria.objects
                  .annotate(cant_productos=Count('productos'))
                  .order_by('orden', 'nombre'))
    return render(request, 'inventario/categorias/lista.html', {
        'categorias': categorias,
    })


@login_required
@requiere_no_vendedor
def crear_categoria(request):
    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        orden_raw = (request.POST.get('orden', '') or '').strip()
        if not nombre:
            messages.error(request, 'El nombre de la categoría es obligatorio.')
            return render(request, 'inventario/categorias/form.html', {
                'accion': 'Crear', 'f_nombre': nombre, 'f_orden': orden_raw,
            })
        if Categoria.objects.filter(nombre__iexact=nombre).exists():
            messages.error(request, f'Ya existe una categoría llamada "{nombre}".')
            return render(request, 'inventario/categorias/form.html', {
                'accion': 'Crear', 'f_nombre': nombre, 'f_orden': orden_raw,
            })
        try:
            orden = int(orden_raw) if orden_raw else 0
        except ValueError:
            orden = 0
        Categoria.objects.create(nombre=nombre, orden=max(0, orden))
        messages.success(request, f'Categoría "{nombre}" creada.')
        return redirect('lista_categorias')

    return render(request, 'inventario/categorias/form.html', {
        'accion': 'Crear', 'f_nombre': '', 'f_orden': '',
    })


@login_required
@requiere_no_vendedor
def editar_categoria(request, pk):
    cat = get_object_or_404(Categoria, pk=pk)
    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        orden_raw = (request.POST.get('orden', '') or '').strip()
        if not nombre:
            messages.error(request, 'El nombre de la categoría es obligatorio.')
            return render(request, 'inventario/categorias/form.html', {
                'accion': 'Editar', 'categoria': cat,
                'f_nombre': nombre, 'f_orden': orden_raw,
            })
        if Categoria.objects.filter(nombre__iexact=nombre).exclude(pk=cat.pk).exists():
            messages.error(request, f'Ya existe otra categoría llamada "{nombre}".')
            return render(request, 'inventario/categorias/form.html', {
                'accion': 'Editar', 'categoria': cat,
                'f_nombre': nombre, 'f_orden': orden_raw,
            })
        try:
            orden = int(orden_raw) if orden_raw else 0
        except ValueError:
            orden = 0
        cat.nombre = nombre
        cat.orden = max(0, orden)
        cat.save()
        messages.success(request, f'Categoría "{cat.nombre}" actualizada.')
        return redirect('lista_categorias')

    return render(request, 'inventario/categorias/form.html', {
        'accion': 'Editar', 'categoria': cat,
        'f_nombre': cat.nombre, 'f_orden': cat.orden,
    })


@require_POST
@login_required
@requiere_no_vendedor
def toggle_categoria(request, pk):
    cat = get_object_or_404(Categoria, pk=pk)
    cat.activo = not cat.activo
    cat.save(update_fields=['activo'])
    estado = 'activada' if cat.activo else 'desactivada'
    messages.success(request, f'Categoría "{cat.nombre}" {estado}.')
    return redirect('lista_categorias')


@require_POST
@login_required
@requiere_no_vendedor
def eliminar_categoria(request, pk):
    cat = get_object_or_404(Categoria, pk=pk)
    nombre = cat.nombre
    cantidad_productos = cat.productos.count()
    try:
        cat.delete()
    except ProtectedError:
        messages.error(
            request,
            f'No se puede eliminar "{nombre}" porque hay productos asociados.'
        )
        return redirect('lista_categorias')
    if cantidad_productos:
        messages.success(
            request,
            f'Categoría "{nombre}" eliminada. {cantidad_productos} '
            f'producto{"s" if cantidad_productos != 1 else ""} quedaron sin categoría.'
        )
    else:
        messages.success(request, f'Categoría "{nombre}" eliminada.')
    return redirect('lista_categorias')
