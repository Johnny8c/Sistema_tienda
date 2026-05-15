"""
Tests end-to-end de los 4 flujos principales del módulo Deudores y Adelantos.
Usan el cliente de test de Django para recorrer vistas reales.
"""
import json

from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse

from apps.usuarios.models import Usuario
from apps.clientes.models import Cliente
from apps.inventario.models import Producto
from apps.deudores.models import Adelanto, Deuda, Pago
from apps.ventas.models import Venta
from apps.deudores.services import crear_adelanto, crear_venta_credito


class BaseE2ETestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.dueno = Usuario.objects.create_user(
            username='dueno_e2e', password='pass123', rol=Usuario.ROL_DUENO
        )
        self.vendedor = Usuario.objects.create_user(
            username='vendedor_e2e', password='pass123', rol=Usuario.ROL_VENDEDOR
        )
        self.bodeguero = Usuario.objects.create_user(
            username='bodeguero_e2e', password='pass123', rol=Usuario.ROL_BODEGUERO
        )
        self.cliente = Cliente.objects.create(
            nombre='Ana Torres', cedula_ruc='1710034065'
        )
        self.producto = Producto.objects.create(
            nombre='Pantalón casual', talla='32', color='Negro',
            precio=Decimal('45.00'), stock=20
        )


class FlujoPosContadoTest(BaseE2ETestCase):
    def test_pos_contado_acepta_precio_con_coma(self):
        self.client.login(username='vendedor_e2e', password='pass123')

        resp = self.client.post(reverse('procesar_venta'), {
            'tipo_venta': 'contado',
            'cliente_id': str(self.cliente.pk),
            'forma_pago': 'efectivo',
            'emitir_factura': '1',
            'items_json': json.dumps([{
                'producto_id': self.producto.pk,
                'cantidad': 2,
                'precio_unitario': '10,50',
            }]),
        })

        self.assertEqual(resp.status_code, 302)

        venta = Venta.objects.get(tipo_pago=Venta.CONTADO)
        self.producto.refresh_from_db()

        self.assertEqual(venta.total, Decimal('21.00'))
        self.assertEqual(self.producto.stock, 18)


class FlujoApartarCompletarTest(BaseE2ETestCase):
    """Flujo A: Apartar → abonar → completar → stock descontado y venta creada."""

    def test_flujo_completo_apartado(self):
        items = [{'producto_id': self.producto.id, 'cantidad': 2}]

        # 1. Crear adelanto ($90 total, $40 inicial)
        adelanto = crear_adelanto(
            cliente_id=self.cliente.id,
            items=items,
            monto_inicial=Decimal('40.00'),
            fecha_limite=None,
            vendedor=self.vendedor,
        )
        self.assertEqual(adelanto.estado, Adelanto.ACTIVO)
        self.assertEqual(adelanto.saldo_pendiente, Decimal('50.00'))

        # Stock reservado, no descontado
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 20)
        self.assertEqual(self.producto.stock_reservado, 2)

        # 2. Abonar el saldo restante vía vista
        self.client.login(username='vendedor_e2e', password='pass123')
        resp = self.client.post(
            reverse('abonar_adelanto', args=[adelanto.pk]),
            {'monto': '50.00', 'forma_pago': 'efectivo'}
        )
        self.assertEqual(resp.status_code, 302)

        adelanto.refresh_from_db()
        self.assertEqual(adelanto.saldo_pendiente, Decimal('0.00'))

        # 3. Completar el apartado vía vista (solo cuando saldo = 0)
        resp = self.client.post(reverse('completar_adelanto', args=[adelanto.pk]))
        self.assertEqual(resp.status_code, 302)

        adelanto.refresh_from_db()
        self.assertEqual(adelanto.estado, Adelanto.COMPLETADO)

        # Stock descontado definitivamente
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 18)
        self.assertEqual(self.producto.stock_reservado, 0)

        # Venta creada
        venta = Venta.objects.get(tipo_pago=Venta.ADELANTO_COMPLETADO)
        self.assertEqual(venta.total, Decimal('90.00'))
        self.assertEqual(venta.cliente, self.cliente)

        # Pagos registrados: 1 inicial + 1 abono = 2
        pagos = Pago.objects.filter(tipo=Pago.TIPO_ADELANTO, referencia_id=adelanto.pk)
        self.assertEqual(pagos.count(), 2)
        self.assertEqual(sum(p.monto for p in pagos), Decimal('90.00'))


class FlujoApartarCancelarTest(BaseE2ETestCase):
    """Flujo B: Apartar → abonar → cancelar → stock liberado y crédito a favor."""

    def test_cancelar_genera_credito_y_libera_stock(self):
        items = [{'producto_id': self.producto.id, 'cantidad': 3}]
        adelanto = crear_adelanto(
            cliente_id=self.cliente.id,
            items=items,
            monto_inicial=Decimal('60.00'),
            fecha_limite=None,
            vendedor=self.vendedor,
        )

        # Stock reservado
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_reservado, 3)

        # Solo el dueño puede cancelar
        self.client.login(username='dueno_e2e', password='pass123')
        resp = self.client.post(
            reverse('cancelar_adelanto', args=[adelanto.pk]),
            {'motivo': 'Cliente no volvió'}
        )
        self.assertEqual(resp.status_code, 302)

        adelanto.refresh_from_db()
        self.assertEqual(adelanto.estado, Adelanto.CANCELADO)

        # Stock liberado
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_reservado, 0)

        # Crédito a favor (lo que pagó: $60)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.saldo_a_favor, Decimal('60.00'))


class FlujoCreditoAbonarSaldarTest(BaseE2ETestCase):
    """Flujo C: Venta a crédito → abonar parcial → abonar resto → saldada."""

    def test_venta_credito_abonos_hasta_saldar(self):
        items = [{'producto_id': self.producto.id, 'cantidad': 1}]
        deuda = crear_venta_credito(
            cliente_id=self.cliente.id,
            items=items,
            plazo_dias=30,
            vendedor=self.vendedor,
        )

        # Stock descontado inmediatamente
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 19)
        self.assertEqual(deuda.monto_original, Decimal('45.00'))
        self.assertEqual(deuda.estado, Deuda.PENDIENTE)

        self.client.login(username='vendedor_e2e', password='pass123')

        # Abono parcial 1
        resp = self.client.post(
            reverse('abonar_deuda', args=[deuda.pk]),
            {'monto': '20.00', 'forma_pago': 'efectivo'}
        )
        self.assertEqual(resp.status_code, 302)
        deuda.refresh_from_db()
        self.assertEqual(deuda.saldo_pendiente, Decimal('25.00'))
        self.assertEqual(deuda.estado, Deuda.PENDIENTE)

        # Abono parcial 2 — salda la deuda
        resp = self.client.post(
            reverse('abonar_deuda', args=[deuda.pk]),
            {'monto': '25.00', 'forma_pago': 'transferencia'}
        )
        self.assertEqual(resp.status_code, 302)
        deuda.refresh_from_db()
        self.assertEqual(deuda.saldo_pendiente, Decimal('0.00'))
        self.assertEqual(deuda.estado, Deuda.SALDADA)

        # Total pagos = monto original
        total_pagado = Pago.objects.filter(
            tipo=Pago.TIPO_DEUDA, referencia_id=deuda.pk
        ).aggregate(t=__import__('django.db.models', fromlist=['Sum']).Sum('monto'))['t']
        self.assertEqual(total_pagado, Decimal('45.00'))


class FlujoCondonarTest(BaseE2ETestCase):
    """Flujo D: Venta a crédito → condonar → solo dueño puede."""

    def test_vendedor_no_puede_condonar(self):
        items = [{'producto_id': self.producto.id, 'cantidad': 1}]
        deuda = crear_venta_credito(
            cliente_id=self.cliente.id,
            items=items,
            plazo_dias=30,
            vendedor=self.vendedor,
        )

        # Vendedor intenta condonar → redirige con error (permiso denegado)
        self.client.login(username='vendedor_e2e', password='pass123')
        resp = self.client.post(
            reverse('condonar_deuda', args=[deuda.pk]),
            {'motivo': 'intento vendedor'}
        )
        # Debe redirigir al dashboard por el decorador requiere_dueno
        self.assertEqual(resp.status_code, 302)
        deuda.refresh_from_db()
        self.assertNotEqual(deuda.estado, Deuda.CONDONADA)

    def test_dueno_puede_condonar(self):
        items = [{'producto_id': self.producto.id, 'cantidad': 1}]
        deuda = crear_venta_credito(
            cliente_id=self.cliente.id,
            items=items,
            plazo_dias=30,
            vendedor=self.vendedor,
        )

        self.client.login(username='dueno_e2e', password='pass123')
        resp = self.client.post(
            reverse('condonar_deuda', args=[deuda.pk]),
            {'motivo': 'Acuerdo con el cliente'}
        )
        self.assertEqual(resp.status_code, 302)
        deuda.refresh_from_db()
        self.assertEqual(deuda.estado, Deuda.CONDONADA)


class PermisosTest(BaseE2ETestCase):
    """Tests de control de acceso por rol."""

    def _login(self, user):
        self.client.login(username=user.username, password='pass123')

    def test_bodeguero_bloqueado_en_adelantos(self):
        self._login(self.bodeguero)
        resp = self.client.get(reverse('lista_adelantos'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/dashboard/', resp['Location'])

    def test_bodeguero_bloqueado_en_deudas(self):
        self._login(self.bodeguero)
        resp = self.client.get(reverse('lista_deudas'))
        self.assertEqual(resp.status_code, 302)

    def test_bodeguero_bloqueado_en_reportes(self):
        self._login(self.bodeguero)
        resp = self.client.get(reverse('reportes'))
        self.assertEqual(resp.status_code, 302)

    def test_vendedor_bloqueado_en_reportes(self):
        self._login(self.vendedor)
        resp = self.client.get(reverse('reportes'))
        self.assertEqual(resp.status_code, 302)

    def test_vendedor_puede_ver_adelantos(self):
        self._login(self.vendedor)
        resp = self.client.get(reverse('lista_adelantos'))
        self.assertEqual(resp.status_code, 200)

    def test_vendedor_puede_ver_deudas(self):
        self._login(self.vendedor)
        resp = self.client.get(reverse('lista_deudas'))
        self.assertEqual(resp.status_code, 200)

    def test_dueno_accede_a_reportes(self):
        self._login(self.dueno)
        resp = self.client.get(reverse('reportes'))
        self.assertEqual(resp.status_code, 200)

    def test_no_autenticado_redirige_a_login(self):
        resp = self.client.get(reverse('lista_adelantos'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp['Location'])
