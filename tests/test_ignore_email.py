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

    def test_c03_extrair_endereco(self):  # quando remetente tiver nome de exibicao
        regra = IgnoreEmail(email_address="spam@dominio.com")

        resultado = regra.test("João Silva <spam@dominio.com>")

        self.assertTrue(resultado)

    def test_c04_curinga_no_final_do_username(self):
        regra = IgnoreEmail(email_address="username*@email.com")
        resultado = regra.test("username_noreply@email.com")
        self.assertTrue(resultado)

    def test_c05_curinga_no_inicio_do_username(self):
        regra = IgnoreEmail(email_address="*_noreply@email.com")
        resultado = regra.test("empresa_noreply@email.com")
        self.assertTrue(resultado)

    def test_c06_curinga_no_inicio_e_final_do_username(self):
        regra = IgnoreEmail(email_address="*_username_*@email.com")
        resultado = regra.test("joao_username_silva@email.com")
        self.assertTrue(resultado)

    def test_c07_curinga_no_inicio_do_dominio(self):
        regra = IgnoreEmail(email_address="*@*.empresa.com")

        resultado = regra.test("joao@mail.empresa.com")

        self.assertTrue(resultado)
        self.assertTrue(regra.test("joao@a.b.empresa.com"))
        self.assertFalse(regra.test("joao@empresa.com"))
        self.assertFalse(regra.test("joao@fakeempresa.com"))
        self.assertFalse(regra.test("joao@mail.outra.com"))

    def test_c08_curinga_no_final_e_no_meio_do_dominio(self):
        regra_fim = IgnoreEmail(email_address="*@empresa.*")
        regra_meio = IgnoreEmail(email_address="*@mail.*.com")

        resultado = regra_fim.test("joao@empresa.com.br")

        self.assertTrue(resultado)
        self.assertTrue(regra_fim.test("joao@empresa.org"))
        self.assertFalse(regra_fim.test("joao@outraempresa.com"))
        self.assertTrue(regra_meio.test("joao@mail.sp.com"))
        self.assertFalse(regra_meio.test("joao@mail.sp.org"))
        self.assertFalse(regra_meio.test("joao@mail.com"))
