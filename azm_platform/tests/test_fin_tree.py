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
        self.assertEqual(node['doc']['id'], pub.id)

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
