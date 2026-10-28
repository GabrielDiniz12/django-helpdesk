from django.test import SimpleTestCase

from helpdesk.models import IgnoreEmail


class IgnoreEmailTestCase(SimpleTestCase):
    def test_c01_ignorar_email_independentemente_de_maiusculas_e_minusculas(self):
        regra = IgnoreEmail(email_address="spam@dominio.com")

        resultado = regra.test("SPAM@DOMINIO.COM")

        self.assertTrue(resultado)

    def test_c02_ignorar_espacos_em_branco_nas_extremidades(self):
        regra = IgnoreEmail(email_address="  spam@dominio.com ")

        resultado = regra.test(" spam@dominio.com  ")

        self.assertTrue(resultado)
