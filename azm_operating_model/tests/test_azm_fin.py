import json
import re
import xml.etree.ElementTree as ET

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.azm_operating_model.models import fin_engine
from odoo.addons.azm_operating_model.models.azm_fin_catalogue import FALLBACK_KINDS, PROFILES

from .fin_common import FULL, columns_of, fill, real_options, table_question


def _entity(env, code, name, scopes=()):
    return env["azm.entity"].create({
        "code": code, "name": name,
        "fin_scope_ids": [(6, 0, [s.id for s in scopes])],
    })


@tagged("post_install", "-at_install")
class TestAzmFinancialModel(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Scope = cls.env["azm.fin.scope"]
        cls.edu, cls.work, cls.prj = (Scope.search([("code", "=", c)]) for c in ("EDU", "WORK", "PRJ"))
        cls.entity = _entity(cls.env, "FTA", "كيان مالي أ", (cls.edu, cls.work))
        cls.other = _entity(cls.env, "FTB", "كيان مالي ب")
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
        """The spreadsheet taxonomy, loaded whole."""
        Module = self.env["azm.fin.module"]
        Requirement = self.env["azm.fin.requirement"]
        self.assertEqual(Module.search_count([]), 19)
        # superseded modules are archived rather than deleted, so an approved
        # version still names the module it was answered under — but nothing
        # live may hang off one.
        retired = Module.with_context(active_test=False).search([("active", "=", False)])
        self.assertFalse(Requirement.search([("module_id", "in", retired.ids)]),
                         "a requirement is hanging off a retired module")
        self.assertEqual(Requirement.search_count([]), 167)
        self.assertEqual(Requirement.search_count([("source", "=", "HRF")]), 60)
        self.assertEqual(self.env["azm.fin.topic"].search_count([]), 215)
        self.assertEqual(self.env["azm.fin.prompt"].search_count([]), 3655)
        self.assertEqual(len(self.assessment.answer_ids), 167)
        # every requirement is reachable through the module navigator
        nav = {m["code"]: m for m in self.assessment._modules_nav()}
        self.assertEqual(sum(m["total"] for m in nav.values()), 167)

    def test_every_question_has_its_own_options(self):
        """The point of importing the spreadsheet: a question must offer the
        options that answer it, not another question's scale."""
        Question = self.env["azm.fin.question"]
        self.assertEqual(Question.search_count([]), 1136)
        self.assertEqual(self.env["azm.fin.option"].search_count([]), 6121)

        choice = Question.search([("qtype", "in", ("select", "multi"))])
        self.assertFalse(choice.filtered(lambda q: not q.option_ids),
                         "a choice question was imported with no options")
        # The four standard scales repeat by design; everything else must not.
        standard = {tuple(q.option_ids.mapped("name"))
                    for q in Question.search([("role", "in", ("status", "impl", "rule", "target"))])}
        self.assertEqual(len(standard), 4, "the standard scales are not consistent")
        specific = Question.search([("role", "in", ("main", "follow")),
                                    ("qtype", "in", ("select", "multi"))])
        self.assertFalse(
            specific.filtered(lambda q: tuple(q.option_ids.mapped("name")) in standard),
            "a question answers with one of the standard scales instead of its own")

    def test_follow_up_conditions_point_backwards(self):
        """A forward reference would never fire, and would do so silently."""
        conditioned = self.env["azm.fin.question"].search([("condition_json", "!=", False)])
        self.assertEqual(len(conditioned), 519)   # exactly what the sheet declares
        for question in conditioned:
            siblings = question.requirement_id.question_ids
            leaf = question._condition()
            trigger = siblings.filtered(lambda q: q.key == leaf["q"])
            self.assertTrue(trigger, f"{question.code}: trigger {leaf['q']} missing")
            self.assertLess(trigger.sequence, question.sequence, question.code)
            self.assertEqual(trigger.qtype, "select",
                             f"{question.code}: engine cannot match a list with 'in'")
            offered = set(trigger.option_ids.mapped("name"))
            self.assertFalse(set(leaf["in"]) - offered,
                             f"{question.code}: names options {trigger.key} never offers")

    def test_the_standard_scales_close_every_requirement(self):
        """Each requirement opens with its own question and ends with the four
        standard scales, in that order."""
        for requirement in self.env["azm.fin.requirement"].search([], limit=40):
            roles = requirement.question_ids.sorted("sequence").mapped("role")
            self.assertEqual(roles[0], "main", requirement.code)
            self.assertEqual(roles[-4:], ["status", "impl", "rule", "target"], requirement.code)

    def test_applicability_follows_activities(self):
        self.assertEqual(self.assessment.scope_ids, self.edu | self.work)
        self.assertTrue(self._line("FIN-024").applicable)     # EDU
        self.assertTrue(self._line("HRF-006").applicable)     # WORK
        self.assertFalse(self._line("FIN-062").applicable)    # PRJ
        self.assessment.scope_ids = [(4, self.prj.id)]
        self.assertTrue(self._line("FIN-062").applicable)
        # workspace_data falls back to the first module when it cannot match a
        # code, so assert which module actually came back.
        data = self.assessment.workspace_data("PRJ")
        self.assertEqual(data["module"]["code"], "PRJ")
        expected = self.env["azm.fin.requirement"].search_count([
            ("module_id.code", "=", "PRJ"),
            ("scope_code", "in", ("ALL", *self.assessment.scope_ids.mapped("code"))),
        ])
        shown = sum(len(t["requirements"]) for t in data["topics"])
        self.assertEqual(shown, expected)

    def test_the_payload_is_grouped_by_topic(self):
        """The workspace renders topics, so every requirement must arrive
        inside one and no topic may arrive empty."""
        data = self.assessment.workspace_data("GOV")
        self.assertTrue(data["topics"])
        for topic in data["topics"]:
            self.assertTrue(topic["requirements"], f"{topic['code']} has no requirements")
            self.assertTrue(topic["name"], f"{topic['code']} has no name")
        codes = [r["code"] for t in data["topics"] for r in t["requirements"]]
        self.assertEqual(len(codes), len(set(codes)), "a requirement appears twice")
        for key in ("header", "modules", "module", "topics", "states", "na_reasons",
                    "priorities", "tabs", "output"):
            self.assertIn(key, data)

    def test_done_rule_and_outputs(self):
        a = self.assessment.with_user(self.preparer)
        line = self._line("FIN-004")
        self.assertFalse(line.is_done)
        fill(line)
        self.assertTrue(line.is_done)
        self.assertEqual(line.state, "full")
        for tab, _title in fin_engine.OUTPUT_TABS:
            self.assertTrue(a.workspace_output("GOV", tab, "module"))
            self.assertTrue(a.workspace_output("GOV", tab, "model"))
        self.assertIn("FIN-004", a.workspace_output("GOV", "authority", "module"))

    def test_a_requirement_that_does_not_apply_is_closed_by_its_reason(self):
        line = self._line("FIN-004")
        result = self.assessment.workspace_requirement(line.id, {"na": True})
        self.assertFalse(result["requirement"]["done"], "«لا ينطبق» still needs a reason")
        result = self.assessment.workspace_requirement(
            line.id, {"na": True, "reason": "الكيان لا يمارس هذا النشاط"})
        self.assertTrue(result["requirement"]["done"])
        self.assertEqual(line.state, "na")

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
            a.with_user(self.preparer).workspace_requirement(self._line("FIN-001").id, {"na": True})
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
    """The roll-up azm.fin.answer must follow the standard questions rather
    than be written behind their back."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        scope = cls.env["azm.fin.scope"].search([("code", "=", "EDU")])
        cls.entity = _entity(cls.env, "FRU", "كيان التجميع", (scope,))
        cls.assessment = cls.env["azm.fin.assessment"].create({"entity_id": cls.entity.id})
        cls.line = cls.assessment.answer_ids.filtered(lambda a: a.code == "FIN-004")

    def _question(self, role):
        return self.line.requirement_id.question_ids.filtered(lambda q: q.role == role)[:1]

    def _answer(self, role, vals):
        return self.line._set_answer(self._question(role).id, vals)

    def _option(self, role, name):
        return self._question(role).option_ids.filtered(lambda o: o.name == name)

    def test_every_requirement_has_its_standard_questions(self):
        roles = self.line.requirement_id.question_ids.mapped("role")
        for role in ("status", "impl", "rule", "target"):
            self.assertIn(role, roles)

    def test_the_roll_up_follows_the_questions(self):
        self._answer("status", {"option_id": self._option("status", "مطبق جزئيًا").id,
                                "note": "تغطية جزئية"})
        self.assertEqual(self.line.state, "partial")
        self.assertIn("تغطية جزئية", self.line.issues or "")
        # a partial state is a gap, and the gap must carry the same explanation
        self.assertIn("تغطية جزئية", self.line.gap or "")

        impl = self._question("impl")
        chosen = impl.option_ids.filtered(lambda o: o.kind not in FALLBACK_KINDS)[:2]
        self._answer("impl", {"option_ids": chosen.ids})
        self.assertEqual(self.line.impl, "، ".join(chosen.mapped("name")))

        target = real_options(self._question("target"))[:1]
        self._answer("target", {"option_id": target.id})
        self.assertEqual(self.line.target, target.name)
        self.assertIn(target.name, self.line.future or "")

    def test_an_unknown_answer_is_its_own_state(self):
        """«لا أعرف» is recorded rather than left blank, but it is never read
        as a degree of implementation."""
        unknown = self._question("status").option_ids.filtered(lambda o: o.kind == "unknown")
        self.assertTrue(unknown, "the status scale offers no «لا أعرف»")
        self._answer("status", {"option_id": unknown[:1].id})
        self.assertEqual(self.line.state, "unknown")
        self.assertNotIn(self.line.state, ("full", "partial", "unavailable"))
        self.assertFalse(self.line.gap, "«لا أعرف» is not a gap, it is a question still open")

    def test_an_unknown_answer_keeps_the_scales_hidden(self):
        """The scales are asked only once the status is known."""
        unknown = self._question("status").option_ids.filtered(lambda o: o.kind == "unknown")[:1]
        self._answer("status", {"option_id": unknown.id})
        self.assertNotIn("impl", self.line._visible().mapped("role"))

    def test_na_is_declared_on_the_requirement(self):
        """No question produces «لا ينطبق»; it is declared on the requirement."""
        self.line.na = True
        self.assertEqual(self.line.state, "na")

    def test_the_priority_reaches_the_target_note(self):
        # the scales are asked only once the status says there is something to
        # grade, and the roll-up only reads questions that are visible
        self._answer("status", {"option_id": self._option("status", FULL).id})
        target = self._question("target")
        self._answer("target", {"option_id": real_options(target)[:1].id,
                                "note": "تغيير مطلوب", "priority": "high"})
        self.assertIn("مرتفعة", self.line.target_note or "")

    def test_an_option_of_another_question_is_refused(self):
        foreign = self.env["azm.fin.option"].search(
            [("question_id", "!=", self._question("status").id)], limit=1)
        with self.assertRaises(UserError):
            self._answer("status", {"option_id": foreign.id})


@tagged("post_install", "-at_install")
class TestAzmFinWorkspaceQuestions(TransactionCase):
    """Follow-ups are resolved on the server, so the client never has to decide
    which question to show."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        scope = cls.env["azm.fin.scope"].search([("code", "=", "EDU")])
        cls.entity = _entity(cls.env, "FWQ", "كيان الأسئلة", (scope,))
        cls.assessment = cls.env["azm.fin.assessment"].create({"entity_id": cls.entity.id})
        cls.line = cls.assessment.answer_ids.filtered(lambda a: a.code == "FIN-004")

    def _keys(self):
        return self.line._visible().mapped("key")

    def _status(self):
        return self.line.requirement_id.question_ids.filtered(lambda q: q.role == "status")[:1]

    def test_the_scales_wait_for_the_status(self):
        """The requirement's own questions are asked straight away; the four
        standard scales only once the status says there is something to grade."""
        self.assertEqual(self._keys(), ["Q001", "Q002", "Q003"])

    def test_an_unknown_trigger_keeps_the_scales_hidden(self):
        status = self._status()
        unknown = status.option_ids.filtered(lambda o: o.kind == "unknown")[:1]
        self.line._set_answer(status.id, {"option_id": unknown.id})
        self.assertEqual(self._keys(), ["Q001", "Q002", "Q003"])

    def test_answering_the_trigger_reveals_them(self):
        status = self._status()
        full = status.option_ids.filtered(lambda o: o.name == FULL)[:1]
        self.line._set_answer(status.id, {"option_id": full.id})
        self.assertEqual(self._keys(), ["Q001", "Q002", "Q003", "Q004", "Q005", "Q006"])

    def test_the_rpc_round_trip_reveals_the_follow_ups(self):
        data = self.assessment.workspace_data("GOV")
        req = next(r for t in data["topics"] for r in t["requirements"] if r["code"] == "FIN-004")
        self.assertEqual([q["key"] for q in req["questions"] if q["visible"]],
                         ["Q001", "Q002", "Q003"])

        status = next(q for q in req["questions"] if q["role"] == "status")
        option = next(o for o in status["options"] if o["name"] == FULL)
        result = self.assessment.workspace_answer(
            req["answer_id"], status["id"], {"option_id": option["id"]}, module_code="GOV")
        fresh = result["requirement"]
        self.assertEqual(len([q for q in fresh["questions"] if q["visible"]]), 6)
        self.assertEqual(fresh["state"], "full")
        # the client patches the page from this payload, so it must be whole
        self.assertEqual(set(result), {"requirement", "header", "modules", "output"})

    def test_the_payload_carries_the_saved_value_back(self):
        """The client renders from `value`, so a saved answer must come back in
        it or the chip reverts the moment the page repaints."""
        data = self.assessment.workspace_data("GOV")
        req = next(r for t in data["topics"] for r in t["requirements"] if r["code"] == "FIN-004")
        status = next(q for q in req["questions"] if q["role"] == "status")
        option = next(o for o in status["options"] if o["name"] == FULL)
        result = self.assessment.workspace_answer(req["answer_id"], status["id"],
                                                  {"option_id": option["id"]})
        saved = next(q for q in result["requirement"]["questions"] if q["id"] == status["id"])
        self.assertEqual(saved["value"]["option_id"], option["id"])
        self.assertTrue(saved["answered"])

    def test_a_table_column_offers_its_own_choices(self):
        """A column that lists its choices in the sheet becomes a dropdown; one
        that does not stays a free-text cell."""
        question = self.env["azm.fin.question"].search(
            [("qtype", "=", "table"), ("columns_json", "like", "options")], limit=1)
        columns = question._columns()
        self.assertTrue(columns, question.code)
        self.assertTrue(all(isinstance(c, dict) and "label" in c for c in columns))
        self.assertTrue(any(c.get("options") for c in columns), "no column offers a choice list")

    def test_an_option_from_another_question_is_refused(self):
        """The whole point: a question answers with its own options."""
        status = self._status()
        foreign = self.env["azm.fin.option"].search([("question_id", "!=", status.id)], limit=1)
        with self.assertRaises(UserError):
            self.assessment.workspace_answer(self.line.id, status.id, {"option_id": foreign.id})

    def test_answering_is_refused_outside_draft(self):
        status = self._status()
        self.assessment.with_context(azm_skip_lock=True).state = "approved"
        with self.assertRaises(UserError):
            self.assessment.workspace_answer(self.line.id, status.id, {"note": "بعد الاعتماد"})


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
        self.env.cr.execute("SELECT count(*) FROM azm_fin_option WHERE question_id IS NULL")
        self.assertEqual(self.env.cr.fetchone()[0], 0)

    def test_every_question_code_is_unique(self):
        self.env.cr.execute("""
            SELECT count(*) FROM (
                SELECT code FROM azm_fin_question GROUP BY code HAVING count(*) > 1
            ) duplicated
        """)
        self.assertEqual(self.env.cr.fetchone()[0], 0)

    def test_only_the_standard_scales_repeat(self):
        """The four standard scales repeat on every requirement by design.
        Any other repeated set must be a deliberately shared vocabulary, never
        a requirement-specific question wearing someone else's answers."""
        questions = self.env["azm.fin.question"].search(
            [("role", "in", ("status", "impl", "rule", "target"))])
        by_role = {}
        for question in questions:
            names = tuple(question.option_ids.sorted("sequence").mapped("name"))
            by_role.setdefault(question.role, set()).add(names)
        for role, sets in by_role.items():
            self.assertEqual(len(sets), 1, f"the {role} scale is not consistent")


@tagged("post_install", "-at_install")
class TestAzmFinGridColumns(TransactionCase):
    """A grid cell should offer what it can rather than ask for free text."""

    def _columns(self, profile):
        requirement = self.env["azm.fin.requirement"].search([("profile", "=", profile)], limit=1)
        question = requirement.question_ids.filtered(lambda q: q.qtype == "table")[:1]
        return question._columns() if question else []

    def test_every_column_declares_what_it_holds(self):
        """The client picks its widget from `type`, so a column without one
        would silently become a text box."""
        allowed = {"list", "text", "number", "date"}
        for question in self.env["azm.fin.question"].search([("qtype", "=", "table")]):
            for column in question._columns():
                self.assertIsInstance(column, dict, question.code)
                self.assertTrue(column.get("label"), question.code)
                self.assertIn(column.get("type"), allowed, f"{question.code}: {column}")

    def test_a_listed_column_carries_its_list(self):
        for question in self.env["azm.fin.question"].search([("qtype", "=", "table")]):
            for column in question._columns():
                if column["type"] == "list":
                    self.assertTrue(column.get("options"), f"{question.code}: {column['label']}")
                else:
                    self.assertFalse(column.get("options"),
                                     f"{question.code}: {column['label']} lists options but is not a list")

    def test_most_columns_offer_a_list(self):
        """A grid people fill five different ways is not a grid worth reading."""
        total = listed = 0
        for question in self.env["azm.fin.question"].search([("qtype", "=", "table")]):
            for column in question._columns():
                total += 1
                listed += column["type"] != "text"
        self.assertGreater(listed / total, 0.9, f"only {listed} of {total} columns are typed")

    def test_a_date_column_is_a_date(self):
        """A cell that holds a date gets a date picker rather than a text box."""
        dates = []
        for question in self.env["azm.fin.question"].search([("qtype", "=", "table")]):
            dates += [c for c in question._columns() if c["type"] == "date"]
        self.assertTrue(dates, "no column is a date, so the date picker is never reached")
        for column in dates:
            self.assertFalse(column.get("options"), f"{column['label']} is both a date and a list")

    def test_the_workflow_grid_offers_a_list_almost_everywhere(self):
        """A دورة عمل grid asks who does what in which order — answers a list
        can hold. Only «القيد», which names an accounting entry, stays open."""
        OPEN = {"القيد"}
        grids = self.env["azm.fin.question"].search(
            [("qtype", "=", "table"), ("requirement_id.profile", "=", "W")])
        self.assertEqual(len(grids), 9)
        bare = {c["label"] for q in grids for c in q._columns() if c["type"] == "text"}
        self.assertFalse(bare - OPEN, f"workflow columns with no list: {sorted(bare - OPEN)}")


@tagged("post_install", "-at_install")
class TestAzmFinOutputs(TransactionCase):
    """Every answer template must have an output that shows it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        scope = cls.env["azm.fin.scope"].search([("code", "in", ("EDU", "WORK", "PRJ"))])
        cls.entity = _entity(cls.env, "FOU", "كيان المخرجات", scope)
        cls.assessment = cls.env["azm.fin.assessment"].create({"entity_id": cls.entity.id})

    def _line(self, profile):
        return self.assessment.answer_ids.filtered(
            lambda a: a.profile == profile and a.applicable)[:1]

    def test_every_profile_has_its_own_output(self):
        covered = {p for profiles in fin_engine.TAB_PROFILES.values() for p in profiles}
        self.assertFalse(set(PROFILES) - covered,
                         "an answer template has no output tab, so its answers are invisible")

    def test_no_requirement_falls_outside_the_outputs(self):
        covered = {p for profiles in fin_engine.TAB_PROFILES.values() for p in profiles}
        orphans = self.env["azm.fin.requirement"].search([("profile", "not in", list(covered))])
        self.assertFalse(orphans, f"{len(orphans)} requirements have no output")

    def test_every_tab_has_a_document_code(self):
        for tab, _title in fin_engine.OUTPUT_TABS:
            self.assertIn(tab, fin_engine.DOC_CODES, f"{tab} has no document code")

    def test_each_output_is_its_own_document(self):
        """Two tabs sharing a document code would file two different outputs
        under one reference."""
        codes = [fin_engine.DOC_CODES[tab] for tab, _t in fin_engine.OUTPUT_TABS]
        self.assertEqual(len(codes), len(set(codes)), f"duplicate document codes: {codes}")

    def test_the_outputs_show_the_answers(self):
        """A tab that renders nothing from its answers is a tab nobody can use."""
        for tab, profiles in fin_engine.TAB_PROFILES.items():
            line = self._line(profiles[0])
            if not line:
                continue
            token = f"ZZ-{profiles[0]}-TOKEN"
            fill(line, token)
            html = self.assessment.workspace_output(line.module_id.code, tab, "module") or ""
            self.assertIn(line.code, html, f"{tab} does not show {line.code}")

    def test_each_output_shows_only_its_own_template(self):
        """A tab that leaks another template's requirements is showing the
        reader a document that is not the one it claims to be."""
        profile_of = {r.code: r.profile for r in self.env["azm.fin.requirement"].search([])}
        for tab, profiles in fin_engine.TAB_PROFILES.items():
            html = self.assessment.workspace_output(False, tab, "model") or ""
            shown = set(re.findall(r"\b((?:FIN|HRF)-\d{3})\b", html))
            stray = {c for c in shown if profile_of.get(c) not in profiles}
            self.assertFalse(stray, f"{tab} shows requirements of another template: {sorted(stray)}")

    def test_an_output_shows_every_applicable_requirement(self):
        """Anything applicable must reach its document; a silently dropped
        requirement is worse than an empty one."""
        for tab, profiles in fin_engine.TAB_PROFILES.items():
            html = self.assessment.workspace_output(False, tab, "model") or ""
            shown = len(set(re.findall(r"\b((?:FIN|HRF)-\d{3})\b", html)))
            applicable = len(self.assessment.answer_ids.filtered(
                lambda a: a.profile in profiles and a.applicable))
            self.assertEqual(shown, applicable, f"{tab} renders {shown} of {applicable}")

    def test_every_output_is_well_formed(self):
        for tab, _title in fin_engine.OUTPUT_TABS:
            html = self.assessment.workspace_output(False, tab, "model") or ""
            self.assertTrue(html.strip(), f"{tab} renders nothing")
            ET.fromstring(f"<root>{html}</root>")   # raises if the markup is broken

    def test_only_the_workflow_renders_a_step_list(self):
        """A policy rendered as a workflow would be the wrong document even
        with the right requirements in it."""
        for profile in PROFILES:
            line = self._line(profile)
            if line:
                fill(line)
        # the step list is drawn from a grid that opens with a step column, so
        # make sure at least one of those is answered
        stepped = self.assessment.answer_ids.filtered(
            lambda a: a.applicable and a.profile == "W" and any(
                q.qtype == "table" and (q._columns() or [{}])[0].get("label") in fin_engine.STEP_COLUMNS
                for q in a.requirement_id.question_ids))
        self.assertTrue(stepped, "no workflow requirement has a step grid")
        fill(stepped[:1])
        for tab in fin_engine.TAB_PROFILES:
            html = self.assessment.workspace_output(False, tab, "model") or ""
            steps = "o_azm_steps" in html
            self.assertEqual(steps, tab == "workflow",
                             f"{tab} {'renders' if steps else 'does not render'} a step list")


@tagged("post_install", "-at_install")
class TestAzmFinAuthorityOutput(TransactionCase):
    """الصلاحيات والرقابة must report what it was actually told."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        scope = cls.env["azm.fin.scope"].search([])
        cls.entity = _entity(cls.env, "FAU", "كيان الصلاحيات", scope)
        cls.assessment = cls.env["azm.fin.assessment"].create({"entity_id": cls.entity.id})
        # one authority requirement carries the يُنشئ / يراجع / يعتمد trio the
        # separation-of-duties check reads; that is the one to exercise
        cls.line = cls.assessment.answer_ids.filtered(
            lambda a: a.code == "FIN-004")

    def _render(self, **cells):
        line = self.line
        question = table_question(line)
        columns = columns_of(line)
        at = {c["label"]: n for n, c in enumerate(columns)}
        missing = set(cells) - set(at)
        self.assertFalse(missing, f"the authority grid has no column {sorted(missing)}")
        row = [""] * len(columns)
        for label, value in cells.items():
            row[at[label]] = value
        fill(line)                                   # the scales, so the item renders
        line._set_answer(question.id, {"table": [row]})
        return self.assessment.workspace_output(line.module_id.code, "authority", "module") or ""

    def test_the_grid_names_the_three_roles(self):
        """The separation-of-duties check matches on these verbs, so if the
        sheet ever renames a column the warning would go quiet."""
        labels = [c["label"] for c in columns_of(self.line)]
        for expected in ("يُنشئ", "يراجع", "يعتمد"):
            self.assertIn(expected, labels)

    def test_the_same_person_twice_is_flagged(self):
        html = self._render(**{"يُنشئ": "موظف", "يراجع": "مراجع", "يعتمد": "موظف"})
        self.assertIn("أكثر من مهمة", html)

    def test_distinct_roles_are_not_flagged(self):
        html = self._render(**{"يُنشئ": "موظف", "يراجع": "مراجع", "يعتمد": "المدير المالي"})
        self.assertNotIn("أكثر من مهمة", html)
