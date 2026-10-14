import json

from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestAzmLanguageSwitch(HttpCase):
    """The sidebar switcher changes the language of the running session."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.arabic = cls.env['res.lang'].with_context(active_test=False).search(
            [('code', '=like', 'ar%'), ('active', '=', True)], limit=1)
        cls.user = new_test_user(
            cls.env, 'lang_switcher', password='lang_switcher',
            groups='base.group_user,azm_platform.group_azm_user',
        )

    def _call(self, lang):
        response = self.url_open(
            '/azm/language',
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': {'lang': lang}}),
            headers={'Content-Type': 'application/json'},
        )
        return response.json().get('result')

    def test_the_language_of_the_user_and_of_the_session_both_change(self):
        """Writing res.users.lang alone is not enough.

        The session keeps the context it built when the user logged in, and the
        pages and the assets are rendered in the language read from there, so a
        preference written on its own only shows up at the next login. The page
        has to come back in the new language on the reload that follows.
        """
        if not self.arabic:
            self.skipTest("Arabic is not installed")
        self.authenticate('lang_switcher', 'lang_switcher')
        self.assertEqual(self.user.lang, 'en_US')
        self.assertTrue(self._call(self.arabic.code))
        self.assertEqual(self.user.lang, self.arabic.code, "the preference was not written")
        page = self.url_open('/odoo').text
        self.assertIn(
            '.rtl.', page,
            "the session still renders left to right: its context kept the old language",
        )

    def test_switching_back_restores_the_left_to_right_assets(self):
        if not self.arabic:
            self.skipTest("Arabic is not installed")
        self.authenticate('lang_switcher', 'lang_switcher')
        self._call(self.arabic.code)
        self.assertTrue(self._call('en_US'))
        self.assertEqual(self.user.lang, 'en_US')
        self.assertNotIn('.rtl.', self.url_open('/odoo').text)

    def test_a_language_that_is_not_installed_is_refused(self):
        """The route writes a field the user may write, so it validates first."""
        self.authenticate('lang_switcher', 'lang_switcher')
        self.assertFalse(self._call('zz_ZZ'))
        self.assertEqual(self.user.lang, 'en_US')
