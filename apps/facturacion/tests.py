from unittest.mock import call, patch

from django.test import TestCase

from apps.facturacion.services.sri import sri_client


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
