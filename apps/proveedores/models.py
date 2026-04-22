from django.db import models
from django.conf import settings


class Proveedor(models.Model):
    nombre = models.CharField(max_length=200)
    ruc = models.CharField(max_length=13, blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    direccion = models.TextField(blank=True)
    contacto = models.CharField(max_length=100, blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Proveedor'
        verbose_name_plural = 'Proveedores'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Compra(models.Model):
    PENDIENTE = 'pendiente'
    PAGADA = 'pagada'
    ESTADOS = [(PENDIENTE, 'Pendiente'), (PAGADA, 'Pagada')]

    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT, related_name='compras')
    fecha = models.DateField()
    numero_factura = models.CharField(max_length=50, blank=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=PENDIENTE)
    notas = models.TextField(blank=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Compra'
        verbose_name_plural = 'Compras'
        ordering = ['-fecha']

    def __str__(self):
        return f'Compra #{self.pk} — {self.proveedor} — {self.fecha}'


class ItemCompra(models.Model):
    compra = models.ForeignKey(Compra, on_delete=models.CASCADE, related_name='items')
    producto = models.ForeignKey('inventario.Producto', on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario

    def __str__(self):
        return f'{self.producto} x{self.cantidad}'
