from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAzmFinQuestions(TransactionCase):
    """The question catalogue is machine-generated from the spreadsheet, so the
    invariants that keep a question answering with its OWN options are enforced
    by the model rather than trusted."""

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
            "requirement_id": self.requirement.id, "key": key, "sequence": sequence,
            "label": f"سؤال {key}", "role": extra.pop("role", "main"), **extra,
        })

    def test_code_is_derived_from_the_requirement(self):
        question = self._question("Q001", 1)
        self.assertEqual(question.code, "ZZ-001/Q001")

    def test_key_is_unique_inside_the_requirement(self):
        self._question("Q001", 1)
        with self.assertRaises(Exception):
            self._question("Q001", 2)

    def test_options_belong_to_their_own_question(self):
        first = self._question("Q001", 1)
        second = self._question("Q002", 2, role="followup")
        self.env["azm.fin.option"].create([
            {"question_id": first.id, "name": "نعم", "sequence": 1},
            {"question_id": first.id, "name": "لا", "sequence": 2},
            {"question_id": second.id, "name": "أخرى", "sequence": 1},
        ])
        self.assertEqual(first.option_ids.mapped("name"), ["نعم", "لا"])
        self.assertEqual(second.option_ids.mapped("name"), ["أخرى"])
        self.assertEqual((first.option_count, second.option_count), (2, 1))

    def test_a_condition_may_only_point_backwards(self):
        """A forward reference would never fire: the engine only sees the answers
        of questions that sort before the one being evaluated."""
        self._question("Q001", 1)
        with self.assertRaises(ValidationError):
            self._question("Q002", 2, role="followup",
                           condition='{"field": "Q003", "in": ["نعم"]}')

        backwards = self._question("Q003", 3, role="followup",
                                   condition='{"field": "Q001", "in": ["نعم"]}')
        self.assertTrue(backwards.id)

    def test_a_condition_must_be_valid_json(self):
        with self.assertRaises(ValidationError):
            self._question("Q001", 1, condition="not json at all")

    def test_unknown_answers_are_not_counted_as_known(self):
        """'لا أعرف' leaves the question unknown, which is what keeps the
        follow-ups depending on it hidden."""
        question = self._question("Q001", 1)
        yes, dunno = self.env["azm.fin.option"].create([
            {"question_id": question.id, "name": "نعم", "sequence": 1},
            {"question_id": question.id, "name": "لا أعرف", "sequence": 2, "kind": "unknown"},
        ])
        assessment = self.env["azm.fin.assessment"].search([], limit=1)
        if not assessment:
            self.skipTest("no financial assessment in this database")
        answer = self.env["azm.fin.qanswer"].create({
            "assessment_id": assessment.id, "question_id": question.id})

        answer.option_id = yes
        self.assertTrue(answer.has_value)
        self.assertTrue(answer.is_known)
        self.assertEqual(answer._engine_value(), "نعم")

        answer.option_id = dunno
        self.assertTrue(answer.has_value)
        self.assertFalse(answer.is_known)

    def test_answers_are_locked_outside_draft(self):
        question = self._question("Q001", 1)
        assessment = self.env["azm.fin.assessment"].search([], limit=1)
        if not assessment:
            self.skipTest("no financial assessment in this database")
        answer = self.env["azm.fin.qanswer"].create({
            "assessment_id": assessment.id, "question_id": question.id})
        answer.text = "مسموح في المسودة"

        assessment.with_context(azm_skip_lock=True).state = "approved"
        with self.assertRaises(UserError):
            answer.text = "ممنوع بعد الاعتماد"
