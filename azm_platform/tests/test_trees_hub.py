from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestTreesHub(TransactionCase):
    """The Trees page: a section per model that can be walked, a card per entity in it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({'name': 'AZM Trees Campus'})
        cls.quiet = cls.env['res.company'].create({'name': 'AZM Trees Quiet'})
        cls.env.user.company_ids = [(4, cls.company.id), (4, cls.quiet.id)]
        cls.entity = cls.company.azm_entity_ids
        cls.D = cls.env['azm.dashboard'].with_context(
            allowed_company_ids=[cls.env.company.id, cls.company.id, cls.quiet.id])
        cls.proc = cls.env['azm.assessment'].create({
            'entity_id': cls.entity.id, 'purchase_kind': 'subscriptions', 'scenario': 'petty_cash',
        })
        cls.proc.action_fill_demo()
        cls.fin = cls.env['azm.fin.assessment'].create({'entity_id': cls.entity.id})
        cls.fin.action_fill_demo()

    def _entities(self):
        return {e['company_id']: e for e in self.D.get_trees_hub()['entities']}

    def _trees_of(self, company):
        return {t['key']: t for t in self._entities()[company.id]['trees']}

    def test_the_page_opens_on_the_entities(self):
        """A tree is always somebody's, so the page asks who before it asks which."""
        hub = self.D.get_trees_hub()
        self.assertTrue(hub['available'])
        self.assertEqual({e['company_id'] for e in hub['entities']},
                         {c.id for c in self.D._companies()})
        self.assertEqual(hub['totals']['trees'], 2)

    def test_an_entity_carries_every_tree_it_has(self):
        """Including the tree it has not started: that one shows what is being asked."""
        for company in (self.company, self.quiet):
            trees = self._trees_of(company)
            self.assertEqual(set(trees), {'financial', 'procurement'})
            for tree in trees.values():
                self.assertEqual(len(tree['levels']), 3, "a tree is read three levels deep")
                self.assertTrue(tree['units'] and tree['leaves'])
                self.assertTrue(tree['action'], "a tree says which page it opens")

        self.assertEqual(self._trees_of(self.company)['financial']['status'], 'in_progress')
        self.assertIsNotNone(self._trees_of(self.company)['financial']['completion'])
        self.assertEqual(self._trees_of(self.quiet)['financial']['status'], 'not_started')
        self.assertEqual(self._trees_of(self.quiet)['financial']['assessments'], 0)

    def test_an_entity_says_how_far_it_has_got_across_its_trees(self):
        started, quiet = self._entities()[self.company.id], self._entities()[self.quiet.id]
        self.assertEqual(started['started'], 2, 'both of its trees are under way')
        self.assertEqual(started['status'], 'in_progress')
        self.assertIsNotNone(started['completion'])
        self.assertEqual(quiet['started'], 0)
        self.assertEqual(quiet['status'], 'not_started')
        self.assertIsNone(quiet['completion'], 'nothing started is not nought per cent')

    def test_a_tree_carries_the_figures_of_the_entity_it_is_under(self):
        fin = self._trees_of(self.company)['financial']
        figures = {f['key']: f['value'] for f in fin['figures']}
        self.assertEqual(figures['applicable'], self.fin.applicable_count)
        self.assertEqual(figures['gaps'], self.fin.gap_count)

        proc = self._trees_of(self.company)['procurement']
        self.assertEqual({f['key'] for f in proc['figures']}, {'answered', 'findings'})

    def test_the_page_only_covers_entities_the_user_works_in(self):
        outsider_company = self.env['res.company'].create({'name': 'AZM Trees Outside'})
        user = new_test_user(
            self.env, 'azm_trees_insider', company_id=self.company.id,
            company_ids=[(6, 0, [self.company.id])],
            groups='azm_platform.group_azm_user,azm_operating_model.azm_group_user')
        hub = self.env['azm.dashboard'].with_user(user).with_company(self.company).get_trees_hub()
        self.assertEqual([e['company_id'] for e in hub['entities']], [self.company.id])
        self.assertNotIn(outsider_company.id, [e['company_id'] for e in hub['entities']])


@tagged('post_install', '-at_install')
class TestTreesTour(HttpCase):

    def test_the_trees_open_from_their_cards(self):
        """The Trees page and both trees render, and a card really opens its tree."""
        self.start_tour('/odoo/action-azm_platform.action_azm_trees', 'azm_trees_tour', login='admin')
