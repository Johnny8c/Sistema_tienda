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

    # Personalización visual
    color_primario = models.CharField(
        max_length=7, default='#4F46E5',
        help_text='Color principal del sistema (botones, links, badges).',
    )

    # Operativos — alertas
    stock_minimo_alerta = models.PositiveIntegerField(
        default=5,
        help_text='Cuando el stock disponible de una variante baje de este valor, se muestra como "stock bajo".',
    )
    dias_alerta_vencimiento = models.PositiveIntegerField(
        default=7,
        help_text='Días de anticipación para alertar deudas o adelantos por vencer.',
    )

    # Inventario / venta
    permitir_vender_sin_stock = models.BooleanField(
        default=False,
        help_text='Permitir registrar ventas aunque el producto no tenga stock disponible.',
    )

    # POS
    cliente_obligatorio_venta = models.BooleanField(
        default=False,
        help_text='Exigir cliente en cada venta (si está apagado, "Consumidor final" es válido).',
    )
    PRECIO_RANGO_BLOQUEAR  = 'bloquear'
    PRECIO_RANGO_ADVERTIR  = 'advertir'
    PRECIO_RANGO_PERMITIR  = 'permitir'
    PRECIO_RANGO_OPCIONES = [
        (PRECIO_RANGO_BLOQUEAR, 'Bloquear'),
        (PRECIO_RANGO_ADVERTIR, 'Advertir'),
        (PRECIO_RANGO_PERMITIR, 'Permitir'),
    ]
    precio_fuera_rango_modo = models.CharField(
        max_length=12, choices=PRECIO_RANGO_OPCIONES, default=PRECIO_RANGO_ADVERTIR,
        help_text='Qué hacer cuando el vendedor pone un precio fuera del rango min/max del producto.',
    )
    sonido_escaneo = models.BooleanField(
        default=True,
        help_text='Reproducir un beep al detectar un código de barras en el POS.',
    )

    # Notas de venta
    imprimir_auto_nota = models.BooleanField(
        default=False,
        help_text='Abrir automáticamente la nota de venta al cobrar.',
    )
    mostrar_logo_en_nota = models.BooleanField(
        default=True,
        help_text='Incluir el logo del negocio en notas de venta y RIDE.',
    )
    mostrar_vendedor_en_nota = models.BooleanField(
        default=True,
        help_text='Mostrar el nombre del vendedor que registró la venta en la nota.',
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

    @staticmethod
    def _hex_to_rgb(h):
        h = (h or '').lstrip('#')
        if len(h) != 6:
            h = '4F46E5'
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    @staticmethod
    def _rgb_to_hex(r, g, b):
        return '#{:02X}{:02X}{:02X}'.format(
            max(0, min(255, int(r))),
            max(0, min(255, int(g))),
            max(0, min(255, int(b))),
        )

    @property
    def color_primario_dark(self):
        """Versión 22% más oscura del color primario (para hover)."""
        r, g, b = self._hex_to_rgb(self.color_primario)
        return self._rgb_to_hex(r * 0.78, g * 0.78, b * 0.78)

    @property
    def color_primario_light(self):
        """Versión clara del color primario (para texto sobre sidebar oscuro)."""
        r, g, b = self._hex_to_rgb(self.color_primario)
        # Mezcla 60% primario + 40% blanco
        return self._rgb_to_hex(r * 0.6 + 255 * 0.4, g * 0.6 + 255 * 0.4, b * 0.6 + 255 * 0.4)

    @property
    def color_primario_rgb(self):
        """Tupla 'r,g,b' para usar en rgba(...)."""
        r, g, b = self._hex_to_rgb(self.color_primario)
        return f'{r},{g},{b}'

    @property
    def color_sidebar(self):
        """Color del sidebar (light mode): muy oscuro tintado con el primario."""
        r, g, b = self._hex_to_rgb(self.color_primario)
        # 15% primario + base oscura (5, 8, 16)
        return self._rgb_to_hex(r * 0.15 + 5, g * 0.15 + 8, b * 0.15 + 16)

    @property
    def color_sidebar_dark(self):
        """Color del sidebar (dark mode): casi negro tintado."""
        r, g, b = self._hex_to_rgb(self.color_primario)
        # 6% primario + base muy oscura (3, 7, 15)
        return self._rgb_to_hex(r * 0.06 + 3, g * 0.06 + 7, b * 0.06 + 15)
