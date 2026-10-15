"""رأي في السؤال نفسه، لا إجابة عنه."""
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestReviewingTheQuestionsThemselves(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.C = cls.env["azm.question.comment"]
        cls.reviewer = new_test_user(
            cls.env, "qc_rev", groups="azm_operating_model.azm_group_question_reviewer")
        cls.other = new_test_user(
            cls.env, "qc_rev2", groups="azm_operating_model.azm_group_question_reviewer")
        cls.manager = new_test_user(
            cls.env, "qc_mgr", groups="azm_operating_model.azm_group_manager")
        cls.fin = cls.env["azm.fin.question"].sudo().search([], limit=2)
        cls.proc = cls.env["azm.question"].sudo().search([], limit=1)

    def _mine(self, user=None):
        return self.C.with_user(user or self.reviewer)

    def test_a_reviewer_reads_the_bank_but_not_anybody_s_answers(self):
        """رأيه في صياغة سؤال لا يحتاج أن يرى ما أجاب به كيان."""
        self.assertTrue(self.env["azm.fin.question"].with_user(self.reviewer).search_count([]))
        self.assertTrue(self.env["azm.question"].with_user(self.reviewer).search_count([]))
        with self.assertRaises(AccessError):
            self.env["azm.fin.assessment"].with_user(self.reviewer).search_count([])

    def test_an_opinion_can_be_written_on_either_model(self):
        if not (self.fin and self.proc):
            self.skipTest("بنك الأسئلة فارغ")
        self._mine().save_note("financial", self.fin[0].id, "wording", "صياغة مركّبة")
        self._mine().save_note("procurement", self.proc.id, "duplicate", "يتداخل مع غيره")
        notes = self.C.sudo().search([("user_id", "=", self.reviewer.id)])
        self.assertEqual(len(notes), 2)
        self.assertEqual(set(notes.mapped("model_key")), {"financial", "procurement"})
        self.assertTrue(all(notes.mapped("question_code")), "كل ملاحظة تحمل كود سؤالها")

    def test_an_empty_comment_is_not_an_opinion(self):
        if not self.fin:
            self.skipTest("بنك الأسئلة فارغ")
        self._mine().save_note("financial", self.fin[0].id, "wording", "رأي")
        self._mine().save_note("financial", self.fin[0].id, "wording", "   ")
        self.assertFalse(self.C.sudo().search_count(
            [("user_id", "=", self.reviewer.id), ("fin_question_id", "=", self.fin[0].id)]))

    def test_one_opinion_per_reviewer_per_question(self):
        """وتعديله أولى من تكديس آراء متناقضة لصاحب واحد."""
        if not self.fin:
            self.skipTest("بنك الأسئلة فارغ")
        self._mine().save_note("financial", self.fin[0].id, "wording", "أولى")
        self._mine().save_note("financial", self.fin[0].id, "options", "ثانية")
        notes = self.C.sudo().search(
            [("user_id", "=", self.reviewer.id), ("fin_question_id", "=", self.fin[0].id)])
        self.assertEqual(len(notes), 1)
        self.assertEqual((notes.verdict, notes.comment), ("options", "ثانية"))

    def test_a_reviewer_does_not_see_another_reviewer_s_drafts(self):
        """رأي لم يُرسَل بعد ليس شيئًا يراه الزملاء."""
        if not self.fin:
            self.skipTest("بنك الأسئلة فارغ")
        self._mine().save_note("financial", self.fin[0].id, "wording", "رأيي أنا")
        self.assertFalse(self._mine(self.other).search_count([]))

    def test_what_was_sent_is_not_edited_afterwards(self):
        if not self.fin:
            self.skipTest("بنك الأسئلة فارغ")
        self._mine().save_note("financial", self.fin[0].id, "wording", "رأي")
        self._mine().send_my_notes()
        note = self.C.sudo().search([("user_id", "=", self.reviewer.id)], limit=1)
        self.assertEqual(note.state, "sent")
        self.assertTrue(note.sent_on)
        with self.assertRaises(UserError):
            note.with_user(self.reviewer).write({"comment": "تعديل بعد الإرسال"})

    def test_the_manager_sees_what_was_sent_and_not_what_was_not(self):
        if len(self.fin) < 2:
            self.skipTest("يحتاج سؤالين")
        self._mine().save_note("financial", self.fin[0].id, "wording", "مُرسَلة")
        self._mine().send_my_notes()
        self._mine().save_note("financial", self.fin[1].id, "options", "ما زالت مسودة")
        seen = self.C.with_user(self.manager).search([])
        self.assertEqual(set(seen.mapped("state")), {"sent"})

    def test_the_statistics_count_questions_not_notes(self):
        """سؤال علّق عليه ثلاثة مراجعين سؤال واحد عليه ملاحظة."""
        if not self.fin:
            self.skipTest("بنك الأسئلة فارغ")
        for user in (self.reviewer, self.other):
            self._mine(user).save_note("financial", self.fin[0].id, "wording", f"رأي {user.login}")
            self._mine(user).send_my_notes()
        stats = self.C.with_user(self.manager).comment_stats()
        self.assertEqual(stats["notes"], 2)
        self.assertEqual(stats["questions_commented"], 1, "سؤال واحد")
        self.assertEqual(stats["reviewers"], 2)
        self.assertTrue(stats["rows"], "والمدير يرى الكود مع الملاحظة")
        self.assertIn("code", stats["rows"][0])
        self.assertIn("comment", stats["rows"][0])

    def test_statistics_are_for_the_manager(self):
        with self.assertRaises(UserError):
            self.C.with_user(self.reviewer).comment_stats()

    def test_a_note_belongs_to_one_question(self):
        from psycopg2 import IntegrityError
        from odoo.tools import mute_logger
        if not (self.fin and self.proc):
            self.skipTest("بنك الأسئلة فارغ")
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            with self.env.cr.savepoint():
                self.C.sudo().create({
                    "fin_question_id": self.fin[0].id,
                    "proc_question_id": self.proc.id,
                    "verdict": "wording", "comment": "الاثنان معًا",
                })
