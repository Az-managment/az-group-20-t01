from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from .fin_common import FULL


@tagged("post_install", "-at_install")
class TestAzmFinQuestions(TransactionCase):
    """The catalogue is machine-generated and validated by
    ``tools/build_fin_catalogue.py`` before it is written, so what the models
    still have to guarantee is that an answer cannot stray from its question.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.module = cls.env["azm.fin.module"].create({"code": "ZZ.TST", "name": "اختبار"})
        cls.topic = cls.env["azm.fin.topic"].create({
            "code": "ZZ.TST.01", "name": "موضوع اختبار", "module_id": cls.module.id})
        cls.requirement = cls.env["azm.fin.requirement"].create({
            "code": "ZZ-001", "module_id": cls.module.id, "topic_id": cls.topic.id,
            "title": "متطلب اختبار", "question": "سؤال المتطلب", "profile": "L", "scope_code": "ALL",
        })

    def _question(self, key, sequence, **extra):
        return self.env["azm.fin.question"].create({
            "code": f"{self.requirement.code}-{key}", "requirement_id": self.requirement.id,
            "key": key, "sequence": sequence, "label": f"سؤال {key}",
            "role": extra.pop("role", "main"), **extra,
        })

    def test_a_question_code_is_unique(self):
        """The loader matches on the code, so a duplicate would make one
        question silently overwrite another on every reload."""
        self._question("Q001", 1)
        self.env.flush_all()
        with self.assertRaises(Exception):
            self._question("Q001", 2)
            self.env.flush_all()

    def test_options_belong_to_their_own_question(self):
        first = self._question("Q001", 1)
        second = self._question("Q002", 2, role="follow")
        self.env["azm.fin.option"].create([
            {"question_id": first.id, "name": "نعم", "sequence": 1},
            {"question_id": first.id, "name": "لا", "sequence": 2},
            {"question_id": second.id, "name": "أخرى", "sequence": 1},
        ])
        self.assertEqual(first.option_ids.mapped("name"), ["نعم", "لا"])
        self.assertEqual(second.option_ids.mapped("name"), ["أخرى"])

    def test_a_condition_is_read_back_as_it_was_written(self):
        question = self._question("Q002", 2, role="follow",
                                  condition_json='{"q": "Q001", "in": ["نعم"]}')
        self.assertEqual(question._condition(), {"q": "Q001", "in": ["نعم"]})
        self.assertIn("Q001", question.condition_text)

    def test_a_question_without_a_condition_is_always_shown(self):
        question = self._question("Q001", 1)
        self.assertIsNone(question._condition())
        self.assertFalse(question.condition_text)

    def test_the_schema_carries_everything_the_client_renders(self):
        question = self._question("Q001", 1, qtype="select")
        self.env["azm.fin.option"].create({"question_id": question.id, "name": "نعم", "sequence": 1})
        schema = question._schema()
        for key in ("id", "code", "key", "role", "label", "hint", "qtype", "unit", "columns",
                    "condition", "condition_text", "note_label", "note_options", "has_priority",
                    "options"):
            self.assertIn(key, schema)
        self.assertEqual([o["name"] for o in schema["options"]], ["نعم"])


@tagged("post_install", "-at_install")
class TestAzmFinAnswerGuards(TransactionCase):
    """An answer points at one question of one requirement, and only while the
    assessment is still a draft."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        scope = cls.env["azm.fin.scope"].search([("code", "=", "EDU")])
        cls.entity = cls.env["azm.entity"].create({
            "code": "FQG", "name": "كيان الضوابط", "fin_scope_ids": [(6, 0, scope.ids)]})
        cls.assessment = cls.env["azm.fin.assessment"].create({"entity_id": cls.entity.id})
        cls.line = cls.assessment.answer_ids.filtered(lambda a: a.code == "FIN-004")

    def _status(self):
        return self.line.requirement_id.question_ids.filtered(lambda q: q.role == "status")[:1]

    def test_an_unknown_answer_is_a_fallback(self):
        """«لا أعرف» is an answer, but not a known one — which is what keeps
        the questions depending on it hidden."""
        status = self._status()
        unknown = status.option_ids.filtered(lambda o: o.kind == "unknown")[:1]
        known = status.option_ids.filtered(lambda o: o.name == FULL)[:1]

        qa = self.line._set_answer(status.id, {"option_id": known.id})
        self.assertTrue(qa.is_answered)
        self.assertFalse(qa._is_fallback())
        self.assertEqual(qa._names(), {FULL})

        qa = self.line._set_answer(status.id, {"option_id": unknown.id})
        self.assertTrue(qa.is_answered, "«لا أعرف» is still an answer")
        self.assertTrue(qa._is_fallback())

    def test_a_question_is_answered_once_per_requirement(self):
        status = self._status()
        self.line._set_answer(status.id, {"option_id": self._status().option_ids[:1].id})
        with self.assertRaises(Exception):
            self.env["azm.fin.qanswer"].create({"line_id": self.line.id, "question_id": status.id})
            self.env.flush_all()

    def test_a_question_of_another_requirement_is_refused(self):
        foreign = self.env["azm.fin.question"].search(
            [("requirement_id", "!=", self.line.requirement_id.id)], limit=1)
        with self.assertRaises(UserError):
            self.line._set_answer(foreign.id, {"note": "ليس من هذا المتطلب"})

    def test_answers_are_locked_outside_draft(self):
        status = self._status()
        self.line._set_answer(status.id, {"note": "مسموح في المسودة"})
        self.assessment.with_context(azm_skip_lock=True).state = "approved"
        with self.assertRaises(UserError):
            self.line._set_answer(status.id, {"note": "ممنوع بعد الاعتماد"})
