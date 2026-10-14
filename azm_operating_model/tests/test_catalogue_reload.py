import io
import json
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged
from odoo.tools import file_open


@tagged('post_install', '-at_install')
class TestCatalogueReload(TransactionCase):
    """What a catalogue reload must not break in the assessments that already exist."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({'name': 'AZM Reload Campus'})
        cls.env.user.company_ids = [(4, cls.company.id)]
        cls.entity = cls.company.azm_entity_ids
        cls.proc = cls.env['azm.assessment'].create({
            'entity_id': cls.entity.id, 'purchase_kind': 'subscriptions', 'scenario': 'petty_cash'})
        cls.proc.action_fill_demo()
        cls.fin = cls.env['azm.fin.assessment'].create({'entity_id': cls.entity.id})
        cls.fin.action_fill_demo()

    # ------------------------------------------------------------------ added question
    def test_a_new_question_does_not_break_an_older_assessment(self):
        """The workspace reads a line for every visible question; a question added to
        the catalogue has none on the assessments that predate it."""
        stage = self.env['azm.stage'].search([], limit=1)
        self.env['azm.question'].create({
            'stage_id': stage.id, 'key': 'zz_probe', 'label': 'سؤال تجريبي',
            'clause': 'تجربة', 'qtype': 'select'})

        self.proc.workspace_data(stage_id=stage.id)     # used to raise KeyError
        self.proc.action_fill_demo()                    # and so did this

        self.env['azm.assessment']._ensure_all_answers()
        added = self.env['azm.question'].search([('key', '=', 'zz_probe')])
        self.assertTrue(self.proc.answer_ids.filtered(lambda a: a.question_id == added),
                        "the reload gives the older assessment a line for it")

    # ------------------------------------------------------------------ retired requirement
    def test_a_retired_requirement_stops_being_asked_and_counted(self):
        line = self.fin.answer_ids.filtered('applicable')[:1]
        requirement = line.requirement_id
        module = requirement.module_id
        before = self.fin.applicable_count
        before_nav = {m['code']: m['applicable'] for m in self.fin._modules_nav()}

        requirement.active = False
        self.fin.invalidate_recordset()

        self.assertEqual(self.fin.applicable_count, before - 1)
        self.assertFalse(self.fin.answer_ids.filtered(lambda a: a.requirement_id == requirement),
                         "it is no longer one of the assessment's answers")
        nav = {m['code']: m['applicable'] for m in self.fin._modules_nav()}
        self.assertEqual(nav[module.code], before_nav[module.code] - 1,
                         "and the module stops counting it")
        self.assertNotIn(requirement.id,
                         [i['id'] for i in self.fin._engine_items() if 'id' in i],
                         "nor does the rendering engine still print it")

    def test_a_retired_requirement_is_not_answered_twice(self):
        """Its line survives for the record, so topping the assessment up must not
        create a second one."""
        line = self.fin.answer_ids[:1]
        requirement = line.requirement_id
        requirement.active = False
        self.fin._ensure_answers()
        self.assertEqual(
            self.env['azm.fin.answer'].with_context(active_test=False).search_count(
                [('assessment_id', '=', self.fin.id), ('requirement_id', '=', requirement.id)]),
            1)

    # ------------------------------------------------------------------ reordered rules
    def _reload_with_swapped_rules(self):
        """Reload the catalogue with the two rules of one question written the other
        way round — the edit that used to re-point findings at the wrong risk."""
        with file_open('azm_operating_model/data/catalogue.json', 'rb') as handle:
            catalogue = json.load(handle)
        seen, pair = {}, None
        for index, rule in enumerate(catalogue['rules']):
            key = (rule[0], rule[1])
            if key in seen:
                pair = (seen[key], index)
                break
            seen[key] = index
        self.assertTrue(pair, "the catalogue has a question carrying two rules")
        first, second = pair
        catalogue['rules'][first], catalogue['rules'][second] = (
            catalogue['rules'][second], catalogue['rules'][first])
        raw = json.dumps(catalogue, ensure_ascii=False).encode()
        with patch('odoo.addons.azm_operating_model.models.azm_stage.file_open',
                   return_value=io.BytesIO(raw)):
            self.env['azm.stage']._load_catalogue()

    def test_a_rule_keeps_its_own_trigger_when_the_catalogue_is_reordered(self):
        Rule = self.env['azm.risk.rule']
        before = {r.id: (r.trigger_option_id.id, r.fact) for r in Rule.search([])}
        self._reload_with_swapped_rules()
        after = {r.id: (r.trigger_option_id.id, r.fact) for r in Rule.search([])}
        self.assertEqual(after, before,
                         "no rule took another's trigger or text just because the "
                         "catalogue listed them the other way round")

    def test_a_reviewed_finding_follows_its_rule(self):
        """A finding that has been scored, treated and closed must still describe the
        risk it was raised for after a reload."""
        rule = self.env['azm.risk.rule'].search([], limit=1)
        finding = self.env['azm.finding'].create({
            'assessment_id': self.proc.id, 'stage_id': rule.stage_id.id, 'code': rule.code,
            'fact': rule.fact, 'risk': rule.risk, 'state': 'closed',
            'evidence': 'أُقفلت بدليل', 'likelihood': '4', 'impact': '5'})
        trigger = rule.trigger_option_id

        self._reload_with_swapped_rules()

        finding.invalidate_recordset()
        rule.invalidate_recordset()
        self.assertEqual(finding.code, rule.code, "it travelled with the rule's new code")
        self.assertEqual(rule.trigger_option_id, trigger, "which still watches the same answer")
        self.assertEqual(finding.fact, rule.fact, "and still describes the same risk")
        self.assertEqual((finding.state, finding.evidence, finding.score),
                         ('closed', 'أُقفلت بدليل', 20), "with the reviewer's work intact")

    def test_a_rule_code_names_the_answer_that_fires_it(self):
        """So it is the same on every database and does not move when rules are
        reordered — it used to be a counter over the order they were written in."""
        for rule in self.env['azm.risk.rule'].search([]):
            self.assertEqual(
                rule.code,
                f"R-{rule.stage_id.code}-{rule.question_id.key}-{rule.trigger_option_id.sequence:02d}")
        codes = self.env['azm.risk.rule'].search([]).mapped('code')
        self.assertEqual(len(set(codes)), len(codes))
