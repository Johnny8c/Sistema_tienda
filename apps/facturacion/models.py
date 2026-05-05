from django.db import models
from django.conf import settings


class ConfiguracionSRI(models.Model):
    """
    Configuración del emisor (singleton — una sola fila).
    Equivalente a la tabla 'clinicas' del sistema original, adaptada a tienda única.
    """
    PRUEBAS    = 'pruebas'
    PRODUCCION = 'produccion'
    AMBIENTES  = [(PRUEBAS, 'Pruebas'), (PRODUCCION, 'Producción')]

    # Identificación tributaria
    ruc                   = models.CharField(max_length=13)
    razon_social          = models.CharField(max_length=300)
    nombre_comercial      = models.CharField(max_length=300, blank=True)
    direccion             = models.CharField(max_length=300)
    telefono              = models.CharField(max_length=20, blank=True)
    establecimiento       = models.CharField(max_length=3, default='001')
    punto_emision         = models.CharField(max_length=3, default='001')
    ambiente              = models.CharField(max_length=15, choices=AMBIENTES, default=PRUEBAS)
    iva_porcentaje        = models.IntegerField(default=15)
    obligado_contabilidad = models.BooleanField(default=False)

    # Certificado .p12 (cifrado AES-256-GCM con SRI_P12_ENCRYPTION_KEY)
    certificado_p12       = models.TextField(blank=True)
    clave_certificado     = models.TextField(blank=True)
    cert_titular          = models.CharField(max_length=400, blank=True)
    cert_vencimiento      = models.DateTimeField(null=True, blank=True)

    # Estado
    siguiente_secuencial  = models.PositiveIntegerField(default=1)
    contingencia_activa   = models.BooleanField(default=False)

    actualizado_en        = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Configuración SRI'
        verbose_name_plural = 'Configuración SRI'

    def __str__(self):
        return f'Config SRI — {self.razon_social} ({self.ruc})'

    @classmethod
    def get_singleton(cls):
        return cls.objects.first()

    @property
    def cert_configurado(self):
        return bool(self.certificado_p12 and self.clave_certificado)


class FacturaSRI(models.Model):
    BORRADOR    = 'borrador'
    EMITIDA     = 'emitida'
    AUTORIZADA  = 'autorizada'
    RECHAZADA   = 'rechazada'
    ANULADA     = 'anulada'
    ESTADOS = [
        (BORRADOR,   'Borrador'),
        (EMITIDA,    'Emitida'),
        (AUTORIZADA, 'Autorizada'),
        (RECHAZADA,  'Rechazada'),
        (ANULADA,    'Anulada'),
    ]

    venta            = models.OneToOneField(
        'ventas.Venta', on_delete=models.SET_NULL,
        related_name='factura_sri', null=True, blank=True,
    )
    cliente          = models.ForeignKey('clientes.Cliente', on_delete=models.PROTECT)

    numero_factura   = models.CharField(max_length=20)             # 001-001-000000001
    clave_acceso     = models.CharField(max_length=49, unique=True, blank=True, null=True)

    fecha_emision    = models.DateField()
    ambiente         = models.CharField(max_length=15, default='pruebas')
    estado           = models.CharField(max_length=15, choices=ESTADOS, default=BORRADOR)

    subtotal_0       = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    subtotal_iva     = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    iva_porcentaje   = models.IntegerField(default=15)
    iva_valor        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total            = models.DecimalField(max_digits=12, decimal_places=2)

    xml_firmado             = models.TextField(blank=True)
    sri_numero_autorizacion = models.CharField(max_length=80, blank=True)
    sri_fecha_autorizacion  = models.DateTimeField(null=True, blank=True)
    sri_respuesta           = models.TextField(blank=True)
    sri_intentos_recepcion  = models.IntegerField(default=0)
    es_contingencia         = models.BooleanField(default=False)

    creada_por       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    creada_en        = models.DateTimeField(auto_now_add=True)
    actualizada_en   = models.DateTimeField(auto_now=True)
    notas            = models.TextField(blank=True)

    class Meta:
        verbose_name        = 'Factura SRI'
        verbose_name_plural = 'Facturas SRI'
        ordering            = ['-creada_en']
        indexes = [
            models.Index(fields=['estado']),
            models.Index(fields=['clave_acceso']),
            models.Index(fields=['cliente', 'estado']),
        ]

    def __str__(self):
        return f'Factura {self.numero_factura} — {self.cliente.nombre} — ${self.total}'


class ItemFacturaSRI(models.Model):
    factura          = models.ForeignKey(FacturaSRI, on_delete=models.CASCADE, related_name='items')
    orden            = models.PositiveIntegerField()
    descripcion      = models.CharField(max_length=300)
    cantidad         = models.DecimalField(max_digits=10, decimal_places=4, default=1)
    precio_unitario  = models.DecimalField(max_digits=10, decimal_places=4)
    descuento        = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    aplica_iva       = models.BooleanField(default=True)
    subtotal         = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ['orden']
