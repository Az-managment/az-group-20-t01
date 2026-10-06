from odoo import Command
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestFinTree(TransactionCase):
    """The model read as a tree: FIN › module › topic › requirement, for one entity."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({'name': 'AZM Tree Campus'})
        cls.other = cls.env['res.company'].create({'name': 'AZM Tree Elsewhere'})
        cls.env.user.company_ids = [(4, cls.company.id)]
        cls.D = cls.env['azm.dashboard']
        cls.entity = cls.company.azm_entity_ids
        cls.assessment = cls.env['azm.fin.assessment'].create({'entity_id': cls.entity.id})
        cls.assessment.action_fill_demo()
        # someone who works in one entity only: creating a company hands it to its creator,
        # so the boundary has to be checked with a user who was never given the other one
        cls.insider = new_test_user(
            cls.env, 'azm_tree_insider', company_id=cls.company.id, company_ids=[(6, 0, [cls.company.id])],
            groups='azm_platform.group_azm_user,azm_operating_model.azm_group_user')

    def _tree(self):
        return self.D.with_company(self.company).get_fin_tree(company_id=self.company.id)

    def test_every_leaf_says_what_it_is_called(self):
        """The tree shows two codes against a requirement and they answer two questions:
        FIN.GOV.01.01 is where it sits, FUE-FIN-GOV-DOA-000001 is what this entity's copy
        of the deliverable is called. A reader holding a document should be able to find
        it on the tree, and a reader on the tree should know what to ask the library for.
        """
        self.env['azm.artifact'].sudo()._register_all()
        tree = self.D.get_fin_tree(company_id=self.company.id)
        entity = self.company.azm_entity_ids[:1]
        self.assertTrue(entity.code)
        leaves = [item for node in tree['nodes'] for child in node['children']
                  for item in child['items']]
        self.assertTrue(leaves)
        coded = [leaf for leaf in leaves if leaf.get('azm_code')]
        self.assertTrue(coded, 'the leaves carry the code of the deliverable they are')
        for leaf in coded[:8]:
            self.assertTrue(leaf['azm_code'].startswith(f"{entity.code}-FIN-"),
                            "this entity's own copy of it, not the group's master")
            self.assertNotEqual(leaf['azm_code'], leaf['code'],
                                'the tree reference and the code are different things')

    def test_tree_nests_module_topic_requirement(self):
        tree = self._tree()
        self.assertTrue(tree['available'])
        self.assertEqual(tree['company']['id'], self.company.id)
        self.assertTrue(tree['nodes'], "the tree carries every module that has requirements")

        seen = 0
        for module in tree['nodes']:
            self.assertTrue(module['code'].startswith('FIN.'))
            self.assertTrue(module['children'], f"{module['code']} has no topic")
            for topic in module['children']:
                self.assertTrue(topic['items'], f"{topic['code']} has no requirement")
                for item in topic['items']:
                    # the leaf's code sits under its topic, which sits under its module
                    self.assertTrue(item['code'].startswith(f"{topic['code']}."))
                    self.assertTrue(topic['code'].startswith(f"{module['code']}."))
                    self.assertIn(item['status']['key'],
                                  ('full', 'partial', 'unavailable', 'unknown', 'na', 'open'))
                    seen += 1
        self.assertEqual(seen, self.env['azm.fin.requirement'].search_count([]),
                         "every requirement hangs somewhere on the tree, exactly once")
        self.assertEqual(tree['totals']['requirements'], seen)
        for node in tree['nodes']:
            record = self.env['azm.fin.module'].browse(node['id'])
            self.assertEqual([d['tab'] for d in node['docs']], record._azm_outputs(),
                             "every output the module can have hangs on it in the tree")
        self.assertEqual(tree['summary_doc']['kind'], 'summary')

        outputs = tree['outputs']
        self.assertTrue(outputs['families'], "the page says how many of each it holds")
        self.assertEqual(outputs['total'], sum(f['count'] for f in outputs['families']))
        self.assertLessEqual(outputs['ready'], outputs['total'],
                             "a document cannot be readier than it is offered")
        by_tab = {f['tab']: f for f in outputs['families']}
        self.assertEqual(by_tab['requirement']['count'], tree['totals']['requirements'])
        self.assertEqual(by_tab['summary']['count'], 1)
        for family in outputs['families']:
            self.assertLessEqual(family['ready'], family['count'])

        branches = [t['id'] for m in tree['nodes'] for t in m['children']]
        self.assertEqual(len(branches), len(set(branches)),
                         "each branch has an id of its own, so folding one never folds another")

    def test_a_node_follows_the_entity_answers(self):
        requirement = self.env['azm.fin.requirement'].search([], limit=1)
        line = self.assessment.answer_ids.filtered(lambda a: a.requirement_id == requirement)
        line.write({'na': True, 'reason': 'تجربة'})

        def status_of(tree):
            for module in tree['nodes']:
                for topic in module['children']:
                    for item in topic['items']:
                        if item['id'] == requirement.id:
                            return item['status']['key']
            return None

        self.assertEqual(status_of(self._tree()), 'na')
        node = self.D.get_fin_tree_node(requirement_id=requirement.id, company_id=self.company.id)
        self.assertEqual(node['status']['key'], 'na')

    def test_the_node_reads_the_same_path_as_its_document(self):
        requirement = self.env['azm.fin.requirement'].search([('topic_id', '!=', False)], limit=1)
        node = self.D.get_fin_tree_node(requirement_id=requirement.id, company_id=self.company.id)
        pub = self.env['azm.doc.publication']._get(self.company, 'requirement', requirement=requirement)
        doc_path = pub._azm_payload()['path']
        self.assertEqual([step[0] for step in node['path']], [step[0] for step in doc_path],
                         "the page and the filed document place the requirement identically")
        for step, (_label, code, name) in zip(node['path'], doc_path):
            # the page shows one line where the document has a code and a name; both are on it
            self.assertIn(name or code, step[1])
            self.assertIn(code or name, step[1])
        # the page names the node, not the publication: the document is resolved — and
        # built, if nobody has read it yet — when it is opened
        self.assertEqual(node['doc'], {'kind': 'requirement', 'id': requirement.id})
        self.assertEqual(pub.requirement_id, requirement)

    def test_an_entity_outside_the_switcher_is_not_read(self):
        """Asking for a company the user was never given falls back to one they work in."""
        tree = self.D.with_user(self.insider).get_fin_tree(company_id=self.other.id)
        self.assertEqual(tree['company']['id'], self.company.id)
        self.assertNotIn(self.other.id, [o['id'] for o in tree['entity_options']])

    def test_a_node_of_another_entity_is_not_read(self):
        requirement = self.env['azm.fin.requirement'].search([], limit=1)
        node = self.D.with_user(self.insider).get_fin_tree_node(
            requirement_id=requirement.id, company_id=self.other.id)
        self.assertEqual(node['company'], self.company.name)

    def test_an_entity_that_has_not_started_is_promised_nothing_empty(self):
        """Every module output is empty until there are answers behind it, so the
        count must not offer documents that would refuse to open."""
        fresh = self.env['res.company'].create({'name': 'AZM Tree Unstarted'})
        self.env.user.company_ids = [(4, fresh.id)]
        tree = self.D.with_context(
            allowed_company_ids=[self.env.company.id, fresh.id]).with_company(
            fresh).get_fin_tree(company_id=fresh.id)
        self.assertIsNone(tree['assessment'])
        tabs = {f['tab'] for f in tree['outputs']['families']}
        self.assertEqual(tabs, {'requirement', 'summary'},
                         "only the sheets that really exist are counted")
        self.assertEqual(tree['outputs']['total'],
                         tree['totals']['requirements'] + 1)

    def test_the_tree_shows_only_the_answers_the_reader_may_read(self):
        """An assessment is scoped to the person preparing or reviewing it; a published
        document is scoped to the company. The tree shows the answers themselves, so it
        follows the first — it used to read them elevated and show everyone everything.
        """
        company = self.env['res.company'].create({'name': 'AZM Tree Scope'})
        entity = company.azm_entity_ids[:1]

        def azm_user(login):
            user = self.env['res.users'].create({
                'name': login, 'login': login, 'company_id': company.id,
                'company_ids': [Command.set([company.id])],
                'group_ids': [Command.link(self.env.ref('azm_platform.group_azm_user').id),
                              Command.link(self.env.ref('azm_operating_model.azm_group_user').id)]})
            entity.user_ids = [Command.link(user.id)]
            return user

        preparer, colleague = azm_user('azm_scope_preparer'), azm_user('azm_scope_colleague')
        assessment = self.env['azm.fin.assessment'].create({
            'entity_id': entity.id, 'user_id': preparer.id})
        assessment.action_fill_demo()
        requirement = self.env['azm.fin.requirement'].search([], limit=1)

        def tree_for(user):
            dashboard = self.env['azm.dashboard'].with_user(user).with_context(
                allowed_company_ids=[company.id]).with_company(company)
            data = dashboard.get_fin_tree(company_id=company.id)
            answered = sum(1 for n in data['nodes'] for c in n['children'] for i in c['items']
                           if i['status']['key'] != 'open')
            node = dashboard.get_fin_tree_node(
                requirement_id=requirement.id, company_id=company.id)
            return data, answered, node

        data, answered, node = tree_for(preparer)
        self.assertEqual(data['assessment']['id'], assessment.id)
        self.assertTrue(answered, "the preparer sees their own answers")
        self.assertNotEqual(node['status']['key'], 'open')

        self.assertFalse(
            self.env['azm.fin.assessment'].with_user(colleague).search_count(
                [('id', '=', assessment.id)]),
            "the access rules do not let a colleague read this assessment")
        data, answered, node = tree_for(colleague)
        self.assertIsNone(data['assessment'], "so the tree does not read it for them either")
        self.assertEqual(answered, 0, "no leaf carries somebody else's answer")
        self.assertEqual(node['status']['key'], 'open',
                         "a requirement reads as unanswered, which is what they may know")
        self.assertTrue(data['nodes'], "the tree still shows what the model asks")
