from decimal import Decimal

from django.test import TestCase

from apps.clientes.models import Cliente
from apps.configuracion.models import ConfiguracionGeneral
from apps.inventario.models import Producto
from apps.usuarios.models import Usuario

from .services import crear_venta_contado


class CrearVentaContadoTest(TestCase):
    def setUp(self):
        self.vendedor = Usuario.objects.create_user(
            username='vendedor_ventas', password='pass123', rol=Usuario.ROL_VENDEDOR
        )
        self.cliente = Cliente.objects.create(
            nombre='Cliente POS', cedula_ruc='1710034065'
        )
        self.producto = Producto.objects.create(
            nombre='Blusa adidas', talla='XS', color='Azul',
            precio=Decimal('12.00'), stock=10
        )
        self.cfg_gen = ConfiguracionGeneral.get_singleton()

    def test_acepta_precio_unitario_con_coma(self):
        venta = crear_venta_contado(
            items=[{
                'producto_id': self.producto.pk,
                'cantidad': 2,
                'precio_unitario': '10,50',
            }],
            cliente_id=self.cliente.pk,
            vendedor=self.vendedor,
            forma_pago='efectivo',
            cfg_gen=self.cfg_gen,
        )

        self.producto.refresh_from_db()

        self.assertEqual(venta.total, Decimal('21.00'))
        self.assertEqual(self.producto.stock, 8)
