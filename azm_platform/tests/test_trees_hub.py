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

    def _sections(self):
        return {s['key']: s for s in self.D.get_trees_hub()['sections']}

    def test_the_page_carries_one_section_per_tree(self):
        hub = self.D.get_trees_hub()
        self.assertTrue(hub['available'])
        sections = {s['key']: s for s in hub['sections']}
        self.assertEqual(set(sections), {'financial', 'procurement'})
        for section in hub['sections']:
            self.assertEqual(len(section['levels']), 3, "a tree is read three levels deep")
            self.assertTrue(section['units'] and section['leaves'])
            self.assertTrue(section['action'], "a section says which page its cards open")
        self.assertEqual(hub['totals']['trees'], 2)

    def test_every_entity_gets_a_card_in_every_section(self):
        """A card is the way into a tree, so every entity the user works in has one —
        including the entity that has not started, whose tree shows what is asked."""
        companies = {c.id for c in self.D._companies()}
        for section in self._sections().values():
            self.assertEqual({c['company_id'] for c in section['cards']}, companies)

        started = {c['company_id']: c for c in self._sections()['financial']['cards']}
        self.assertEqual(started[self.company.id]['status'], 'in_progress')
        self.assertIsNotNone(started[self.company.id]['completion'])
        self.assertEqual(started[self.quiet.id]['status'], 'not_started')
        self.assertEqual(started[self.quiet.id]['assessments'], 0)

    def test_a_card_carries_the_figures_of_its_own_entity(self):
        fin = {c['company_id']: c for c in self._sections()['financial']['cards']}[self.company.id]
        figures = {f['key']: f['value'] for f in fin['figures']}
        self.assertEqual(figures['applicable'], self.fin.applicable_count)
        self.assertEqual(figures['gaps'], self.fin.gap_count)

        proc = {c['company_id']: c for c in self._sections()['procurement']['cards']}[self.company.id]
        self.assertEqual({f['key'] for f in proc['figures']}, {'answered', 'findings'})

    def test_the_cards_only_cover_entities_the_user_works_in(self):
        outsider_company = self.env['res.company'].create({'name': 'AZM Trees Outside'})
        user = new_test_user(
            self.env, 'azm_trees_insider', company_id=self.company.id,
            company_ids=[(6, 0, [self.company.id])],
            groups='azm_platform.group_azm_user,azm_operating_model.azm_group_user')
        hub = self.env['azm.dashboard'].with_user(user).with_company(self.company).get_trees_hub()
        for section in hub['sections']:
            self.assertEqual([c['company_id'] for c in section['cards']], [self.company.id])
            self.assertNotIn(outsider_company.id, [c['company_id'] for c in section['cards']])


@tagged('post_install', '-at_install')
class TestTreesTour(HttpCase):

    def test_the_trees_open_from_their_cards(self):
        """The Trees page and both trees render, and a card really opens its tree."""
        self.start_tour('/odoo/action-azm_platform.action_azm_trees', 'azm_trees_tour', login='admin')
