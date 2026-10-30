from types import SimpleNamespace

from django.contrib.admin.sites import AdminSite
from django.test import SimpleTestCase

from helpdesk.admin import TicketAdmin
from helpdesk.models import Ticket


class HiddenSubmitterEmailTestCase(SimpleTestCase):
    def setUp(self):
        self.model_admin = TicketAdmin(Ticket, AdminSite())

    def mask(self, email):
        """Chama o método sob teste com um "ticket" que só tem o e-mail."""
        return self.model_admin.hidden_submitter_email(
            SimpleNamespace(submitter_email=email)
        )

    # CT1 - CV1: um único "@"
    def test_once_at_sign_masked_email(self):
        self.assertEqual(self.mask("angelo@gmail.com"), "an****@g*******m")

    # CT2 - CI2: mais de um "@"
    def test_multiple_at_sign_masked_email(self):
        with self.assertRaises(ValueError):
            self.mask("ange@lo@email.com")

    # CT3 - CI1: nenhum "@"
    def test_email_without_at_sign(self):
        with self.assertRaises(ValueError):
            self.mask("Unknown Sender")

    # CT4 - CV2, CV3: mínimo de 3 caracteres no username e no domínio
    def test_masked_email(self):
        self.assertEqual(self.mask("abc@email.com"), "ab*@e*******m")

    # CT5 - CI3: username com menos de 3 caracteres
    def test_short_username_masked_email(self):
        self.assertEqual(self.mask("an@gmail.com"), "an@g*******m")

    # CT6 - CI4: domínio com menos de 3 caracteres
    def test_short_domain_masked_email(self):
        self.assertEqual(self.mask("teste@om"), "te***@om")

    # CT7 - CV4: e-mail vazio
    def test_empty_email(self):
        self.assertEqual(self.mask(""), "")

    # CT8 - CV5: sem e-mail
    def test_none_email(self):
        self.assertIsNone(self.mask(None))
