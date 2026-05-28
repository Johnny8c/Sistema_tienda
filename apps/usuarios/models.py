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
    # Código corto (2 dígitos, ej "01", "07") que aparece en las notas de venta
    # en lugar del nombre del vendedor. Sirve para identificación rápida en
    # tickets impresos sin exponer datos personales.
    codigo = models.CharField(max_length=2, unique=True)

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    @classmethod
    def siguiente_codigo(cls):
        """Devuelve el siguiente código de 2 dígitos disponible (01-99).
        Busca el menor número no usado, no el siguiente al máximo, así
        si borrás el 05 y tenés 01-04 + 06, te devuelve 05."""
        usados = set()
        for c in cls.objects.values_list('codigo', flat=True):
            if c and c.isdigit():
                usados.add(int(c))
        for n in range(1, 100):
            if n not in usados:
                return f'{n:02d}'
        return '99'  # fallback si llegaron a 99 usuarios

    def save(self, *args, **kwargs):
        # Auto-asignar el siguiente código si quien crea el usuario no se
        # acordó (shell, admin, tests, scripts de import). El form de
        # empleados ya valida + asigna explícitamente — esto es la red de
        # seguridad para todos los otros caminos.
        if not self.codigo:
            self.codigo = self.__class__.siguiente_codigo()
        super().save(*args, **kwargs)

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
