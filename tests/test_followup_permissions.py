from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase

from helpdesk import settings as helpdesk_settings
from helpdesk.models import FollowUp
from helpdesk.templatetags.followup_permissions import can_edit_followup

User = get_user_model()


class FollowUpPermissionsTests(SimpleTestCase):

    def setUp(self):
        self.author = User(id=1, username="author_user", is_superuser=False)
        self.superuser = User(id=2, username="super_user", is_superuser=True)
        self.colleague = User(id=3, username="colleague_user", is_superuser=False)
        self.superuser_author = User(id=4, username="super_author", is_superuser=True)
        self.user_null_superuser = User(id=5, username="null_super", is_superuser=None)

        self.followup_with_author = FollowUp(user=self.author)
        self.followup_without_author = FollowUp(user=None)

    def test_case_01_author_can_edit_own_followup(self):
        followup = self.followup_with_author
        user = self.author

        result = can_edit_followup(followup, user)

        self.assertTrue(result)

    def test_case_02_superuser_can_edit_other_user_followup(self):
        followup = self.followup_with_author
        user = self.superuser

        result = can_edit_followup(followup, user)

        self.assertTrue(result)

    def test_case_03_non_author_regular_user_cannot_edit_followup(self):
        followup = self.followup_with_author
        user = self.colleague

        result = can_edit_followup(followup, user)

        self.assertFalse(result)

    def test_case_04_edit_forbidden_when_setting_is_disabled(self):
        followup = self.followup_with_author
        user = self.author

        with mock.patch.object(
            helpdesk_settings, "HELPDESK_SHOW_EDIT_BUTTON_FOLLOW_UP", False
        ):
            result = can_edit_followup(followup, user)

            self.assertFalse(result)

    def test_case_05_edit_forbidden_when_setting_is_none(self):
        followup = self.followup_with_author
        user = self.author

        with mock.patch.object(
            helpdesk_settings, "HELPDESK_SHOW_EDIT_BUTTON_FOLLOW_UP", None
        ):
            result = can_edit_followup(followup, user)

            self.assertFalse(result)

    def test_case_06_edit_forbidden_when_followup_has_no_author(self):
        followup = self.followup_without_author
        user = self.author

        result = can_edit_followup(followup, user)

        self.assertFalse(result)

    def test_case_07_raises_attribute_error_when_followup_is_none(self):
        followup = None
        user = self.author

        with self.assertRaises(AttributeError):
            can_edit_followup(followup, user)

    def test_case_08_raises_attribute_error_when_user_is_none(self):
        followup = self.followup_with_author
        user = None

        with self.assertRaises(AttributeError):
            can_edit_followup(followup, user)

    def test_case_09_superuser_author_can_edit_followup(self):
        followup = FollowUp(user=self.superuser_author)
        user = self.superuser_author

        result = can_edit_followup(followup, user)

        self.assertTrue(result)

    def test_case_10_edit_forbidden_when_is_superuser_is_none(self):
        followup = self.followup_with_author
        user = self.user_null_superuser

        result = can_edit_followup(followup, user)

        self.assertFalse(result)
