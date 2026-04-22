from django.test import TestCase, Client
from django.urls import reverse
from .models import Usuario


class RolesModeloTest(TestCase):

    def setUp(self):
        self.dueno = Usuario.objects.create_user(
            username='dueno_test', password='pass', rol=Usuario.ROL_DUENO
        )
        self.vendedor = Usuario.objects.create_user(
            username='vendedor_test', password='pass', rol=Usuario.ROL_VENDEDOR
        )
        self.bodeguero = Usuario.objects.create_user(
            username='bodeguero_test', password='pass', rol=Usuario.ROL_BODEGUERO
        )

    def test_es_dueno(self):
        self.assertTrue(self.dueno.es_dueno())
        self.assertFalse(self.vendedor.es_dueno())
        self.assertFalse(self.bodeguero.es_dueno())

    def test_es_vendedor(self):
        self.assertTrue(self.vendedor.es_vendedor())
        self.assertFalse(self.dueno.es_vendedor())

    def test_es_bodeguero(self):
        self.assertTrue(self.bodeguero.es_bodeguero())
        self.assertFalse(self.dueno.es_bodeguero())

    def test_puede_acceder_deudores(self):
        self.assertTrue(self.dueno.puede_acceder_deudores())
        self.assertTrue(self.vendedor.puede_acceder_deudores())
        self.assertFalse(self.bodeguero.puede_acceder_deudores())


class LoginTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.usuario = Usuario.objects.create_user(
            username='user_login', password='clave123', rol=Usuario.ROL_VENDEDOR
        )

    def test_login_correcto_redirige_a_dashboard(self):
        resp = self.client.post(reverse('login'), {
            'username': 'user_login', 'password': 'clave123'
        })
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/dashboard/', resp['Location'])

    def test_login_incorrecto_muestra_error(self):
        resp = self.client.post(reverse('login'), {
            'username': 'user_login', 'password': 'incorrecta'
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'incorrectos')

    def test_usuario_autenticado_redirige_desde_login(self):
        self.client.login(username='user_login', password='clave123')
        resp = self.client.get(reverse('login'))
        self.assertEqual(resp.status_code, 302)
