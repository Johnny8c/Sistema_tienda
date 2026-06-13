from django.db import models
from django.conf import settings
from django.utils.text import slugify


class Categoria(models.Model):
    """Categorías de productos administradas por el dueño/bodeguero."""
    nombre    = models.CharField(max_length=80, unique=True)
    slug      = models.SlugField(max_length=90, unique=True, blank=True)
    orden     = models.PositiveIntegerField(default=0, help_text='Orden de aparición. Menor = primero.')
    activo    = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Categoría'
        verbose_name_plural = 'Categorías'
        ordering            = ['orden', 'nombre']

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.nombre) or 'categoria'
            slug = base
            i = 2
            while Categoria.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{i}'
                i += 1
            self.slug = slug
        super().save(*args, **kwargs)


class CatalogoProducto(models.Model):
    """Producto base: nombre, foto y precio de referencia. Agrupa variantes por color/talla."""
    nombre        = models.CharField(max_length=200)
    categoria     = models.ForeignKey(
        Categoria, on_delete=models.SET_NULL,
        related_name='productos', null=True, blank=True,
    )
    descripcion   = models.TextField(blank=True)
    precio_base   = models.DecimalField(max_digits=10, decimal_places=2,
                                        help_text='Precio sugerido / por defecto.')
    precio_minimo = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                        help_text='Precio mínimo permitido al vender (no se puede bajar de aquí).')
    precio_maximo = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                        help_text='Precio máximo sugerido (techo recomendado).')
    foto          = models.ImageField(upload_to='productos/', blank=True, null=True)
    activo        = models.BooleanField(default=True)
    creado_en     = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Catálogo producto'
        verbose_name_plural = 'Catálogo productos'
        ordering            = ['nombre']

    def __str__(self):
        return self.nombre

    @property
    def stock_total_disponible(self):
        return sum(v.stock_disponible for v in self.variantes.filter(activo=True))

    @property
    def precio_min(self):
        precios = list(self.variantes.filter(activo=True).values_list('precio', flat=True))
        return min(precios) if precios else self.precio_base

    @property
    def precio_max(self):
        precios = list(self.variantes.filter(activo=True).values_list('precio', flat=True))
        return max(precios) if precios else self.precio_base


def _generar_codigo():
    ultimo = Producto.objects.order_by('-id').first()
    siguiente = (ultimo.id + 1) if ultimo else 1
    return f'TDA-{siguiente:06d}'


class Producto(models.Model):
    """Variante de producto: color + talla + stock + código de barras."""
    catalogo        = models.ForeignKey(
        CatalogoProducto, on_delete=models.CASCADE,
        related_name='variantes', null=True, blank=True,
    )
    # Se mantiene nombre para compatibilidad con ventas/deudores/compras ya registradas
    nombre          = models.CharField(max_length=200)
    codigo_barras   = models.CharField(max_length=100, unique=True, blank=True, null=True)
    talla           = models.CharField(max_length=20, blank=True)
    color           = models.CharField(max_length=50, blank=True)
    precio          = models.DecimalField(max_digits=10, decimal_places=2)
    stock           = models.PositiveIntegerField(default=0)
    stock_reservado = models.PositiveIntegerField(default=0)
    activo          = models.BooleanField(default=True)
    creado_en       = models.DateTimeField(auto_now_add=True)
    # Última vez que ENTRÓ stock después de creada (ajuste al alza o compra a
    # proveedor). Alimenta el filtro "Por día de ingreso" de etiquetas, que
    # antes solo veía la fecha de creación y dejaba fuera las reposiciones.
    ultimo_ingreso_stock = models.DateTimeField(null=True, blank=True)
    # Stock que tenía la variante ANTES de su último movimiento de stock. Se
    # muestra en la pantalla de ajuste ("Stock anterior") para dar contexto
    # rápido. El historial completo vive en MovimientoInventario.
    stock_anterior = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name        = 'Producto'
        verbose_name_plural = 'Productos'

    def __str__(self):
        partes = [self.nombre]
        if self.talla:
            partes.append(self.talla)
        if self.color:
            partes.append(self.color)
        return ' · '.join(partes)

    @property
    def stock_disponible(self):
        return self.stock - self.stock_reservado

    def save(self, *args, **kwargs):
        # Sincroniza nombre con catálogo cuando existe
        if self.catalogo_id and not self.nombre:
            self.nombre = self.catalogo.nombre
        super().save(*args, **kwargs)
        # Garantía a nivel de modelo: toda variante queda con código de barras,
        # sin importar desde qué flujo se cree (vistas, seeds, imports). Una
        # variante sin código es invisible en la pantalla de etiquetas y su
        # stock no cuenta para etiquetas pendientes.
        if not self.codigo_barras:
            self.codigo_barras = f'TDA-{self.pk:06d}'
            super().save(update_fields=['codigo_barras'])


class EtiquetaImpresa(models.Model):
    """Historial de impresión de etiquetas — compartido entre todos los
    dispositivos. Antes vivía en localStorage del navegador, lo que hacía que
    la PC central y el celular mostraran porcentajes distintos. Aquí
    persistimos cuántas veces se imprimió cada código de barras y cuándo
    fue la última, para que el indicador de progreso sea el mismo en
    cualquier dispositivo que abra la cuenta."""
    codigo_barras    = models.CharField(max_length=100, unique=True, db_index=True)
    total_impresas   = models.PositiveIntegerField(default=0)
    ultima_impresion = models.DateTimeField()
    # Snapshot del stock que tenía la variante al marcar como impresa. Sirve
    # para detectar "faltantes": si hoy el producto tiene stock=8 pero al
    # imprimir tenía stock=5, faltan 3 etiquetas para las nuevas unidades.
    # NULL = registro previo a esta feature; la app lo trata como "todo impreso".
    stock_al_imprimir = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        verbose_name        = 'Etiqueta impresa'
        verbose_name_plural = 'Etiquetas impresas'
        ordering            = ['-ultima_impresion']

    def __str__(self):
        return f'{self.codigo_barras} (×{self.total_impresas})'

    @staticmethod
    def descontar_por_venta(codigo_barras, cantidad):
        """Al vender unidades, la etiqueta física impresa se va con el producto.
        Reduce el snapshot `stock_al_imprimir` para que, si más tarde se repone
        stock, esas unidades nuevas se detecten como 'faltan etiquetas'.

        Sin esto, vender la última unidad y recargar stock al mismo nivel dejaba
        `stock_al_imprimir >= stock` y el sistema la mostraba como 'Impresa',
        cuando en realidad la etiqueta ya no existe.
        """
        if not codigo_barras or cantidad <= 0:
            return
        ei = EtiquetaImpresa.objects.filter(codigo_barras=codigo_barras).first()
        if ei and ei.stock_al_imprimir:
            ei.stock_al_imprimir = max(0, ei.stock_al_imprimir - cantidad)
            ei.save(update_fields=['stock_al_imprimir'])

    @staticmethod
    def materializar_legacy(codigo_barras, stock_actual):
        """Convierte un registro legacy (stock_al_imprimir=NULL, anterior a la
        feature de snapshot) en uno concreto, usando el stock ANTES de un
        aumento. NULL se interpreta como 'todo el stock de ese momento ya
        tenía etiqueta'; al fijarlo en el stock previo, las unidades que
        entren después cuentan como 'faltan etiquetas'. Sin esto, reponer
        stock sobre una variante etiquetada antes de la feature perdía las
        etiquetas nuevas en silencio (el caso real de '100 prendas, 95
        etiquetas'). Llamar ANTES de subir el stock."""
        if not codigo_barras:
            return
        (EtiquetaImpresa.objects
         .filter(codigo_barras=codigo_barras, stock_al_imprimir__isnull=True)
         .update(stock_al_imprimir=stock_actual))

    @staticmethod
    def sincronizar_con_stock(codigo_barras, stock):
        """Al ajustar el stock manualmente no pueden quedar más unidades
        'etiquetadas' que unidades en existencia. Si `stock_al_imprimir` supera
        el nuevo stock, lo bajamos. Así, si después se repone stock, las
        etiquetas faltantes se cuentan bien (no quedan unidades viejas
        'fantasma' que ya no existen pero seguían contando como impresas)."""
        if not codigo_barras:
            return
        ei = EtiquetaImpresa.objects.filter(codigo_barras=codigo_barras).first()
        if ei and ei.stock_al_imprimir is not None and ei.stock_al_imprimir > stock:
            ei.stock_al_imprimir = stock
            ei.save(update_fields=['stock_al_imprimir'])


class MovimientoInventario(models.Model):
    """Bitácora de auditoría del inventario: registra TODO cambio de stock o
    de reservas de una variante — quién lo hizo, cuándo, de cuánto a cuánto y
    por qué (ajuste, venta, compra, apartado, creación). Permite reconstruir
    el historial completo y respaldar el inventario ante dudas ('faltan
    unidades', 'no se imprimieron todas las etiquetas')."""

    CREACION             = 'creacion'
    AJUSTE               = 'ajuste'
    VENTA                = 'venta'
    VENTA_CREDITO        = 'venta_credito'
    APARTADO             = 'apartado'
    APARTADO_COMPLETADO  = 'apartado_completado'
    APARTADO_CANCELADO   = 'apartado_cancelado'
    COMPRA               = 'compra'

    TIPOS = [
        (CREACION,            'Creación de variante'),
        (AJUSTE,              'Ajuste manual de stock'),
        (VENTA,               'Venta al contado'),
        (VENTA_CREDITO,       'Venta a crédito'),
        (APARTADO,            'Apartado (reserva)'),
        (APARTADO_COMPLETADO, 'Apartado entregado'),
        (APARTADO_CANCELADO,  'Apartado cancelado'),
        (COMPRA,              'Compra a proveedor'),
    ]

    # SET_NULL + snapshot de código/nombre: la bitácora sobrevive aunque la
    # variante se borre alguna vez (hoy solo se desactivan, pero el log de
    # auditoría no debe depender de eso).
    producto = models.ForeignKey(
        Producto, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='movimientos',
    )
    codigo_barras   = models.CharField(max_length=100, blank=True, db_index=True)
    nombre_producto = models.CharField(max_length=250, blank=True)

    tipo = models.CharField(max_length=25, choices=TIPOS, db_index=True)

    stock_anterior = models.IntegerField()
    stock_nuevo    = models.IntegerField()
    # Solo se llenan en apartados (reserva/liberación). NULL = el movimiento no
    # tocó el stock reservado.
    reservado_anterior = models.IntegerField(null=True, blank=True)
    reservado_nuevo    = models.IntegerField(null=True, blank=True)

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='movimientos_inventario',
    )
    referencia = models.CharField(max_length=120, blank=True,
                                  help_text='p. ej. "Venta #123", "Compra #45"')
    nota = models.CharField(max_length=250, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name        = 'Movimiento de inventario'
        verbose_name_plural = 'Movimientos de inventario'
        ordering            = ['-creado_en', '-id']
        indexes = [
            models.Index(fields=['producto', '-creado_en']),
        ]

    def __str__(self):
        return f'{self.get_tipo_display()} · {self.codigo_barras} · {self.stock_anterior}→{self.stock_nuevo}'

    @property
    def delta_stock(self):
        return self.stock_nuevo - self.stock_anterior

    @property
    def delta_reservado(self):
        if self.reservado_anterior is None or self.reservado_nuevo is None:
            return None
        return self.reservado_nuevo - self.reservado_anterior
