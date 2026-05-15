from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    ROL_DUENO = 'dueno'
    ROL_VENDEDOR = 'vendedor'
    ROL_BODEGUERO = 'bodeguero'

    ROLES = [
        (ROL_DUENO, 'Dueño'),
        (ROL_VENDEDOR, 'Vendedor'),
        (ROL_BODEGUERO, 'Bodeguero'),
    ]

    rol = models.CharField(max_length=20, choices=ROLES, default=ROL_VENDEDOR)
    cedula = models.CharField(max_length=20, blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    direccion = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def es_dueno(self):
        return self.rol == self.ROL_DUENO

    def es_vendedor(self):
        return self.rol == self.ROL_VENDEDOR

    def es_bodeguero(self):
        return self.rol == self.ROL_BODEGUERO

    def puede_acceder_deudores(self):
        return self.rol in (self.ROL_DUENO, self.ROL_VENDEDOR)

    def puede_gestionar_inventario(self):
        """Dueño + bodeguero pueden modificar el inventario."""
        return self.rol in (self.ROL_DUENO, self.ROL_BODEGUERO)

    def puede_registrar_compras(self):
        """Dueño + bodeguero pueden ver y registrar compras (recibir mercadería)."""
        return self.rol in (self.ROL_DUENO, self.ROL_BODEGUERO)
