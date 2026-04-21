from django.db import models


class Cliente(models.Model):
    nombre = models.CharField(max_length=200)
    cedula_ruc = models.CharField(max_length=13, unique=True)
    telefono = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    direccion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'
        indexes = [
            models.Index(fields=['cedula_ruc']),
        ]

    def __str__(self):
        return f'{self.nombre} ({self.cedula_ruc})'
