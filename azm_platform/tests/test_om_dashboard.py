from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestOmDashboard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({'name': 'AZM Test Campus'})
        cls.env.user.company_ids = [(4, cls.company.id)]
        cls.entity = cls.company.azm_entity_ids   # created with the company
        cls.assessment = cls.env['azm.assessment'].create({
            'company_id': cls.company.id, 'entity_id': cls.entity.id, 'purchase_kind': 'subscriptions', 'scenario': 'petty_cash',
        })
        cls.assessment.action_fill_demo()
        cls.assessment.action_sync_findings()
        cls.Dashboard = cls.env['azm.dashboard'].with_context(
            allowed_company_ids=[cls.env.company.id, cls.company.id])
        cls.user = new_test_user(cls.env, 'azm_om_viewer', company_id=cls.company.id,
                                 company_ids=[(6, 0, [cls.company.id])],
                                 groups='azm_platform.group_azm_user,azm_operating_model.azm_group_user')
        cls.entity.user_ids = [(4, cls.user.id)]

    def test_stage_domains(self):
        stages = self.env['azm.stage'].search([])
        by_code = {s.code: s.azm_domain for s in stages}
        self.assertEqual(by_code['GOV'], 'governance')
        for code in ('BUD', 'INV', 'ADV', 'PAY', 'CLS'):
            self.assertEqual(by_code[code], 'financial')
        for code in ('REQ', 'STK', 'VEN', 'RFQ', 'AWD', 'ORD', 'RCV'):
            self.assertEqual(by_code[code], 'procurement')
        # a hand-chosen domain survives a catalogue reload
        stages.filtered(lambda s: s.code == 'STK').azm_domain = 'financial'
        self.env['azm.stage']._load_catalogue()
        self.assertEqual(stages.filtered(lambda s: s.code == 'STK').azm_domain, 'financial')

    def test_page_data(self):
        data = self.Dashboard.get_operating_model_data()
        self.assertTrue(data['available'])
        self.assertEqual(len(data['stages']), 13)
        self.assertEqual([d['key'] for d in data['domains']], ['governance', 'procurement', 'financial'])
        self.assertEqual(sum(d['questions'] for d in data['domains']), self.env['azm.question'].search_count([]))
        k = data['kpis']
        self.assertGreaterEqual(k['assessments'], 1)
        self.assertIn(self.assessment.id, [a['id'] for a in data['assessments']])
        self.assertGreater(k['visible'], 0)
        self.assertGreater(k['completion'], 90)  # demo answers fill everything visible
        self.assertGreater(k['findings_open'], 0)
        self.assertEqual(k['risks'], sum(s['risks'] for s in data['stages']))

    def test_filters(self):
        data = self.Dashboard.get_operating_model_data(domain='financial', assessment_id=self.assessment.id)
        self.assertEqual({s['code'] for s in data['stages']}, {'BUD', 'INV', 'ADV', 'PAY', 'CLS'})
        self.assertEqual(data['kpis']['assessments'], 1)
        self.assertTrue(all(s['status'] for s in data['stages']))
        fin = next(d for d in data['domains'] if d['key'] == 'financial')
        self.assertEqual(fin['risks'], data['kpis']['risks'])
        by_company = self.Dashboard.get_operating_model_data(company_id=self.company.id)
        self.assertEqual([e['id'] for e in by_company['entities']], [self.entity.id])

    def test_home_and_entity_page(self):
        home = self.env['azm.dashboard'].with_user(self.user).get_dashboard_data()
        self.assertTrue(home['om'])
        self.assertIn('domains', home['om'])
        overview = self.env['azm.dashboard'].with_user(self.user).get_company_overview(self.company.id)
        self.assertEqual(overview['om']['entities'][0]['id'], self.entity.id)

    def test_without_access(self):
        outsider = new_test_user(self.env, 'azm_platform_only', groups='azm_platform.group_azm_user')
        home = self.env['azm.dashboard'].with_user(outsider).get_dashboard_data()
        self.assertFalse(home['om'])
        self.assertFalse(self.env['azm.dashboard'].with_user(outsider).get_operating_model_data()['available'])

    def test_each_user_sees_own_data(self):
        """Figures on the page and the Home page only count what the person may open."""
        own = self.env['azm.assessment'].with_user(self.user).create({
            'entity_id': self.entity.id, 'purchase_kind': 'works', 'scenario': 'direct'})
        mine = self.env['azm.dashboard'].with_user(self.user).get_operating_model_data()
        self.assertEqual([a['id'] for a in mine['assessments']], [own.id])
        self.assertEqual([e['id'] for e in mine['entities']], [self.entity.id])
        self.assertEqual(mine['kpis']['findings_open'], 0)  # the demo findings belong to someone else
        everything = self.Dashboard.get_operating_model_data()
        self.assertIn(self.assessment.id, [a['id'] for a in everything['assessments']])
        # another preparer on another entity sees neither
        company_2 = self.env['res.company'].create({'name': 'AZM Second Campus'})
        other_entity = company_2.azm_entity_ids
        other = new_test_user(self.env, 'azm_om_other', company_id=company_2.id,
                              company_ids=[(6, 0, [company_2.id])],
                              groups='azm_platform.group_azm_user,azm_operating_model.azm_group_user')
        other_entity.user_ids = [(4, other.id)]
        theirs = self.env['azm.dashboard'].with_user(other).get_operating_model_data()
        self.assertFalse(theirs['assessments'])
        self.assertEqual([e['id'] for e in theirs['entities']], [other_entity.id])
        home = self.env['azm.dashboard'].with_user(other).get_dashboard_data()
        self.assertEqual(home['om']['kpis']['assessments'], 0)

    def test_company_switcher_scope(self):
        """The AZM figures follow the companies selected in the company switcher."""
        only_main = self.env['azm.dashboard'].with_context(allowed_company_ids=[self.env.company.id])
        self.assertNotIn(self.entity.id, [e['id'] for e in only_main.get_operating_model_data()['entities']])
        self.assertIn(self.entity.id, [e['id'] for e in self.Dashboard.get_operating_model_data()['entities']])
        self.assertFalse(only_main.get_company_overview(self.company.id))

    def test_structure_hides_inaccessible_parent(self):
        """Group Structure never points to a company the user cannot open."""
        child = self.env['res.company'].create({'name': 'AZM Test Branch', 'parent_id': self.company.id})
        self.user.company_ids = [(4, child.id)]
        company = self.env['res.company'].with_user(self.user).with_context(
            allowed_company_ids=[self.company.id, child.id])
        roots = company.search([('azm_parent_id', '=', False), ('id', 'in', [self.company.id, child.id])])
        self.assertEqual(roots.ids, [self.company.id])  # its real parent (main company) is hidden
        self.assertEqual(company.browse(child.id).azm_parent_id.id, self.company.id)
        self.assertEqual(company.browse(self.company.id).azm_child_ids.ids, [child.id])

    def test_platform_counts_follow_access(self):
        """Platform counts (employees...) no longer bypass access rights."""
        self.env['hr.employee'].create({'name': 'AZM Test Employee', 'company_id': self.company.id})
        self.assertGreaterEqual(self.company.azm_employee_count, 1)
        plain = new_test_user(self.env, 'azm_no_hr', company_id=self.company.id,
                              company_ids=[(6, 0, [self.company.id])], groups='azm_platform.group_azm_user')
        if not self.env['hr.employee'].with_user(plain).has_access('read'):
            self.assertEqual(self.company.with_user(plain).azm_employee_count, 0)
        home = self.env['azm.dashboard'].with_user(plain).get_dashboard_data()
        self.assertEqual(home['kpis']['employees'], self.company.with_user(plain).azm_employee_count)

    def test_financial_model_page(self):
        """The unified financial model page, Home and entity sections follow each user's access."""
        self.entity.fin_scope_ids = [(6, 0, self.env['azm.fin.scope'].search([('code', 'in', ('EDU', 'WORK'))]).ids)]
        fin = self.env['azm.fin.assessment'].with_user(self.user).create({'entity_id': self.entity.id})
        fin.action_fill_demo()
        Dash = self.env['azm.dashboard'].with_user(self.user)
        data = Dash.get_financial_model_data()
        self.assertTrue(data['available'])
        self.assertEqual(len(data['modules']), 19)
        self.assertEqual(data['kpis']['requirements'], 167)
        self.assertEqual(data['kpis']['catalogue_questions'], 1136)
        self.assertEqual(data['kpis']['answered_questions'], fin.answered_count)
        self.assertEqual(data['kpis']['questions'], fin.question_count)
        self.assertEqual(data['kpis']['assessments'], 1)
        self.assertEqual(data['kpis']['completion'], 100)
        self.assertEqual(sum(m['applicable'] for m in data['modules']), fin.applicable_count)
        self.assertEqual(data['kpis']['gaps'], fin.partial_count + fin.unavailable_count)
        hrf = Dash.get_financial_model_data(source='HRF')
        self.assertEqual(hrf['kpis']['requirements'], 60)
        one = Dash.get_financial_model_data(assessment_id=fin.id, profile='A')
        self.assertTrue(all(m['requirements'] == len([1 for _ in range(m['requirements'])]) for m in one['modules']))
        self.assertTrue(Dash.get_dashboard_data()['fin'])
        self.assertTrue(Dash.get_company_overview(self.company.id)['fin'])
        other = new_test_user(self.env, 'azm_fin_other', company_id=self.company.id,
                              company_ids=[(6, 0, [self.company.id])],
                              groups='azm_platform.group_azm_user,azm_operating_model.azm_group_user')
        self.assertEqual(self.env['azm.dashboard'].with_user(other).get_financial_model_data()['kpis']['assessments'], 0)
        platform_only = new_test_user(self.env, 'azm_fin_none', groups='azm_platform.group_azm_user')
        self.assertFalse(self.env['azm.dashboard'].with_user(platform_only).get_dashboard_data()['fin'])

    def test_operating_models_hub(self):
        hub = self.env['azm.dashboard'].with_user(self.user).get_operating_models_hub()
        self.assertTrue(hub['available'])
        self.assertEqual([m['key'] for m in hub['models']], ['procurement', 'financial'])
        self.assertEqual(hub['totals']['items'], 396 + 1136)
        self.assertIn(self.entity.id, [e['id'] for e in hub['entities']])
        none = new_test_user(self.env, 'azm_hub_none', groups='azm_platform.group_azm_user')
        self.assertFalse(self.env['azm.dashboard'].with_user(none).get_operating_models_hub()['available'])

    def test_unified_assessments_and_register(self):
        """Assessments and Risk Register list both operating models, per user."""
        fin = self.env['azm.fin.assessment'].with_user(self.user).create({'entity_id': self.entity.id})
        fin.action_fill_demo()
        Dash = self.env['azm.dashboard'].with_user(self.user)
        rows = Dash.get_unified_assessments()['rows']
        self.assertEqual({r['model'] for r in rows}, {'financial'})   # the procurement demo belongs to someone else
        own = self.env['azm.assessment'].with_user(self.user).create(
            {'entity_id': self.entity.id, 'purchase_kind': 'works', 'scenario': 'direct'})
        rows = Dash.get_unified_assessments()['rows']
        self.assertEqual({(r['model'], r['id']) for r in rows}, {('financial', fin.id), ('procurement', own.id)})
        register = Dash.get_unified_register()['rows']
        self.assertTrue(register)
        self.assertEqual({r['model'] for r in register}, {'financial'})
        self.assertEqual(len(register), fin.partial_count + fin.unavailable_count)
        admin_rows = self.Dashboard.get_unified_register()['rows']
        self.assertIn('procurement', {r['model'] for r in admin_rows})
        none = new_test_user(self.env, 'azm_reg_none', groups='azm_platform.group_azm_user')
        self.assertFalse(self.env['azm.dashboard'].with_user(none).get_unified_assessments()['available'])

    def test_companies_are_the_entities(self):
        self.assertEqual((self.entity.name, self.entity.code), ('AZM Test Campus', 'ATC'))
        self.assertEqual(self.company.azm_om_entity_ids, self.entity)
        # an entity typed earlier under the other-language name is linked, not duplicated
        by_alt = self.env['azm.entity'].create({'code': 'ZB1', 'name': 'فرع زيتا'})
        other = self.env['res.company'].create({'name': 'Zeta Branch', 'azm_name_alt': 'فرع زيتا'})
        self.assertEqual(other.azm_entity_ids, by_alt)
        self.assertEqual(by_alt.name, 'Zeta Branch')


@tagged('post_install', '-at_install')
class TestOmDashboardTour(HttpCase):

    def test_pages_render(self):
        """The Operating Model page, Home page and an entity page load without JS errors."""
        self.start_tour('/odoo/action-azm_platform.action_azm_dashboard',
                        'azm_om_dashboard_tour', login='admin')
