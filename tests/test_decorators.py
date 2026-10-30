from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseRedirect
from django.test import RequestFactory, TestCase
from django.urls import reverse

from helpdesk import settings as helpdesk_settings
from helpdesk.decorators import staff_member_required

ALLOW = "HELPDESK_ALLOW_NON_STAFF_TICKET_UPDATE"
PROTECTOR = "HELPDESK_STAFF_VIEW_PROTECTOR"


def protector_none(request):
    """Protetor que nao bloqueia ninguem (igual ao padrao do projeto)."""


def protector_blocks(request):
    return HttpResponseRedirect("/bloqueado-pelo-protetor/")


def fake_user(is_authenticated, is_active, is_staff):
    return SimpleNamespace(
        is_authenticated=is_authenticated, is_active=is_active, is_staff=is_staff
    )


class StaffMemberRequiredBase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.view_calls = []

        def view(request, *args, **kwargs):
            self.view_calls.append((request, args, kwargs))
            return HttpResponse("view executada")

        self.decorated = staff_member_required(view)

    def make_request(self, user):
        request = self.factory.get("/")
        request.user = user
        return request


class StaffMemberRequiredMCDCTests(StaffMemberRequiredBase):
    def test_wb1_nao_autenticado_e_inativo_redireciona_para_login(self):
        request = self.make_request(fake_user(False, False, False))

        response = self.decorated(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("helpdesk:login"))
        self.assertEqual(self.view_calls, [])

    @mock.patch.object(helpdesk_settings, PROTECTOR, protector_none)
    @mock.patch.object(helpdesk_settings, ALLOW, False)
    def test_wb2_autenticado_inativo_nao_staff_levanta_permission_denied(self):
        request = self.make_request(fake_user(True, False, False))

        with self.assertRaises(PermissionDenied):
            self.decorated(request)
        self.assertEqual(self.view_calls, [])

    @mock.patch.object(helpdesk_settings, PROTECTOR, protector_blocks)
    @mock.patch.object(helpdesk_settings, ALLOW, True)
    def test_wb3_nao_autenticado_mas_ativo_com_protetor_devolve_redirect(self):
        request = self.make_request(fake_user(False, True, False))

        response = self.decorated(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/bloqueado-pelo-protetor/")
        self.assertEqual(self.view_calls, [])

    @mock.patch.object(helpdesk_settings, PROTECTOR, protector_none)
    @mock.patch.object(helpdesk_settings, ALLOW, False)
    def test_wb4_autenticado_ativo_staff_executa_a_view(self):
        request = self.make_request(fake_user(True, True, True))

        response = self.decorated(request)

        self.assertEqual(response.content, b"view executada")
        self.assertEqual(len(self.view_calls), 1)


class StaffMemberRequiredBlackBoxTests(StaffMemberRequiredBase):
    @mock.patch.object(helpdesk_settings, PROTECTOR, protector_none)
    @mock.patch.object(helpdesk_settings, ALLOW, False)
    def test_bb1_usuario_anonimo_real_e_redirecionado_para_login(self):
        request = self.make_request(AnonymousUser())

        response = self.decorated(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("helpdesk:login"))
        self.assertEqual(self.view_calls, [])

    @mock.patch.object(helpdesk_settings, PROTECTOR, protector_none)
    @mock.patch.object(helpdesk_settings, ALLOW, False)
    def test_bb2_staff_ativo_acessa_e_argumentos_chegam_a_view(self):
        user = User(username="staff", is_staff=True, is_active=True)
        request = self.make_request(user)

        response = self.decorated(request, 10, "abc", ticket_id=7)

        self.assertEqual(response.content, b"view executada")
        self.assertEqual(self.view_calls, [(request, (10, "abc"), {"ticket_id": 7})])

    @mock.patch.object(helpdesk_settings, PROTECTOR, protector_none)
    @mock.patch.object(helpdesk_settings, ALLOW, False)
    def test_bb3_usuario_comum_ativo_recebe_403_com_setting_padrao(self):
        user = User(username="comum", is_staff=False, is_active=True)
        request = self.make_request(user)

        with self.assertRaises(PermissionDenied):
            self.decorated(request)
        self.assertEqual(self.view_calls, [])

    @mock.patch.object(helpdesk_settings, PROTECTOR, protector_none)
    @mock.patch.object(helpdesk_settings, ALLOW, True)
    def test_bb4_usuario_comum_ativo_acessa_quando_setting_permite(self):
        user = User(username="comum", is_staff=False, is_active=True)
        request = self.make_request(user)

        response = self.decorated(request)

        self.assertEqual(response.content, b"view executada")
        self.assertEqual(len(self.view_calls), 1)
