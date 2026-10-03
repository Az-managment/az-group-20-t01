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


@tagged("post_install", "-at_install")
class TestAzmFinOptionIntegrity(TransactionCase):
    """Every question must offer the options that answer it — no more, no less,
    and never another question's."""

    def test_every_choice_question_has_options(self):
        Question = self.env["azm.fin.question"]
        self.assertFalse(
            Question.search([("qtype", "in", ("select", "multi")), ("option_ids", "=", False)]),
            "a choice question has no options")
        self.assertFalse(
            Question.search([("qtype", "=", "number"), ("option_ids", "!=", False)]),
            "a number question carries options")

    def test_table_questions_keep_their_escape_options(self):
        """A table question still offers «لا يوجد» / «لا أعرف», otherwise the
        answerer is forced to fill a grid that may not apply."""
        tables = self.env["azm.fin.question"].search([("qtype", "=", "table")])
        self.assertEqual(len(tables), 53)
        self.assertFalse(tables.filtered(lambda q: not q.option_ids))

    def test_no_option_is_shared_between_questions(self):
        """Options are owned by one question; a shared row would let an answer
        point at a question it does not belong to."""
        self.env.cr.execute("""
            SELECT count(*) FROM azm_fin_option WHERE question_id IS NULL
        """)
        self.assertEqual(self.env.cr.fetchone()[0], 0)

    def test_only_the_standard_scales_repeat(self):
        """The four standard scales repeat on every requirement by design.
        Any other repeated set must be a deliberately shared vocabulary, never
        a requirement-specific question wearing someone else's answers."""
        questions = self.env["azm.fin.question"].search([("role", "in", ("state", "impl", "rule", "target"))])
        by_role = {}
        for question in questions:
            names = tuple(question.option_ids.sorted("sequence").mapped("name"))
            by_role.setdefault(question.role, set()).add(names)
        for role, sets in by_role.items():
            self.assertEqual(len(sets), 1, f"the {role} scale is not consistent")


@tagged("post_install", "-at_install")
class TestAzmFinGridColumns(TransactionCase):
    """A grid cell should offer what it can rather than ask for free text."""

    def test_a_listed_column_is_a_dropdown(self):
        requirement = self.env["azm.fin.requirement"].search([("profile", "=", "C")], limit=1)
        by_label = {c["label"]: c for c in requirement._schema()["columns"]}
        self.assertEqual(by_label["أساس الحساب"]["type"], "select")
        self.assertEqual(by_label["العملة"]["type"], "select")

    def test_a_date_column_is_a_date_field(self):
        requirement = self.env["azm.fin.requirement"].search([("profile", "=", "C")], limit=1)
        by_label = {c["label"]: c for c in requirement._schema()["columns"]}
        self.assertEqual(by_label["تاريخ السريان"]["type"], "date")

    def test_the_unit_column_offers_a_list(self):
        """«الوحدة» has no list in the catalogue; the vocabulary is supplied."""
        columns = self.env["azm.fin.requirement"].search(
            [("profile", "=", "C")], limit=1)._schema()["columns"]
        unit = next(c for c in columns if c["label"] == "الوحدة")
        self.assertEqual(unit["type"], "select")
        self.assertIn("يوم", unit["options"])
        self.assertIn("نسبة مئوية", unit["options"])
        # currency lives in its own column, so it must not be repeated here
        self.assertNotIn("EGP جنيه", unit["options"])

    def test_a_period_column_stays_free_text(self):
        """«التاريخ/الفترة» also accepts a period, which a date picker cannot
        express, so it must not be narrowed to a date."""
        from odoo.addons.azm_operating_model.models import fin_engine
        self.assertEqual(fin_engine.column_type("التاريخ/الفترة", None), "text")
        self.assertEqual(fin_engine.column_type("تاريخ السريان", None), "date")
        # an enumerated column stays a dropdown even if its label says موعد
        self.assertEqual(fin_engine.column_type("موعد الانسحاب", ["نعم", "لا"]), "select")

    def test_an_open_column_still_offers_suggestions(self):
        """«المعادلة أو الشرائح» holds the real formula, so it must stay
        typeable; it offers a list of shapes rather than replacing the text."""
        columns = self.env["azm.fin.requirement"].search(
            [("profile", "=", "C")], limit=1)._schema()["columns"]
        formula = next(c for c in columns if c["label"] == "المعادلة أو الشرائح")
        self.assertEqual(formula["type"], "suggest")
        self.assertIn("شرائح تصاعدية", formula["suggestions"])
        self.assertFalse(formula["options"], "a suggestion column must not be a closed list")


    def test_the_component_column_offers_a_vocabulary(self):
        """«المكوّن» suggests the generic parts a calculation is built from, but
        stays typeable because every rule computes something different."""
        columns = self.env["azm.fin.requirement"].search(
            [("profile", "=", "C")], limit=1)._schema()["columns"]
        component = next(c for c in columns if c["label"] == "المكوّن")
        self.assertEqual(component["type"], "suggest")
        self.assertIn("النسبة", component["suggestions"])
        self.assertFalse(component["options"])


@tagged("post_install", "-at_install")
class TestAzmFinOutputs(TransactionCase):
    """Every answer template must have an output that shows it."""

    def test_every_profile_has_its_own_output(self):
        from odoo.addons.azm_operating_model.models import fin_engine
        from odoo.addons.azm_operating_model.models.azm_fin_catalogue import PROFILES
        covered = {p for profiles in fin_engine.TAB_PROFILES.values() for p in profiles}
        self.assertFalse(set(PROFILES) - covered,
                         "an answer template has no output tab, so its answers are invisible")
        # and no tab mixes two templates
        for tab, profiles in fin_engine.TAB_PROFILES.items():
            self.assertEqual(len(profiles), 1, f"{tab} mixes templates: {profiles}")

    def test_no_requirement_falls_outside_the_outputs(self):
        from odoo.addons.azm_operating_model.models import fin_engine
        covered = {p for profiles in fin_engine.TAB_PROFILES.values() for p in profiles}
        orphans = self.env["azm.fin.requirement"].search([("profile", "not in", list(covered))])
        self.assertFalse(orphans, f"{len(orphans)} requirements have no output")

    def test_every_tab_has_a_document_code(self):
        from odoo.addons.azm_operating_model.models import fin_engine
        for tab, _title in fin_engine.OUTPUT_TABS:
            self.assertIn(tab, fin_engine.DOC_CODES, f"{tab} has no document code")

    def test_the_workflow_grid_offers_a_list_everywhere(self):
        """Every column of a دورة عمل grid either picks from a list or
        suggests one; none is a bare text box."""
        columns = self.env["azm.fin.requirement"].search(
            [("profile", "=", "W")], limit=1)._schema()["columns"]
        self.assertEqual(len(columns), 8)
        bare = [c["label"] for c in columns if c["type"] == "text"]
        self.assertFalse(bare, f"workflow columns with no list: {bare}")

    def test_the_outputs_show_the_answers(self):
        """A tab that renders nothing from its answers is a tab nobody can use."""
        assessment = self.env["azm.fin.assessment"].search([], limit=1)
        if not assessment:
            self.skipTest("no financial assessment in this database")
        for profile, tab in (("L", "lists"), ("C", "calc"), ("P", "policies"), ("W", "workflow")):
            line = assessment.answer_ids.filtered(
                lambda a: a.profile == profile and a.applicable)[:1]
            if not line:
                continue
            token = "ZZ-%s-TOKEN" % profile
            columns = line.requirement_id._schema()["columns"]
            row = [c["options"][0] if c["options"] else token for c in columns]
            line._workspace_write({"state": "full", "current": token, "table": [row]})
            html = assessment.workspace_output(line.module_id.code, tab, "model") or ""
            self.assertIn(line.code, html, f"{tab} does not show {line.code}")
            self.assertIn(token, html, f"{tab} does not show what was answered")

    def test_only_genuinely_open_columns_are_free_text(self):
        """Every grid column offers a list unless the cell holds something a
        list cannot express: a name, a code, a field list, a threshold.

        If a new column shows up here, it needs a vocabulary or an exemption —
        it must not quietly become another box people fill five different ways.
        """
        OPEN = {
            "العنصر",              # the item a reference list enumerates
            "الكود إن وجد",         # a code
            "القاعدة",              # the wording of the rule
            "اسم التقرير/المؤشر",   # a report name
            "الحقول/المعادلة",      # the fields a report is built from
            "الحقول",
            "حد التنبيه",           # a threshold value
            "معرف منع التكرار",     # a technical key
        }
        free = set()
        for requirement in self.env["azm.fin.requirement"].search([]):
            for column in requirement._schema()["columns"]:
                if column["type"] == "text":
                    free.add(column["label"])
        self.assertFalse(free - OPEN, f"columns with no list and no exemption: {sorted(free - OPEN)}")

    def test_the_authority_grid_reuses_the_sheets_own_operations(self):
        """«العملية» offers the نوع العملية list the sheet already gives on
        FIN-004, rather than a parallel invention."""
        columns = self.env["azm.fin.requirement"].search(
            [("profile", "=", "A")], limit=1)._schema()["columns"]
        operation = next(c for c in columns if c["label"] == "العملية")
        self.assertEqual(operation["type"], "suggest")
        for expected in ("قيد يومية", "طلب شراء", "سند صرف", "كشف رواتب"):
            self.assertIn(expected, operation["suggestions"])

    def test_each_output_shows_only_its_own_template(self):
        """A tab that leaks another template's requirements is showing the
        reader a document that is not the one it claims to be."""
        import re
        from odoo.addons.azm_operating_model.models import fin_engine
        assessment = self.env["azm.fin.assessment"].search([], limit=1)
        if not assessment:
            self.skipTest("no financial assessment in this database")
        profile_of = {r.code: r.profile
                      for r in self.env["azm.fin.requirement"].search([])}
        for tab, profiles in fin_engine.TAB_PROFILES.items():
            html = assessment.workspace_output(False, tab, "model") or ""
            shown = set(re.findall(r"\b((?:FIN|HRF)-\d{3})\b", html))
            stray = {c for c in shown if profile_of.get(c) not in profiles}
            self.assertFalse(stray, f"{tab} shows requirements of another template: {sorted(stray)}")

    def test_an_output_shows_every_applicable_requirement(self):
        """Anything applicable and answered must reach its document; a silently
        dropped requirement is worse than an empty one."""
        import re
        from odoo.addons.azm_operating_model.models import fin_engine
        assessment = self.env["azm.fin.assessment"].search([], limit=1)
        if not assessment:
            self.skipTest("no financial assessment in this database")
        for tab, profiles in fin_engine.TAB_PROFILES.items():
            html = assessment.workspace_output(False, tab, "model") or ""
            shown = len(set(re.findall(r"\b((?:FIN|HRF)-\d{3})\b", html)))
            applicable = len(assessment.answer_ids.filtered(
                lambda a: a.profile in profiles and a.applicable))
            self.assertEqual(shown, applicable, f"{tab} renders {shown} of {applicable}")

    def test_every_output_is_well_formed(self):
        import xml.etree.ElementTree as ET
        from odoo.addons.azm_operating_model.models import fin_engine
        assessment = self.env["azm.fin.assessment"].search([], limit=1)
        if not assessment:
            self.skipTest("no financial assessment in this database")
        for tab, _title in fin_engine.OUTPUT_TABS:
            html = assessment.workspace_output(False, tab, "model") or ""
            self.assertTrue(html.strip(), f"{tab} renders nothing")
            ET.fromstring(f"<root>{html}</root>")   # raises if the markup is broken

    def test_each_output_renders_in_its_own_style(self):
        """Only دورات العمل renders a step list and only الصلاحيات checks the
        separation of duties; a policy rendered as a workflow would be the
        wrong document even with the right requirements in it."""
        from odoo.addons.azm_operating_model.models import fin_engine
        assessment = self.env["azm.fin.assessment"].search([], limit=1)
        if not assessment:
            self.skipTest("no financial assessment in this database")
        for profile in ("L", "C", "P", "W", "A", "R", "I"):
            line = assessment.answer_ids.filtered(
                lambda a: a.profile == profile and a.applicable)[:1]
            if not line:
                continue
            columns = line.requirement_id._schema()["columns"]
            row = [c["options"][0] if c["options"] else "قيمة" for c in columns]
            line._workspace_write({"state": "full", "current": "قاعدة", "table": [row]})

        for tab in fin_engine.TAB_PROFILES:
            html = assessment.workspace_output(False, tab, "model") or ""
            steps = "o_azm_steps" in html
            self.assertEqual(steps, tab == "workflow",
                             f"{tab} {'renders' if steps else 'does not render'} a step list")

    def test_each_output_is_its_own_document(self):
        """Two tabs sharing a document code would file two different outputs
        under one reference."""
        from odoo.addons.azm_operating_model.models import fin_engine
        codes = [fin_engine.DOC_CODES[tab] for tab, _t in fin_engine.OUTPUT_TABS]
        self.assertEqual(len(codes), len(set(codes)), f"duplicate document codes: {codes}")

    def _authority_row(self, creator, reviewer, approver, conflict, evidence):
        assessment = self.env["azm.fin.assessment"].search([], limit=1)
        line = assessment.answer_ids.filtered(
            lambda a: a.profile == "A" and a.applicable)[:1]
        labels = [c["label"] for c in line.requirement_id._schema()["columns"]]
        at = {label: n for n, label in enumerate(labels)}
        row = [""] * len(labels)
        row[at["العملية"]] = "طلب شراء"
        row[at["المنشئ"]], row[at["المراجع"]], row[at["المعتمد"]] = creator, reviewer, approver
        row[at["التعارض"]], row[at["دليل الرقابة"]] = conflict, evidence
        line._workspace_write({"state": "full", "current": "قاعدة", "table": [row]})
        return assessment.workspace_output(line.module_id.code, "authority", "module") or ""

    def test_the_same_person_twice_is_flagged(self):
        html = self._authority_row("موظف", "مراجع", "موظف", "لا يوجد", "سجل النظام")
        self.assertIn("نفس الدور", html)

    def test_distinct_roles_are_not_flagged(self):
        html = self._authority_row("موظف", "مراجع", "المدير المالي", "لا يوجد", "سجل النظام")
        self.assertNotIn("نفس الدور", html)
        self.assertNotIn("تعارض معلن", html)

    def test_a_declared_conflict_reaches_the_document(self):
        """The roles can all differ and the conflict still be real; the
        duplication check cannot see that, so the declared value must carry."""
        html = self._authority_row("موظف", "مراجع", "المدير المالي",
                                   "يوجد ويحتاج معالجة", "سجل النظام")
        self.assertIn("تعارض معلن", html)

    def test_an_accepted_conflict_is_not_flagged(self):
        html = self._authority_row("موظف", "مراجع", "المدير المالي",
                                   "يوجد ومقبول برقابة بديلة", "سجل النظام")
        self.assertNotIn("تعارض معلن", html)

    def test_an_authority_with_no_evidence_is_noted(self):
        html = self._authority_row("موظف", "مراجع", "المدير المالي", "لا يوجد", "")
        self.assertIn("لا يوجد دليل رقابة", html)
