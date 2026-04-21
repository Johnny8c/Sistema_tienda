from django.db import models
from django.conf import settings
from apps.clientes.models import Cliente


class Venta(models.Model):
    CONTADO = 'contado'
    CREDITO = 'credito'
    ADELANTO_COMPLETADO = 'adelanto_completado'

    TIPOS_PAGO = [
        (CONTADO, 'Contado'),
        (CREDITO, 'Crédito'),
        (ADELANTO_COMPLETADO, 'Apartado completado'),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, null=True, blank=True)
    tipo_pago = models.CharField(max_length=25, choices=TIPOS_PAGO, default=CONTADO)
    deuda_id = models.PositiveIntegerField(null=True, blank=True)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    vendedor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)
    notas = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Venta'
        verbose_name_plural = 'Ventas'

    def __str__(self):
        return f'Venta #{self.pk} — {self.fecha.date()} — ${self.total}'


class ItemVenta(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='items')
    producto = models.ForeignKey('inventario.Producto', on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario
