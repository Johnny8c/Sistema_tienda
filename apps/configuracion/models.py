from django.db import models


class ConfiguracionGeneral(models.Model):
    """Singleton de configuración general del negocio (no fiscal)."""
    # Identidad del negocio
    nombre_negocio   = models.CharField(max_length=200, default='Sistema Tienda')
    slogan           = models.CharField(max_length=200, blank=True)
    logo             = models.ImageField(upload_to='configuracion/', blank=True, null=True)
    direccion        = models.CharField(max_length=300, blank=True)
    telefono         = models.CharField(max_length=20, blank=True)
    email            = models.EmailField(blank=True)
    sitio_web        = models.URLField(blank=True)

    # Contenido en notas de venta y RIDE
    mensaje_nota_venta = models.TextField(
        blank=True,
        default='¡Gracias por su compra!',
        help_text='Mensaje que aparece al pie de la nota de venta.',
    )

    # Operativos
    stock_minimo_alerta = models.PositiveIntegerField(
        default=5,
        help_text='Cuando el stock disponible de una variante baje de este valor, se muestra como "stock bajo".',
    )
    dias_alerta_vencimiento = models.PositiveIntegerField(
        default=7,
        help_text='Días de anticipación para alertar deudas o adelantos por vencer.',
    )

    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Configuración general'
        verbose_name_plural = 'Configuración general'

    def __str__(self):
        return self.nombre_negocio

    @classmethod
    def get_singleton(cls):
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create()
        return obj
