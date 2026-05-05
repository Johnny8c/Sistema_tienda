from django.db import models


class CatalogoProducto(models.Model):
    """Producto base: nombre, foto y precio de referencia. Agrupa variantes por color/talla."""
    CATEGORIAS = [
        ('blusas',      'Blusas'),
        ('camisas',     'Camisas'),
        ('camisetas',   'Camisetas'),
        ('pantalones',  'Pantalones'),
        ('vestidos',    'Vestidos'),
        ('faldas',      'Faldas'),
        ('chaquetas',   'Chaquetas'),
        ('zapatos',     'Zapatos'),
        ('accesorios',  'Accesorios'),
        ('otro',        'Otro'),
    ]

    nombre       = models.CharField(max_length=200)
    categoria    = models.CharField(max_length=50, choices=CATEGORIAS, default='otro')
    descripcion  = models.TextField(blank=True)
    precio_base  = models.DecimalField(max_digits=10, decimal_places=2)
    foto         = models.ImageField(upload_to='productos/', blank=True, null=True)
    activo       = models.BooleanField(default=True)
    creado_en    = models.DateTimeField(auto_now_add=True)

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
