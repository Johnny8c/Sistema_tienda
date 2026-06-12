import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, ProtectedError
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from apps.usuarios.decorators import requiere_no_vendedor
from .models import CatalogoProducto, Producto, Categoria, EtiquetaImpresa

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

def _normalizar_texto(s):
    """minúsculas y sin acentos/ñ→n, para comparar como escribe la gente."""
    import unicodedata
    s = unicodedata.normalize('NFD', s or '')
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower().strip()


def _ids_por_similitud(q, pares):
    """Búsqueda tolerante para el inventario. `pares` = [(id, nombre), ...].
    Devuelve los ids que coinciden, ordenados por relevancia.

    Coincide aunque: falten/sobren acentos ("pano"→"paño"), las palabras
    vayan en otro orden ("bombacho paño"), o haya un error de tipeo leve
    ("camiseta galeta"→"Camiseata galleta"). Antes era icontains literal y
    solo encontraba lo escrito tal cual.
    """
    from difflib import SequenceMatcher

    qn = _normalizar_texto(q)
    tokens = qn.split()
    if not tokens:
        return [pk for pk, _ in pares]

    puntuados = []
    for pk, nombre in pares:
        nn = _normalizar_texto(nombre)
        if qn in nn:
            # La frase completa aparece tal cual: máxima relevancia
            puntuados.append((0, nn, pk))
            continue
        palabras = nn.split()
        score = 0.0
        for t in tokens:
            if t in nn:
                score += 1.0
                continue
            # Tipeo leve: comparar contra cada palabra del nombre. Solo para
            # tokens de 4+ letras (en cortos como "de" daría falsos positivos).
            mejor = 0.0
            if len(t) >= 4:
                mejor = max((SequenceMatcher(None, t, w).ratio() for w in palabras),
                            default=0.0)
            if mejor >= 0.75:
                score += mejor
            else:
                score = -1.0  # un token no coincidió: descartar el producto
                break
        if score >= 0:
            # 1 = menos prioritario que el match de frase; luego mayor score
            puntuados.append((1, -score, nn, pk))

    puntuados.sort(key=lambda x: x[:-1])
    return [item[-1] for item in puntuados]


@login_required
def lista_inventario(request):
    from django.core.paginator import Paginator
    q = request.GET.get('q', '')
    cat = request.GET.get('cat', '')
    catalogos_qs = (CatalogoProducto.objects.filter(activo=True)
                    .select_related('categoria')
                    .prefetch_related('variantes')
                    .order_by('nombre'))
    if cat:
        catalogos_qs = catalogos_qs.filter(categoria_id=cat)

    if q:
        # Búsqueda por similitud (acentos, orden de palabras, tipeo leve).
        # Se resuelve en Python sobre (id, nombre) — son ~1100 catálogos, es
        # barato y funciona igual en SQLite (dev) y PostgreSQL (prod).
        ids = _ids_por_similitud(q, catalogos_qs.values_list('id', 'nombre'))
        posicion = {pk: i for i, pk in enumerate(ids)}
        objetos = sorted(catalogos_qs.filter(id__in=ids),
                         key=lambda c: posicion[c.pk])
        paginator = Paginator(objetos, 60)
    else:
        # Paginar a 60 catálogos por página. Antes cargábamos los 1142+ de una,
        # generando HTML enorme + tirando muchas fotos de Cloudinary a la vez.
        paginator = Paginator(catalogos_qs, 60)
    page_obj = paginator.get_page(request.GET.get('page'))

    for c in page_obj:
        activas = [v for v in c.variantes.all() if v.activo]
        c.tallas_unicas = list(dict.fromkeys(v.talla for v in activas if v.talla))
        c.colores_unicos = list(dict.fromkeys(v.color for v in activas if v.color))

    categorias = Categoria.objects.filter(activo=True)
    return render(request, 'inventario/lista.html', {
        'catalogos': page_obj, 'page_obj': page_obj,
        'q': q, 'cat': cat, 'categorias': categorias,
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
            # Si la variante se etiquetó antes de que existiera el snapshot
            # (registro legacy con NULL), fijarlo al stock previo para que
            # las unidades que entren con este ajuste cuenten como faltantes.
            EtiquetaImpresa.materializar_legacy(producto.codigo_barras, producto.stock)
            producto.stock = int(nuevo_stock)
            producto.save()
            # Mantener coherente el contador de etiquetas: no pueden quedar más
            # unidades "ya etiquetadas" que el stock real, o un reabastecimiento
            # posterior imprimiría de menos.
            EtiquetaImpresa.sincronizar_con_stock(producto.codigo_barras, producto.stock)
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

def _construir_impresas_data():
    """Historial de impresión por código de barras (compartido entre devices)."""
    data = {}
    for r in EtiquetaImpresa.objects.values(
        'codigo_barras', 'total_impresas', 'ultima_impresion', 'stock_al_imprimir'
    ):
        data[r['codigo_barras']] = {
            'ts': int(r['ultima_impresion'].timestamp() * 1000),
            'total': r['total_impresas'],
            'stock_al_imprimir': r['stock_al_imprimir'],
        }
    return data


def _construir_productos_data():
    """Lista de variantes activas con código de barras para la pantalla de
    etiquetas. Reutilizado por la carga inicial y por el refresco automático."""
    productos = (Producto.objects.filter(activo=True)
                 .select_related('catalogo')
                 .order_by('catalogo__nombre', 'talla', 'color'))
    data = []
    for p in productos:
        data.append({
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
    return data


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

    productos_data = _construir_productos_data()

    logo_url = ''
    if cfg and cfg.logo:
        try:
            logo_url = cfg.logo.url
        except Exception:
            logger.exception('No se pudo resolver logo.url del negocio')
            logo_url = ''

    # Historial de impresión (compartido entre dispositivos). Antes vivía en
    # localStorage del navegador, por eso la PC central y el celular mostraban
    # porcentajes distintos. Ahora viene de la BD y todos ven lo mismo.
    impresas_data = _construir_impresas_data()

    return render(request, 'inventario/etiquetas.html', {
        'productos_data': productos_data,
        'impresas_data': impresas_data,
        'producto_preseleccionado': producto_id,
        'variante_preseleccionada': variante_id,
        'nombre_negocio': cfg.nombre_negocio if cfg else 'Sistema Tienda',
        'logo_url': logo_url,
    })


# ── API: registrar / reiniciar etiquetas impresas (servidor) ──────────
# Se hicieron POST en vez de localStorage para que el progreso sea el
# mismo en cualquier dispositivo conectado a la misma cuenta.

@login_required
@require_POST
def api_etiquetas_marcar_impresas(request):
    """Recibe {items:[{codigo_barras, cantidad}, ...]} y registra las
    impresiones. Suma a total_impresas y actualiza ultima_impresion.

    `stock_al_imprimir` se ACUMULA (etiquetadas previas + las recién
    impresas, tope el stock actual) en vez de pisarse con el stock completo.
    Pisarlo hacía que imprimir 5 etiquetas de una variante con 10 unidades
    marcara las 10 como etiquetadas y las otras 5 desaparecieran del conteo
    de faltantes."""
    import json
    from django.db.models import F, Value
    from django.db.models.functions import Coalesce, Least

    if not request.user.puede_gestionar_inventario():
        return JsonResponse({'ok': False, 'mensaje': 'Sin permiso'}, status=403)

    try:
        payload = json.loads(request.body or '{}')
        items = payload.get('items') or []
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'mensaje': 'JSON inválido'}, status=400)

    ahora = timezone.now()
    resultados = {}

    # Lookup del stock actual de cada producto que vamos a marcar. Hacemos
    # una sola consulta (no 1 por item) para no quemar la BD.
    codigos = [
        (it.get('codigo_barras') or '').strip()
        for it in items if it.get('codigo_barras')
    ]
    stocks = dict(
        Producto.objects
        .filter(codigo_barras__in=codigos)
        .values_list('codigo_barras', 'stock')
    )

    for it in items:
        codigo = (it.get('codigo_barras') or '').strip()
        try:
            cant = int(it.get('cantidad') or 0)
        except (TypeError, ValueError):
            cant = 0
        if not codigo or cant <= 0:
            continue
        stock_actual = stocks.get(codigo, 0)
        obj, creado = EtiquetaImpresa.objects.get_or_create(
            codigo_barras=codigo,
            defaults={
                'total_impresas': cant,
                'ultima_impresion': ahora,
                'stock_al_imprimir': min(stock_actual, cant),
            },
        )
        if not creado:
            # F() para sumar sin race condition entre devices simultáneos.
            # Coalesce: un registro legacy (snapshot NULL) se trata como
            # "stock completo etiquetado", igual que hace el frontend.
            EtiquetaImpresa.objects.filter(pk=obj.pk).update(
                total_impresas=F('total_impresas') + cant,
                ultima_impresion=ahora,
                stock_al_imprimir=Least(
                    Coalesce(F('stock_al_imprimir'), Value(stock_actual)) + Value(cant),
                    Value(stock_actual),
                ),
            )
            obj.refresh_from_db(fields=['total_impresas', 'stock_al_imprimir'])
        resultados[codigo] = {
            'ts': int(ahora.timestamp() * 1000),
            'total': obj.total_impresas,
            'stock_al_imprimir': obj.stock_al_imprimir,
        }
    return JsonResponse({'ok': True, 'impresas': resultados})


@login_required
def api_etiquetas_estado(request):
    """Estado actual para el refresco automático entre dispositivos: lista
    completa de variantes (incluye las NUEVAS y refleja stock) + progreso de
    impresión. Permite que la PC se actualice sola cuando en el celular se
    marcan etiquetas, se vende/ajusta stock o se agregan variantes/categorías,
    sin recargar la página."""
    if not request.user.puede_gestionar_inventario():
        return JsonResponse({'ok': False, 'mensaje': 'Sin permiso'}, status=403)
    return JsonResponse({
        'ok': True,
        'productos': _construir_productos_data(),
        'impresas':  _construir_impresas_data(),
    })


@login_required
@require_POST
def api_etiquetas_reiniciar_impresas(request):
    """Borra TODO el historial de impresión. Afecta a todos los dispositivos."""
    if not request.user.puede_gestionar_inventario():
        return JsonResponse({'ok': False, 'mensaje': 'Sin permiso'}, status=403)
    eliminadas, _ = EtiquetaImpresa.objects.all().delete()
    return JsonResponse({'ok': True, 'eliminadas': eliminadas})


@login_required
@require_POST
def api_etiquetas_marcar_pendiente(request):
    """Marca una sola variante como pendiente de imprimir (sin tocar las
    demás). Se usa para regularizar productos a los que el dueño les ajustó
    stock manualmente y por eso el snapshot quedó desactualizado. NO borra
    el registro — solo pone stock_al_imprimir=0 para preservar el historial
    (fecha de última impresión, total acumulado) y que aparezca como
    'Falta N' donde N = stock actual."""
    import json

    if not request.user.puede_gestionar_inventario():
        return JsonResponse({'ok': False, 'mensaje': 'Sin permiso'}, status=403)

    try:
        payload = json.loads(request.body or '{}')
        codigo = (payload.get('codigo_barras') or '').strip()
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'mensaje': 'JSON inválido'}, status=400)

    if not codigo:
        return JsonResponse({'ok': False, 'mensaje': 'Falta codigo_barras'}, status=400)

    actualizadas = EtiquetaImpresa.objects.filter(codigo_barras=codigo).update(stock_al_imprimir=0)
    return JsonResponse({'ok': True, 'actualizadas': actualizadas})


@login_required
@require_POST
def api_etiquetas_importar_localstorage(request):
    """Importa el historial viejo que vivía en localStorage del navegador.
    Se llama UNA sola vez por navegador (el cliente guarda un flag local).
    Es idempotente: si una marca ya existe en BD no la pisa ni suma — así
    abrir la página varias veces no duplica el contador. Solo crea las que
    todavía no existían en el server."""
    import json
    from datetime import datetime, timezone as dt_tz

    if not request.user.puede_gestionar_inventario():
        return JsonResponse({'ok': False, 'mensaje': 'Sin permiso'}, status=403)

    try:
        payload = json.loads(request.body or '{}')
        items = payload.get('items') or []
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'mensaje': 'JSON inválido'}, status=400)

    importadas = 0
    ya_existian = 0
    impresas = {}
    # El historial viejo no traía snapshot de stock; lo fijamos al stock
    # actual ("todo lo de hoy ya tiene etiqueta") en vez de dejar NULL.
    # Un NULL haría invisible cualquier reposición futura de esa variante.
    stocks_import = dict(
        Producto.objects
        .filter(codigo_barras__in=[
            (it.get('codigo_barras') or '').strip()
            for it in items if it.get('codigo_barras')
        ])
        .values_list('codigo_barras', 'stock')
    )
    for it in items:
        codigo = (it.get('codigo_barras') or '').strip()
        try:
            total = max(1, int(it.get('total') or 1))
        except (TypeError, ValueError):
            total = 1
        try:
            ts_ms = int(it.get('ts') or 0)
        except (TypeError, ValueError):
            ts_ms = 0
        if not codigo:
            continue
        # ts del localStorage está en ms epoch. Si viene 0 o inválido, usamos
        # "ahora" para no perder la marca.
        if ts_ms > 0:
            ult = datetime.fromtimestamp(ts_ms / 1000, tz=dt_tz.utc)
        else:
            ult = timezone.now()

        obj, creado = EtiquetaImpresa.objects.get_or_create(
            codigo_barras=codigo,
            defaults={
                'total_impresas': total,
                'ultima_impresion': ult,
                'stock_al_imprimir': stocks_import.get(codigo, 0),
            },
        )
        if creado:
            importadas += 1
        else:
            ya_existian += 1
        impresas[codigo] = {
            'ts': int(obj.ultima_impresion.timestamp() * 1000),
            'total': obj.total_impresas,
            'stock_al_imprimir': obj.stock_al_imprimir,
        }
    return JsonResponse({
        'ok': True,
        'importadas': importadas,
        'ya_existian': ya_existian,
        'impresas': impresas,
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
