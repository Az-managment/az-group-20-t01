from odoo.addons.azm_platform.models.azm_proc_documents import PROC_TAB_ORDER
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestProcTree(TransactionCase):
    """The procurement cycle read as a tree: PUR › stage › group › question."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({'name': 'AZM Proc Campus'})
        cls.other = cls.env['res.company'].create({'name': 'AZM Proc Elsewhere'})
        cls.env.user.company_ids = [(4, cls.company.id)]
        cls.entity = cls.company.azm_entity_ids
        cls.D = cls.env['azm.dashboard']
        cls.assessment = cls.env['azm.assessment'].create({
            'entity_id': cls.entity.id, 'purchase_kind': 'subscriptions', 'scenario': 'petty_cash',
        })
        cls.assessment.action_fill_demo()
        cls.assessment.action_sync_findings()
        # someone who works in one entity only: creating a company hands it to its creator,
        # so the boundary has to be checked with a user who was never given the other one
        cls.insider = new_test_user(
            cls.env, 'azm_proc_insider', company_id=cls.company.id, company_ids=[(6, 0, [cls.company.id])],
            groups='azm_platform.group_azm_user,azm_operating_model.azm_group_user')

    def _tree(self):
        return self.D.with_company(self.company).get_proc_tree(company_id=self.company.id)

    def _leaf(self, tree, question):
        for stage in tree['nodes']:
            for group in stage['children']:
                for item in group['items']:
                    if item['id'] == question.id:
                        return item
        return None

    def test_tree_nests_stage_group_question(self):
        tree = self._tree()
        self.assertTrue(tree['available'])
        self.assertEqual(tree['company']['id'], self.company.id)
        self.assertEqual(tree['assessment']['id'], self.assessment.id)

        seen = 0
        for stage in tree['nodes']:
            self.assertTrue(stage['code'].startswith('PUR-'))
            self.assertTrue(stage['children'], f"{stage['code']} has no group")
            for group in stage['children']:
                self.assertTrue(group['items'], f"{group['name']} has no question")
                for item in group['items']:
                    self.assertTrue(item['code'].startswith(f"PUR-{stage['code'][4:]}/"))
                    self.assertIn(item['status']['key'], ('answered', 'unsure', 'open', 'hidden'))
                    self.assertEqual(item['doc'], {'kind': 'question', 'id': item['id']},
                                     "every leaf names the document it stands for")
                    seen += 1
        self.assertEqual(seen, self.env['azm.question'].search_count([]),
                         "every question hangs somewhere on the tree, exactly once")
        self.assertEqual(tree['totals']['questions'], seen)
        self.assertEqual(tree['totals']['stages'], len(tree['nodes']))
        for node in tree['nodes']:
            record = self.env['azm.stage'].browse(node['id'])
            self.assertEqual([d['tab'] for d in node['docs']], record._azm_outputs(),
                             "every output the stage can have hangs on it in the tree")
        self.assertEqual(tree['summary_doc']['kind'], 'cycle')

        outputs = tree['outputs']
        self.assertEqual(outputs['total'], sum(f['count'] for f in outputs['families']))
        by_tab = {f['tab']: f for f in outputs['families']}
        self.assertEqual(by_tab['question']['count'], tree['totals']['questions'])
        stages = self.env['azm.stage'].browse([n['id'] for n in tree['nodes']])
        for tab in PROC_TAB_ORDER:
            self.assertEqual(by_tab[tab]['count'],
                             sum(1 for s in stages if tab in s._azm_outputs()),
                             "a stage is counted for an output only if it can have one")

        branches = [g['id'] for s in tree['nodes'] for g in s['children']]
        self.assertEqual(len(branches), len(set(branches)),
                         "each branch has an id of its own, so folding one never folds another")

    def test_a_leaf_follows_the_entity_answer(self):
        """A leaf says what this entity answered — answered, uncertain, or still open."""
        answer = self.assessment.answer_ids.filtered(
            lambda a: a.is_visible and a.qtype == 'select' and a.option_id)[:1]
        self.assertTrue(answer, "the demo fills at least one single-choice answer")
        self.assertEqual(self._leaf(self._tree(), answer.question_id)['status']['key'], 'answered')

        unknown = answer.question_id.option_ids.filtered(lambda o: o.kind == 'unknown')[:1]
        if unknown:
            answer.option_id = unknown
            self.assertEqual(self._leaf(self._tree(), answer.question_id)['status']['key'], 'unsure')

        answer.option_id = False
        self.assertEqual(self._leaf(self._tree(), answer.question_id)['status']['key'], 'open')

    def test_a_question_not_asked_here_is_drawn_as_such(self):
        """The engine decides what is asked; the tree shows the rest as 'not asked here',
        so a conditional question never reads as an unanswered hole."""
        hidden = self.assessment.answer_ids.filtered(lambda a: not a.is_visible)[:1]
        self.assertTrue(hidden, "the demo leaves at least one conditional question unasked")
        leaf = self._leaf(self._tree(), hidden.question_id)
        self.assertEqual(leaf['status']['key'], 'hidden')
        node = self.D.get_proc_tree_node(question_id=hidden.question_id.id, company_id=self.company.id)
        self.assertEqual(node['status']['key'], 'hidden')

    def test_a_node_shows_the_choice_made_and_the_risks_watched(self):
        rule = self.env['azm.risk.rule'].search([], limit=1)
        answer = self.assessment.answer_ids.filtered(lambda a: a.question_id == rule.question_id)
        answer.option_id = rule.trigger_option_id
        node = self.D.get_proc_tree_node(question_id=rule.question_id.id, company_id=self.company.id)

        self.assertEqual(node['code'], rule.question_id.code)
        chosen = [o['name'] for o in node['options'] if o['chosen']]
        self.assertEqual(chosen, [rule.trigger_option_id.name],
                         "the detail marks the option this entity actually picked")
        self.assertIn(rule.code, [r['code'] for r in node['risks']],
                      "the risks the catalogue watches on this question are shown with it")
        self.assertEqual([s[1] for s in node['path']][1],
                         f"PUR-{rule.question_id.stage_id.code} · {rule.question_id.stage_id.name}",
                         "the breadcrumb names the stage the way every other place does")

    def test_an_entity_outside_the_switcher_is_not_read(self):
        """Asking for a company the user was never given falls back to one they work in."""
        tree = self.D.with_user(self.insider).get_proc_tree(company_id=self.other.id)
        self.assertEqual(tree['company']['id'], self.company.id)
        self.assertNotIn(self.other.id, [o['id'] for o in tree['entity_options']])

        question = self.env['azm.question'].search([], limit=1)
        node = self.D.with_user(self.insider).get_proc_tree_node(
            question_id=question.id, company_id=self.other.id)
        self.assertEqual(node['company'], self.company.name)
