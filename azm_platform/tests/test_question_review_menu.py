from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestQuestionReviewReaches(TransactionCase):
    """Can a question reviewer actually get to their page?

    Having the group is not having the page. The review workspace was first hung under
    the operating model's technical menu, whose root is the administrator's; a question
    reviewer holds neither that group nor the platform's own user group, so they signed
    in to no AZM app at all and the role was unusable. These read the menus the way the
    web client does — load_menus, which applies every gate — rather than searching
    ir.ui.menu, which answers about a record and not about what somebody sees.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.question_reviewer = new_test_user(
            cls.env, 'azm_qreview_menu',
            groups='azm_operating_model.azm_group_question_reviewer')
        cls.outsider = new_test_user(cls.env, 'azm_outsider_menu',
                                     groups='base.group_user')

    def _apps(self, user):
        """{xmlid: [child xmlid, ...]} of what this user is offered."""
        menus = self.env(user=user)['ir.ui.menu'].load_menus(False)
        # the ids come back as ints here and as strings over the wire; read both
        def at(key):
            return menus.get(key) or menus.get(str(key))
        found = {}
        for app_id in menus['root']['children']:
            app = at(app_id)
            found[app['xmlid']] = [at(c)['xmlid'] for c in app['children']]
        return found

    def test_the_app_is_listed(self):
        apps = self._apps(self.question_reviewer)
        self.assertIn('azm_platform.menu_root', apps,
                      "a question reviewer signs in to no AZM app")

    def test_the_page_is_in_it(self):
        children = self._apps(self.question_reviewer)['azm_platform.menu_root']
        self.assertIn('azm_platform.menu_question_review', children)

    def test_and_nothing_else_is(self):
        """Listing the shell for them must not hand them the rest of it."""
        children = self._apps(self.question_reviewer)['azm_platform.menu_root']
        self.assertEqual(children, ['azm_platform.menu_question_review'])

    def test_an_internal_user_gets_neither(self):
        self.assertNotIn('azm_platform.menu_root', self._apps(self.outsider))

    def test_the_answerer_keeps_their_own_page(self):
        """The shell's gate was widened, not swapped."""
        answerer = new_test_user(
            self.env, 'azm_answerer_menu',
            groups='azm_operating_model.azm_group_user,azm_platform.group_azm_user')
        children = self._apps(answerer)['azm_platform.menu_root']
        self.assertIn('azm_platform.menu_my_work', children)
        self.assertNotIn('azm_platform.menu_question_review', children)
