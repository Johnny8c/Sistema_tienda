from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import call, patch

from django.test import TestCase, override_settings

from apps.facturacion.services.sri import sri_client
from apps.facturacion.services.sri.xml_generator import generar_xml


class SriClientRetryTest(TestCase):
    def test_retry_usa_delays_personalizados(self):
        with patch(
            'apps.facturacion.services.sri.sri_client._soap_request',
            side_effect=RuntimeError('timeout'),
        ) as mock_request, patch(
            'apps.facturacion.services.sri.sri_client.time.sleep'
        ) as mock_sleep:
            result = sri_client._soap_request_retry(
                'cel.sri.gob.ec',
                '/ws',
                '<xml />',
                timeout=4,
                retry_delays=[1],
            )

        self.assertTrue(result['contingencia'])
        self.assertEqual(mock_request.call_count, 2)
        self.assertEqual(mock_sleep.call_args_list, [call(1)])


# ─────────────────────────────────────────────────────────────
# Res. NAC-DGERCGC26-00000027 — RUC del proveedor en infoAdicional
# ─────────────────────────────────────────────────────────────
def _factura_stub():
    return SimpleNamespace(
        numero_factura='001-001-000000123',
        clave_acceso='0' * 49,
        fecha_emision=date(2026, 9, 1),
        subtotal_0=Decimal('0.00'),
        subtotal_iva=Decimal('10.00'),
        iva_porcentaje=15,
        iva_valor=Decimal('1.50'),
        total=Decimal('11.50'),
    )


def _items_stub():
    return [SimpleNamespace(
        descripcion='CAMISETA',
        cantidad=Decimal('1'),
        precio_unitario=Decimal('10.00'),
        descuento=Decimal('0'),
        subtotal=Decimal('10.00'),
        aplica_iva=True,
    )]


def _config_stub():
    return SimpleNamespace(
        ambiente='pruebas',
        razon_social='NR BOUTIQUE',
        nombre_comercial='NR BOUTIQUE',
        ruc='1234567890001',
        direccion='CUENCA',
        obligado_contabilidad=False,
    )


def _cliente_stub(telefono='0999999999', email='cliente@correo.com'):
    return SimpleNamespace(
        nombre='JUAN PEREZ',
        cedula_ruc='0102030405',
        telefono=telefono,
        email=email,
    )


def _xml():
    return generar_xml(_factura_stub(), _items_stub(), _config_stub(), _cliente_stub())


class InfoAdicionalProveedorTest(TestCase):
    """Campos del proveedor del sistema exigidos/derivados de la resolucion."""

    def test_incluye_ruc_del_proveedor(self):
        self.assertIn(
            '<campoAdicional nombre="RUC Proveedor">0150137917001</campoAdicional>',
            _xml(),
        )

    def test_incluye_datos_de_contacto_del_proveedor(self):
        xml = _xml()
        self.assertIn(
            '<campoAdicional nombre="Razon Social Proveedor">'
            'JOHNNY CAIVINAGUA MOROCHO</campoAdicional>', xml)
        self.assertIn(
            '<campoAdicional nombre="Email Proveedor">'
            'leocaivinagua@gmail.com</campoAdicional>', xml)
        self.assertIn(
            '<campoAdicional nombre="Telefono Proveedor">'
            '0997303865</campoAdicional>', xml)

    def test_no_duplica_el_campo(self):
        """Idempotencia: exactamente una ocurrencia de cada campo del proveedor."""
        xml = _xml()
        for nombre in ('RUC Proveedor', 'Razon Social Proveedor',
                       'Email Proveedor', 'Telefono Proveedor'):
            self.assertEqual(
                xml.count(f'<campoAdicional nombre="{nombre}">'), 1,
                f'{nombre} aparece duplicado',
            )

    def test_no_pisa_el_ruc_del_emisor_ni_del_comprador(self):
        """El RUC del proveedor no debe contaminar infoTributaria ni el comprador."""
        xml = _xml()
        self.assertIn('<ruc>1234567890001</ruc>', xml)
        self.assertIn('<identificacionComprador>0102030405</identificacionComprador>', xml)
        self.assertNotIn('<ruc>0150137917001</ruc>', xml)

    def test_respeta_el_orden_del_xsd(self):
        """infoAdicional sigue al final, despues de detalles, y cierra el comprobante."""
        xml = _xml()
        self.assertLess(xml.index('</detalles>'), xml.index('<infoAdicional>'))
        self.assertTrue(xml.endswith('</infoAdicional></factura>'))

    def test_no_supera_el_maximo_de_15_campos(self):
        self.assertLessEqual(_xml().count('<campoAdicional '), 15)

    @override_settings(SRI_MAX_CAMPOS_ADICIONALES=1)
    def test_al_recortar_sobrevive_el_campo_obligatorio(self):
        """Si hubiera que recortar, el RUC del proveedor nunca se descarta."""
        xml = _xml()
        self.assertEqual(xml.count('<campoAdicional '), 1)
        self.assertIn(
            '<campoAdicional nombre="RUC Proveedor">0150137917001</campoAdicional>', xml)

    @override_settings(SRI_PROVEEDOR_TELEFONO='', SRI_PROVEEDOR_EMAIL='')
    def test_campos_vacios_se_omiten(self):
        xml = _xml()
        self.assertNotIn('Telefono Proveedor', xml)
        self.assertNotIn('Email Proveedor', xml)
        self.assertIn('nombre="RUC Proveedor"', xml)

    @override_settings(SRI_PROVEEDOR_CAMPO_RUC='RUC del Proveedor')
    def test_el_literal_del_campo_es_configurable(self):
        """Blindaje: si el SRI define otro nombre, se cambia por config."""
        xml = _xml()
        self.assertIn('<campoAdicional nombre="RUC del Proveedor">', xml)
        self.assertNotIn('nombre="RUC Proveedor"', xml)

    def test_no_altera_totales_ni_clave_de_acceso(self):
        """Regresion: el cambio no toca nada de la logica fiscal."""
        xml = _xml()
        self.assertIn(f'<claveAcceso>{"0" * 49}</claveAcceso>', xml)
        self.assertIn('<importeTotal>11.50</importeTotal>', xml)
        self.assertIn('<totalSinImpuestos>10.00</totalSinImpuestos>', xml)
        self.assertIn('<propina>0.00</propina>', xml)

    def test_conserva_los_campos_del_cliente(self):
        xml = _xml()
        self.assertIn('<campoAdicional nombre="Telefono">0999999999</campoAdicional>', xml)
        self.assertIn('<campoAdicional nombre="Email">cliente@correo.com</campoAdicional>', xml)
        self.assertIn(
            '<campoAdicional nombre="NumeroFactura">001-001-000000123</campoAdicional>', xml)

    def test_xml_es_parseable(self):
        """El XML sigue siendo bien formado con los campos nuevos."""
        from xml.etree import ElementTree
        root = ElementTree.fromstring(_xml())
        nombres = [e.get('nombre') for e in root.find('infoAdicional')]
        self.assertIn('RUC Proveedor', nombres)
        self.assertEqual(len(nombres), len(set(nombres)))
