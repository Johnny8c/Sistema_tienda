from django.test import TestCase
from .services import validar_cedula_ecuador, validar_ruc_persona_natural, validar_cedula_o_ruc


class ValidacionCedulaTest(TestCase):

    def test_cedula_valida(self):
        # Cédulas válidas reales de Ecuador
        self.assertTrue(validar_cedula_ecuador('1710034065'))
        self.assertTrue(validar_cedula_ecuador('0926687856'))

    def test_cedula_invalida_digito_verificador(self):
        self.assertFalse(validar_cedula_ecuador('1710034060'))

    def test_cedula_invalida_longitud(self):
        self.assertFalse(validar_cedula_ecuador('171003406'))
        self.assertFalse(validar_cedula_ecuador('17100340650'))

    def test_cedula_invalida_provincia(self):
        self.assertFalse(validar_cedula_ecuador('2510034065'))

    def test_cedula_invalida_no_numerica(self):
        self.assertFalse(validar_cedula_ecuador('171003406A'))

    def test_cedula_vacia(self):
        self.assertFalse(validar_cedula_ecuador(''))


class ValidacionRucTest(TestCase):

    def test_ruc_persona_natural_valido(self):
        self.assertTrue(validar_ruc_persona_natural('1710034065001'))

    def test_ruc_persona_natural_invalido_sin_001(self):
        self.assertFalse(validar_ruc_persona_natural('1710034065002'))

    def test_ruc_invalido_longitud(self):
        self.assertFalse(validar_cedula_o_ruc('123'))

    def test_cedula_o_ruc_acepta_cedula(self):
        self.assertTrue(validar_cedula_o_ruc('1710034065'))

    def test_cedula_o_ruc_acepta_ruc(self):
        self.assertTrue(validar_cedula_o_ruc('1710034065001'))

    def test_cedula_o_ruc_rechaza_invalido(self):
        self.assertFalse(validar_cedula_o_ruc('0000000000'))
