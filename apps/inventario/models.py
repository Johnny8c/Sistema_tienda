from django.db import models


def _generar_codigo():
    ultimo = Producto.objects.order_by('-id').first()
    siguiente = (ultimo.id + 1) if ultimo else 1
    return f'TDA-{siguiente:06d}'


class Producto(models.Model):
    nombre = models.CharField(max_length=200)
    codigo_barras = models.CharField(max_length=100, unique=True, blank=True, null=True)
    talla = models.CharField(max_length=20, blank=True)
    color = models.CharField(max_length=50, blank=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    stock_reservado = models.PositiveIntegerField(default=0)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'

    def __str__(self):
        return f'{self.nombre} — {self.talla} {self.color}'

    @property
    def stock_disponible(self):
        return self.stock - self.stock_reservado
