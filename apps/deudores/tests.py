from decimal import Decimal
from django.test import TestCase
from apps.usuarios.models import Usuario
from apps.clientes.models import Cliente
from apps.inventario.models import Producto
from apps.deudores.models import Adelanto, Deuda, Pago
from apps.deudores.services import (
    crear_adelanto,
    registrar_abono_adelanto,
    completar_adelanto,
    cancelar_adelanto,
    crear_venta_credito,
    registrar_abono_deuda,
    saldar_deuda,
    condonar_deuda,
)
from apps.deudores.exceptions import (
    SaldoInsuficienteError,
    AbonoExcedeSaldoError,
    EstadoInvalidoError,
    StockInsuficienteError,
    PermisoInsuficienteError,
)


class BaseTestCase(TestCase):
    def setUp(self):
        self.dueno = Usuario.objects.create_user(
            username='dueno', password='pass', rol=Usuario.ROL_DUENO
        )
        self.vendedor = Usuario.objects.create_user(
            username='vendedor', password='pass', rol=Usuario.ROL_VENDEDOR
        )
        self.cliente = Cliente.objects.create(
            nombre='María Pérez', cedula_ruc='1710034065'
        )
        self.producto = Producto.objects.create(
            nombre='Blusa manga larga', talla='M', color='Blanco',
            precio=Decimal('28.00'), stock=10
        )


class CrearAdelantoTest(BaseTestCase):

    def test_crea_adelanto_correctamente(self):
        items = [{'producto_id': self.producto.id, 'cantidad': 2}]
        adelanto = crear_adelanto(
            cliente_id=self.cliente.id,
            items=items,
            monto_inicial=Decimal('20.00'),
            fecha_limite=None,
            vendedor=self.vendedor,
        )
        self.assertEqual(adelanto.estado, Adelanto.ACTIVO)
        self.assertEqual(adelanto.total, Decimal('56.00'))
        self.assertEqual(adelanto.saldo_pendiente, Decimal('36.00'))

    def test_respeta_precio_unitario_del_pos(self):
        """Regresion: el precio que se ajusta en el POS (entre min y max)
        debe usarse para el total del apartado y para AdelantoItem, NO el
        precio base del producto. Bug 2026-05-24."""
        # producto.precio = 28.00. POS manda 32.50.
        items = [{
            'producto_id': self.producto.id,
            'cantidad': 2,
            'precio_unitario': '32.50',
        }]
        adelanto = crear_adelanto(
            cliente_id=self.cliente.id,
            items=items,
            monto_inicial=Decimal('0'),
            fecha_limite=None,
            vendedor=self.vendedor,
        )
        # Total = 32.50 * 2 = 65.00 (NO 28 * 2 = 56)
        self.assertEqual(adelanto.total, Decimal('65.00'))
        # El item registrado debe tener el precio del POS
        item = adelanto.items.first()
        self.assertEqual(item.precio_unitario, Decimal('32.50'))

    def test_reserva_stock_al_crear(self):
        items = [{'producto_id': self.producto.id, 'cantidad': 3}]
        crear_adelanto(
            cliente_id=self.cliente.id,
            items=items,
            monto_inicial=Decimal('10.00'),
            fecha_limite=None,
            vendedor=self.vendedor,
        )
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_reservado, 3)

    def test_falla_si_stock_insuficiente(self):
        items = [{'producto_id': self.producto.id, 'cantidad': 99}]
        with self.assertRaises(StockInsuficienteError):
            crear_adelanto(
                cliente_id=self.cliente.id,
                items=items,
                monto_inicial=Decimal('10.00'),
                fecha_limite=None,
                vendedor=self.vendedor,
            )

    def test_falla_si_monto_inicial_mayor_a_total(self):
        items = [{'producto_id': self.producto.id, 'cantidad': 1}]
        with self.assertRaises(SaldoInsuficienteError):
            crear_adelanto(
                cliente_id=self.cliente.id,
                items=items,
                monto_inicial=Decimal('999.00'),
                fecha_limite=None,
                vendedor=self.vendedor,
            )


class RegistrarAbonoAdelantoTest(BaseTestCase):

    def setUp(self):
        super().setUp()
        items = [{'producto_id': self.producto.id, 'cantidad': 1}]
        self.adelanto = crear_adelanto(
            cliente_id=self.cliente.id,
            items=items,
            monto_inicial=Decimal('10.00'),
            fecha_limite=None,
            vendedor=self.vendedor,
        )

    def test_abono_reduce_saldo(self):
        saldo_antes = self.adelanto.saldo_pendiente
        registrar_abono_adelanto(self.adelanto.id, Decimal('5.00'), 'efectivo', self.vendedor)
        self.adelanto.refresh_from_db()
        self.assertEqual(self.adelanto.saldo_pendiente, saldo_antes - Decimal('5.00'))

    def test_abono_crea_registro_pago(self):
        registrar_abono_adelanto(self.adelanto.id, Decimal('5.00'), 'efectivo', self.vendedor)
        pago = Pago.objects.filter(tipo=Pago.TIPO_ADELANTO, referencia_id=self.adelanto.id).last()
        self.assertEqual(pago.monto, Decimal('5.00'))
        self.assertEqual(pago.vendedor, self.vendedor)

    def test_abono_no_puede_exceder_saldo(self):
        with self.assertRaises(AbonoExcedeSaldoError):
            registrar_abono_adelanto(self.adelanto.id, Decimal('9999.00'), 'efectivo', self.vendedor)

    def test_abono_en_adelanto_cancelado_falla(self):
        cancelar_adelanto(self.adelanto.id, 'prueba', self.dueno)
        with self.assertRaises(EstadoInvalidoError):
            registrar_abono_adelanto(self.adelanto.id, Decimal('5.00'), 'efectivo', self.vendedor)


class CompletarAdelantoTest(BaseTestCase):

    def setUp(self):
        super().setUp()
        items = [{'producto_id': self.producto.id, 'cantidad': 2}]
        self.adelanto = crear_adelanto(
            cliente_id=self.cliente.id,
            items=items,
            monto_inicial=Decimal('56.00'),
            fecha_limite=None,
            vendedor=self.vendedor,
        )

    def test_completar_adelanto_saldado_crea_venta(self):
        venta = completar_adelanto(self.adelanto.id, self.vendedor)
        self.assertIsNotNone(venta)
        self.adelanto.refresh_from_db()
        self.assertEqual(self.adelanto.estado, Adelanto.COMPLETADO)

    def test_completar_descuenta_stock(self):
        completar_adelanto(self.adelanto.id, self.vendedor)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 8)
        self.assertEqual(self.producto.stock_reservado, 0)

    def test_completar_con_saldo_pendiente_falla(self):
        items = [{'producto_id': self.producto.id, 'cantidad': 1}]
        adelanto_incompleto = crear_adelanto(
            cliente_id=self.cliente.id,
            items=items,
            monto_inicial=Decimal('5.00'),
            fecha_limite=None,
            vendedor=self.vendedor,
        )
        with self.assertRaises(SaldoInsuficienteError):
            completar_adelanto(adelanto_incompleto.id, self.vendedor)


class CancelarAdelantoTest(BaseTestCase):

    def setUp(self):
        super().setUp()
        items = [{'producto_id': self.producto.id, 'cantidad': 2}]
        self.adelanto = crear_adelanto(
            cliente_id=self.cliente.id,
            items=items,
            monto_inicial=Decimal('30.00'),
            fecha_limite=None,
            vendedor=self.vendedor,
        )

    def test_cancelar_libera_stock_reservado(self):
        cancelar_adelanto(self.adelanto.id, 'cliente no vino', self.dueno)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_reservado, 0)

    def test_cancelar_genera_credito_a_favor(self):
        cancelar_adelanto(self.adelanto.id, 'cliente no vino', self.dueno)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.saldo_a_favor, Decimal('30.00'))

    def test_cancelar_cambia_estado(self):
        cancelar_adelanto(self.adelanto.id, 'motivo', self.dueno)
        self.adelanto.refresh_from_db()
        self.assertEqual(self.adelanto.estado, Adelanto.CANCELADO)

    def test_solo_dueno_puede_cancelar(self):
        with self.assertRaises(PermisoInsuficienteError):
            cancelar_adelanto(self.adelanto.id, 'motivo', self.vendedor)


class CrearVentaCreditoTest(BaseTestCase):

    def test_crea_deuda_y_descuenta_stock(self):
        items = [{'producto_id': self.producto.id, 'cantidad': 2}]
        deuda = crear_venta_credito(
            cliente_id=self.cliente.id,
            items=items,
            plazo_dias=30,
            vendedor=self.vendedor,
        )
        self.assertEqual(deuda.estado, Deuda.PENDIENTE)
        self.assertEqual(deuda.monto_original, Decimal('56.00'))
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 8)

    def test_falla_si_stock_insuficiente(self):
        items = [{'producto_id': self.producto.id, 'cantidad': 99}]
        with self.assertRaises(StockInsuficienteError):
            crear_venta_credito(
                cliente_id=self.cliente.id,
                items=items,
                plazo_dias=30,
                vendedor=self.vendedor,
            )


class RegistrarAbonoDeudaTest(BaseTestCase):

    def setUp(self):
        super().setUp()
        items = [{'producto_id': self.producto.id, 'cantidad': 1}]
        self.deuda = crear_venta_credito(
            cliente_id=self.cliente.id,
            items=items,
            plazo_dias=30,
            vendedor=self.vendedor,
        )

    def test_abono_reduce_saldo(self):
        registrar_abono_deuda(self.deuda.id, Decimal('10.00'), 'efectivo', self.vendedor)
        self.deuda.refresh_from_db()
        self.assertEqual(self.deuda.saldo_pendiente, Decimal('18.00'))

    def test_abono_exacto_salda_deuda(self):
        registrar_abono_deuda(self.deuda.id, Decimal('28.00'), 'efectivo', self.vendedor)
        self.deuda.refresh_from_db()
        self.assertEqual(self.deuda.estado, Deuda.SALDADA)

    def test_abono_excede_saldo_falla(self):
        with self.assertRaises(AbonoExcedeSaldoError):
            registrar_abono_deuda(self.deuda.id, Decimal('9999.00'), 'efectivo', self.vendedor)


class CondonarDeudaTest(BaseTestCase):

    def setUp(self):
        super().setUp()
        items = [{'producto_id': self.producto.id, 'cantidad': 1}]
        self.deuda = crear_venta_credito(
            cliente_id=self.cliente.id,
            items=items,
            plazo_dias=30,
            vendedor=self.vendedor,
        )

    def test_dueno_puede_condonar(self):
        condonar_deuda(self.deuda.id, 'cliente en mal estado', self.dueno)
        self.deuda.refresh_from_db()
        self.assertEqual(self.deuda.estado, Deuda.CONDONADA)

    def test_vendedor_no_puede_condonar(self):
        with self.assertRaises(PermisoInsuficienteError):
            condonar_deuda(self.deuda.id, 'motivo', self.vendedor)
