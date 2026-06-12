from django.db import models
from django.conf import settings
from apps.clientes.models import Cliente
from apps.inventario.models import Producto


class Adelanto(models.Model):
    ACTIVO = 'activo'
    COMPLETADO = 'completado'
    CANCELADO = 'cancelado'

    ESTADOS = [
        (ACTIVO, 'Activo'),
        (COMPLETADO, 'Completado'),
        (CANCELADO, 'Cancelado'),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='adelantos')
    total = models.DecimalField(max_digits=10, decimal_places=2)
    saldo_pendiente = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(max_length=15, choices=ESTADOS, default=ACTIVO)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_limite = models.DateField(null=True, blank=True)
    vendedor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='adelantos_creados'
    )
    notas = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Adelanto'
        verbose_name_plural = 'Adelantos'
        indexes = [
            models.Index(fields=['cliente', 'estado']),
        ]

    def __str__(self):
        return f'Adelanto #{self.pk} — {self.cliente} — ${self.saldo_pendiente} pendiente'


class AdelantoItem(models.Model):
    adelanto = models.ForeignKey(Adelanto, on_delete=models.CASCADE, related_name='items')
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario


class Deuda(models.Model):
    PENDIENTE = 'pendiente'
    SALDADA = 'saldada'
    CONDONADA = 'condonada'

    ESTADOS = [
        (PENDIENTE, 'Pendiente'),
        (SALDADA, 'Saldada'),
        (CONDONADA, 'Condonada'),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='deudas')
    venta = models.OneToOneField(
        'ventas.Venta', on_delete=models.PROTECT, related_name='deuda', null=True, blank=True
    )
    monto_original = models.DecimalField(max_digits=10, decimal_places=2)
    saldo_pendiente = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(max_length=15, choices=ESTADOS, default=PENDIENTE)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_vencimiento = models.DateField(null=True, blank=True)
    vendedor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='deudas_creadas'
    )

    class Meta:
        verbose_name = 'Deuda'
        verbose_name_plural = 'Deudas'
        indexes = [
            models.Index(fields=['cliente', 'estado']),
            models.Index(fields=['fecha_vencimiento']),
        ]

    def __str__(self):
        return f'Deuda #{self.pk} — {self.cliente} — ${self.saldo_pendiente} pendiente'

    @property
    def dias_transcurridos(self):
        from django.utils import timezone
        # Ambas fechas en hora de Ecuador; con .date() sobre UTC la antigüedad
        # cambiaba de día a las 19:00 locales.
        return (timezone.localdate() - timezone.localdate(self.fecha_creacion)).days

    @property
    def bucket_antiguedad(self):
        dias = self.dias_transcurridos
        if dias <= 30:
            return '0-30'
        elif dias <= 60:
            return '31-60'
        elif dias <= 90:
            return '61-90'
        return '90+'


class Pago(models.Model):
    TIPO_ADELANTO = 'adelanto'
    TIPO_DEUDA = 'deuda'

    TIPOS = [
        (TIPO_ADELANTO, 'Adelanto'),
        (TIPO_DEUDA, 'Deuda'),
    ]

    EFECTIVO = 'efectivo'
    TARJETA = 'tarjeta'
    TRANSFERENCIA = 'transferencia'

    FORMAS_PAGO = [
        (EFECTIVO, 'Efectivo'),
        (TARJETA, 'Tarjeta'),
        (TRANSFERENCIA, 'Transferencia / QR'),
    ]

    tipo = models.CharField(max_length=10, choices=TIPOS)
    referencia_id = models.PositiveIntegerField()
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    forma_pago = models.CharField(max_length=15, choices=FORMAS_PAGO, default=EFECTIVO)
    fecha = models.DateTimeField(auto_now_add=True)
    vendedor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='pagos_registrados'
    )
    notas = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Pago'
        verbose_name_plural = 'Pagos'
        indexes = [
            models.Index(fields=['tipo', 'referencia_id']),
        ]

    def __str__(self):
        return f'Pago #{self.pk} — {self.tipo} #{self.referencia_id} — ${self.monto}'
