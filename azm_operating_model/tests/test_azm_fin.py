import json

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.azm_operating_model.models import fin_engine


@tagged("post_install", "-at_install")
class TestAzmFinancialModel(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Scope = cls.env["azm.fin.scope"]
        cls.edu, cls.work, cls.prj = (Scope.search([("code", "=", c)]) for c in ("EDU", "WORK", "PRJ"))
        cls.entity = cls.env["azm.entity"].create({"code": "FTA", "name": "كيان مالي أ",
                                                   "fin_scope_ids": [(6, 0, (cls.edu | cls.work).ids)]})
        cls.other = cls.env["azm.entity"].create({"code": "FTB", "name": "كيان مالي ب"})
        cls.preparer = new_test_user(cls.env, "fin_prep", groups="azm_operating_model.azm_group_user")
        cls.preparer_b = new_test_user(cls.env, "fin_prep_b", groups="azm_operating_model.azm_group_user")
        cls.reviewer = new_test_user(cls.env, "fin_rev", groups="azm_operating_model.azm_group_reviewer")
        cls.manager = new_test_user(cls.env, "fin_mgr", groups="azm_operating_model.azm_group_manager")
        cls.entity.user_ids = [(6, 0, [cls.preparer.id, cls.reviewer.id])]
        cls.other.user_ids = [(6, 0, [cls.preparer_b.id])]
        cls.assessment = cls.env["azm.fin.assessment"].with_user(cls.preparer).create(
            {"entity_id": cls.entity.id, "reviewer_id": cls.reviewer.id})

    def _line(self, code, assessment=None):
        return (assessment or self.assessment).answer_ids.filtered(lambda a: a.code == code)

    def test_catalogue(self):
        Module = self.env["azm.fin.module"]
        Requirement = self.env["azm.fin.requirement"]
        # The spreadsheet taxonomy: 19 live modules, the 17 superseded ones
        # archived rather than deleted so approved versions still name them.
        self.assertEqual(Module.search_count([]), 19)
        self.assertEqual(Module.with_context(active_test=False).search_count([]), 36)
        self.assertFalse(Requirement.search([("module_id.active", "=", False)]),
                         "a requirement is hanging off a retired module")
        self.assertEqual(Requirement.search_count([]), 167)
        self.assertEqual(Requirement.search_count([("source", "=", "HRF")]), 60)
        self.assertEqual(len(Module.search([("code", "=", "FIN.ADV")])._details()), 22)
        self.assertEqual(len(self.assessment.answer_ids), 167)
        self.assertEqual(len(self.assessment.qanswer_ids), 1136)

    def test_every_question_has_its_own_options(self):
        """The point of importing the spreadsheet: a question must offer the
        options that answer it, not another question's scale."""
        Question = self.env["azm.fin.question"]
        self.assertEqual(Question.search_count([]), 1136)
        self.assertEqual(self.env["azm.fin.option"].search_count([]), 6121)
        self.assertEqual(self.env["azm.fin.topic"].search_count([]), 215)
        self.assertEqual(self.env["azm.fin.opening.question"].search_count([]), 3655)

        choice = Question.search([("qtype", "in", ("select", "multi"))])
        self.assertFalse(choice.filtered(lambda q: not q.option_ids),
                         "a choice question was imported with no options")
        # The four standard scales repeat by design; everything else must not.
        standard = {tuple(q.option_ids.mapped("name"))
                    for q in Question.search([("role", "in", ("state", "impl", "rule", "target"))])}
        self.assertEqual(len(standard), 4, "the standard scales are not consistent")
        specific = Question.search([("role", "in", ("main", "followup")),
                                    ("qtype", "in", ("select", "multi"))])
        self.assertFalse(
            specific.filtered(lambda q: tuple(q.option_ids.mapped("name")) in standard),
            "a question answers with one of the standard scales instead of its own")

    def test_follow_up_conditions_point_backwards(self):
        """A forward reference would never fire, and would do so silently."""

        def leaves(condition):
            """A gated follow-up keeps its own condition inside an "all"."""
            if "all" in condition or "any" in condition:
                for child in condition.get("all") or condition.get("any"):
                    yield from leaves(child)
            else:
                yield condition

        conditioned = self.env["azm.fin.question"].search([("condition", "!=", False)])
        # 519 from the sheet, plus the gate put on every main and follow-up
        # question that did not already carry one.
        self.assertEqual(len(conditioned), 969)
        for question in conditioned:
            siblings = question.requirement_id.question_ids
            for leaf in leaves(json.loads(question.condition)):
                trigger = siblings.filtered(lambda q: q.key == leaf["field"])
                self.assertTrue(trigger, f"{question.code}: trigger {leaf['field']} missing")
                self.assertLess(trigger.sequence, question.sequence, question.code)
                self.assertEqual(trigger.qtype, "select",
                                 f"{question.code}: engine cannot match a list with 'in'")
                offered = set(trigger.option_ids.mapped("name"))
                self.assertFalse(set(leaf["in"]) - offered,
                                 f"{question.code}: names options {trigger.key} never offers")

    def test_the_gate_is_first_in_every_requirement(self):
        """Every requirement asks «هل هذا مطبق؟» before anything else."""
        firsts = self.env["azm.fin.question"].search([("sequence", "=", 1)])
        self.assertEqual(len(firsts), 167)
        self.assertEqual(set(firsts.mapped("role")), {"state"})

    def test_applicability_follows_activities(self):
        self.assertEqual(self.assessment.scope_ids, self.edu | self.work)
        self.assertTrue(self._line("FIN-024").applicable)     # EDU
        self.assertTrue(self._line("HRF-006").applicable)     # WORK
        self.assertFalse(self._line("FIN-062").applicable)    # PRJ
        self.assessment.scope_ids = [(4, self.prj.id)]
        self.assertTrue(self._line("FIN-062").applicable)
        # "PRJ" is now an archived code: workspace_data falls back to the first
        # module when it cannot match, so assert which module came back too.
        data = self.assessment.workspace_data("FIN.PRJ")
        self.assertEqual(data["module"]["code"], "FIN.PRJ")
        expected = self.env["azm.fin.requirement"].search_count([
            ("module_id.code", "=", "FIN.PRJ"),
            ("scope_code", "in", ("ALL", *self.assessment.scope_ids.mapped("code"))),
        ])
        self.assertEqual(len(data["requirements"]), expected)

    def test_done_rule_and_outputs(self):
        a = self.assessment.with_user(self.preparer)
        line = self._line("FIN-004")
        res = a.workspace_save(line.id, {"state": "partial"})
        self.assertFalse(res["answer"]["done"])  # the gap is mandatory for «partial»
        res = a.workspace_save(line.id, {"gap": "لا توجد مصفوفة صلاحيات مكتوبة", "current": "اعتماد شفهي",
                                         "table": [["الصرف", "موظف", "مراجع", "موظف", "", "", "", ""]]},
                               module_code="FIN.GOV", tab="authority")
        self.assertTrue(res["answer"]["done"])
        self.assertIn("نفس الدور", res["output"])        # creator == approver -> segregation warning
        for tab, _title in fin_engine.OUTPUT_TABS:
            self.assertTrue(a.workspace_output("FIN.GOV", tab, "module"))
            self.assertTrue(a.workspace_output("FIN.GOV", tab, "model"))
        self.assertIn("FIN-004", a.workspace_output("FIN.GOV", "gaps", "module"))

    def test_lifecycle_and_lock(self):
        a = self.assessment
        a.with_user(self.preparer).action_fill_demo()
        self.assertEqual(a.done_count, a.applicable_count)
        a.with_user(self.preparer).action_submit()
        self.assertEqual(a.state, "review")
        self.assertTrue(a.activity_ids.filtered(lambda act: act.user_id == self.reviewer))
        with self.assertRaises(UserError):
            a.with_user(self.preparer).action_approve()
        a.with_user(self.manager).action_approve()
        self.assertEqual((a.state, len(a.version_ids)), ("approved", 1))
        with self.assertRaises((UserError, AccessError)):
            a.with_user(self.preparer).workspace_save(self._line("FIN-001").id, {"state": "na"})
        new = self.env["azm.fin.assessment"].browse(a.with_user(self.manager).action_new_version()["res_id"])
        self.assertEqual((new.version, new.state, a.state), (2, "draft", "archived"))
        self.assertEqual(new.done_count, a.done_count)

    def test_each_user_sees_own_data(self):
        theirs = self.env["azm.fin.assessment"].with_user(self.preparer_b).create({"entity_id": self.other.id})
        Assessment = self.env["azm.fin.assessment"]
        ids = (self.assessment | theirs).ids
        self.assertEqual(Assessment.with_user(self.preparer).search([("id", "in", ids)]), self.assessment)
        self.assertEqual(Assessment.with_user(self.preparer_b).search([("id", "in", ids)]), theirs)
        self.assertEqual(Assessment.with_user(self.reviewer).search([("id", "in", ids)]), self.assessment)
        self.assertEqual(Assessment.with_user(self.manager).search([("id", "in", ids)]), self.assessment | theirs)
        unassigned = self.env["azm.entity"].create({"code": "FTC", "name": "كيان غير مسند"})
        with self.assertRaises(AccessError):
            Assessment.with_user(self.preparer_b).create({"entity_id": unassigned.id})
        answers = self.env["azm.fin.answer"].with_user(self.preparer_b).search([("assessment_id", "in", ids)])
        self.assertEqual(answers.assessment_id, theirs)


@tagged("post_install", "-at_install")
class TestAzmFinRollup(TransactionCase):
    """The roll-up azm.fin.answer must follow the standard questions, and must
    not be writable behind their back."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        scope = cls.env["azm.fin.scope"].search([("code", "=", "EDU")])
        cls.entity = cls.env["azm.entity"].create({
            "code": "FRU", "name": "كيان التجميع", "fin_scope_ids": [(6, 0, scope.ids)]})
        cls.assessment = cls.env["azm.fin.assessment"].create({"entity_id": cls.entity.id})
        cls.line = cls.assessment.answer_ids.filtered(lambda a: a.code == "FIN-004")

    def _line_for(self, role):
        return self.line.qanswer_ids.filtered(lambda q: q.role == role)[:1]

    def test_every_requirement_has_its_standard_questions(self):
        roles = self.line.qanswer_ids.mapped("role")
        for role in ("state", "impl", "rule", "target"):
            self.assertIn(role, roles)

    def test_the_roll_up_follows_the_questions(self):
        state = self._line_for("state")
        state.option_id = state.question_id.option_ids.filtered(
            lambda o: o.name == "مطبق جزئيًا").id
        state.text = "تغطية جزئية"
        self.assertEqual(self.line.state, "partial")
        self.assertEqual(self.line.current, "تغطية جزئية")

        impl = self._line_for("impl")
        impl.option_ids = [(6, 0, impl.question_id.option_ids.filtered(
            lambda o: o.name in ("SAP", "Excel")).ids)]
        self.assertEqual(self.line.impl, "SAP,Excel")

        target = self._line_for("target")
        target.option_id = target.question_id.option_ids.filtered(
            lambda o: o.name == "تحسين").id
        self.assertEqual(self.line.future_stance, "تحسين")

    def test_an_unknown_answer_is_not_a_state(self):
        state = self._line_for("state")
        state.option_id = state.question_id.option_ids.filtered(
            lambda o: o.name == "لا أعرف").id
        self.assertFalse(self.line.state, "«لا أعرف» must not count as a state")

    def test_na_is_declared_on_the_requirement(self):
        """No question produces «لا ينطبق»; it is declared on the requirement."""
        self.line.na_declared = True
        self.assertEqual(self.line.state, "na")

    def test_the_derived_fields_refuse_a_direct_write(self):
        with self.assertRaises(UserError):
            self.line.write({"state": "full"})
        with self.assertRaises(UserError):
            self.line.write({"impl": "يدوي أو ورقي"})

    def test_the_workspace_still_writes_through_the_questions(self):
        """The OWL workspace and action_fill_demo both go through here."""
        self.line._workspace_write({"state": "full", "current": "مطبق بالكامل اليوم",
                                    "impl": ["SAP"]})
        self.assertEqual(self.line.state, "full")
        self.assertEqual(self.line.impl, "SAP")
        self.assertEqual(self._line_for("state").option_id.name, "مطبق بالكامل")
        self.assertTrue(self.line.is_done)


@tagged("post_install", "-at_install")
class TestAzmFinWorkspaceQuestions(TransactionCase):
    """Follow-ups are resolved on the server, so the client never has to decide
    which question to show."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        scope = cls.env["azm.fin.scope"].search([("code", "=", "EDU")])
        cls.entity = cls.env["azm.entity"].create({
            "code": "FWQ", "name": "كيان الأسئلة", "fin_scope_ids": [(6, 0, scope.ids)]})
        cls.assessment = cls.env["azm.fin.assessment"].create({"entity_id": cls.entity.id})
        cls.line = cls.assessment.answer_ids.filtered(lambda a: a.code == "FIN-004")

    def _keys(self):
        return [q["key"] for q in self.line._question_dicts()]

    def _state_line(self):
        return self.line.qanswer_ids.filtered(lambda q: q.role == "state")[:1]

    def test_only_the_gate_is_asked_first(self):
        """«هل هذا مطبق؟» comes first and nothing else is asked until it is
        answered — the same gate procurement puts on a stage."""
        self.assertEqual(self._keys(), ["Q003"])
        self.assertEqual(self.line.qanswer_ids.filtered(
            lambda q: q.sequence == 1).role, "state")

    def test_an_unknown_trigger_keeps_the_follow_ups_hidden(self):
        line = self._state_line()
        line.option_id = line.question_id.option_ids.filtered(lambda o: o.name == "لا أعرف").id
        self.assertEqual(self._keys(), ["Q003"])

    def test_answering_the_trigger_reveals_them(self):
        line = self._state_line()
        line.option_id = line.question_id.option_ids.filtered(
            lambda o: o.name == "مطبق بالكامل").id
        # the gate first, then the requirement's own questions, then the scales
        self.assertEqual(self._keys(), ["Q003", "Q001", "Q002", "Q004", "Q005", "Q006"])
        # and the flags are persisted, so counts and lists agree
        self.assertTrue(all(q.is_visible for q in self.line.qanswer_ids))

    def test_the_rpc_round_trip_reveals_the_follow_ups(self):
        data = self.assessment.workspace_data("FIN.GOV")
        req = next(r for r in data["requirements"] if r["code"] == "FIN-004")
        self.assertEqual([q["key"] for q in req["questions"]], ["Q003"])

        state = next(q for q in req["questions"] if q["role"] == "state")
        option = next(o for o in state["options"] if o["name"] == "مطبق بالكامل")
        result = self.assessment.workspace_answer_question(
            state["line_id"], {"option_id": option["id"]}, module_code="FIN.GOV")
        fresh = next(r for r in result["requirements"] if r["code"] == "FIN-004")
        self.assertEqual(len(fresh["questions"]), 6)
        self.assertEqual(fresh["state"], "full")

    def test_a_table_column_offers_its_own_choices(self):
        """A column that lists its choices in the sheet becomes a dropdown; one
        that does not stays a free-text cell."""
        question = self.env["azm.fin.question"].search(
            [("qtype", "=", "table"), ("columns_json", "like", "options")], limit=1)
        columns = question._columns()
        self.assertTrue(columns, question.code)
        self.assertTrue(all(isinstance(c, dict) and "label" in c for c in columns))
        self.assertTrue(any(c.get("options") for c in columns),
                        "no column offers a choice list")

    def test_an_option_from_another_question_is_refused(self):
        """The whole point: a question answers with its own options."""
        main = self.line.qanswer_ids.filtered(lambda q: q.role == "main")[:1]
        foreign = self.env["azm.fin.option"].search(
            [("question_id", "!=", main.question_id.id)], limit=1)
        with self.assertRaises(UserError):
            self.assessment.workspace_answer_question(main.id, {"option_id": foreign.id})

    def test_answering_is_refused_outside_draft(self):
        line = self._state_line()
        self.assessment.with_context(azm_skip_lock=True).state = "approved"
        with self.assertRaises(UserError):
            self.assessment.workspace_answer_question(line.id, {"text": "بعد الاعتماد"})
