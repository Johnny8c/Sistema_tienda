"""Regresión de zona horaria en reportes diarios.

El contenedor corre en UTC y Ecuador es UTC-5: entre las 19:00 y las 23:59
locales, la fecha UTC ya es "mañana". Calcular "hoy" con now().date() hacía
que el cierre de caja saliera vacío en la noche y que las ventas nocturnas
aparecieran en el día equivocado.
"""
from datetime import date, datetime, timezone as dt_tz
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.ventas.models import Venta
from .views import _hoy

Usuario = get_user_model()

# 12-jun 01:30 UTC == 11-jun 20:30 en America/Guayaquil
NOCHE_EN_ECUADOR = datetime(2026, 6, 12, 1, 30, tzinfo=dt_tz.utc)


# Storage simple en tests: el manifest de whitenoise exige collectstatic
# actualizado y rompe el render de páginas completas (mismo patrón que en
# apps/inventario/tests.py).
@override_settings(STORAGES={
    'default':     {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class FechaLocalReportesTest(TestCase):

    def setUp(self):
        self.user = Usuario.objects.create_user(
            username='test_dueno_tz', password='x', rol=Usuario.ROL_DUENO,
        )
        self.client.force_login(self.user)

    def test_hoy_es_fecha_de_ecuador_no_utc(self):
        with mock.patch('django.utils.timezone.now', return_value=NOCHE_EN_ECUADOR):
            self.assertEqual(
                _hoy(), date(2026, 6, 11),
                'A las 20:30 de Ecuador los reportes deben seguir en el 11-jun, '
                'no saltar al 12-jun (fecha UTC)',
            )

    def test_venta_nocturna_cuenta_en_el_cierre_del_dia_local(self):
        """Una venta a las 20:30 (hora Ecuador) debe aparecer en el cierre de
        caja del MISMO día, consultado esa misma noche."""
        venta = Venta.objects.create(
            total=Decimal('25.00'), vendedor=self.user,
            tipo_pago=Venta.CONTADO,
        )
        # auto_now_add ignora el valor pasado al crear: fijar la fecha después
        Venta.objects.filter(pk=venta.pk).update(fecha=NOCHE_EN_ECUADOR)

        with mock.patch('django.utils.timezone.now', return_value=NOCHE_EN_ECUADOR):
            r = self.client.get(reverse('cierre_caja'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            r.context['fecha'], date(2026, 6, 11),
            'El cierre de caja sin fecha explícita debe abrir el día local',
        )
        self.assertEqual(
            r.context['total_contado'], Decimal('25.00'),
            'La venta de las 20:30 no aparece en el cierre de su propio día',
        )
