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
        # والسؤال سطر واحد تحته رأيان، لا سطران لا يظهر أنهما عن سؤال واحد
        self.assertEqual(len(stats["questions"]), 1, "سؤال واحد")
        entry = stats["questions"][0]
        self.assertEqual(entry["code"], self.fin[0].code or self.fin[0].key)
        self.assertEqual(len(entry["notes"]), 2, "ورأيان تحته")
        self.assertEqual({n["by"] for n in entry["notes"]},
                         {self.reviewer.name, self.other.name})
        self.assertTrue(all(n["comment"] for n in entry["notes"]))

    def test_what_needs_work_is_read_first(self):
        """الصفحة تُفتح على ما يُعمل به، لا على ما طُمئن إليه."""
        if len(self.fin) < 2:
            self.skipTest("بنك الأسئلة أصغر من أن يُرتَّب")
        mine = self._mine(self.reviewer)
        mine.save_note("financial", self.fin[0].id, "clear", "واضح")
        mine.save_note("financial", self.fin[1].id, "duplicate", "مكرر")
        mine.send_my_notes()
        order = [q["code"] for q in
                 self.C.with_user(self.manager).comment_stats()["questions"]]
        self.assertEqual(order[0], self.fin[1].code or self.fin[1].key,
                         "ما يحتاج نظرًا قبل ما لا يحتاجه")

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


@tagged("post_install", "-at_install")
class TestTheReviewerBrowsesBothBanks(TransactionCase):
    """يرى النموذجين ويكتب رأيه من حيث يقرأ."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reviewer = new_test_user(
            cls.env, "qc_browse", groups="azm_operating_model.azm_group_question_reviewer")

    def test_both_banks_are_readable(self):
        fin = self.env["azm.fin.question"].with_user(self.reviewer).search_count([])
        proc = self.env["azm.question"].with_user(self.reviewer).search_count([])
        self.assertTrue(fin, "يرى أسئلة النموذج المالي")
        self.assertTrue(proc, "ويرى أسئلة دورة المشتريات")

    def test_my_opinion_shows_beside_the_question(self):
        question = self.env["azm.fin.question"].with_user(self.reviewer).search([], limit=1)
        if not question:
            self.skipTest("بنك الأسئلة فارغ")
        self.assertFalse(question.my_verdict, "لا رأي بعد")
        self.env["azm.question.comment"].with_user(self.reviewer).save_note(
            "financial", question.id, "options", "ينقصه خيار")
        question.invalidate_recordset()
        self.assertEqual(question.my_verdict, "options")
        self.assertEqual(question.my_comment, "ينقصه خيار")
        self.assertEqual(question.my_note_state, "draft")

    def test_my_opinion_is_mine_and_not_a_colleague_s(self):
        other = new_test_user(
            self.env, "qc_browse2", groups="azm_operating_model.azm_group_question_reviewer")
        question = self.env["azm.fin.question"].sudo().search([], limit=1)
        if not question:
            self.skipTest("بنك الأسئلة فارغ")
        self.env["azm.question.comment"].with_user(self.reviewer).save_note(
            "financial", question.id, "wording", "رأيي")
        seen_by_other = question.with_user(other)
        seen_by_other.invalidate_recordset()
        self.assertFalse(seen_by_other.my_verdict, "«رأيي» يخص قارئه")

    def test_the_button_opens_the_note_for_that_question(self):
        question = self.env["azm.fin.question"].with_user(self.reviewer).search([], limit=1)
        if not question:
            self.skipTest("بنك الأسئلة فارغ")
        action = question.action_write_note()
        self.assertEqual(action["res_model"], "azm.question.comment")
        self.assertEqual(action["context"]["default_fin_question_id"], question.id)

    def test_reading_the_bank_is_not_editing_it(self):
        """الرأي في السؤال شيء، وتعديل السؤال شيء آخر."""
        from odoo.exceptions import AccessError
        question = self.env["azm.fin.question"].with_user(self.reviewer).search([], limit=1)
        if not question:
            self.skipTest("بنك الأسئلة فارغ")
        with self.assertRaises(AccessError):
            question.write({"label": "تعديل غير مأذون"})

    def test_the_count_shows_only_what_was_sent(self):
        question = self.env["azm.fin.question"].sudo().search([], limit=1)
        if not question:
            self.skipTest("بنك الأسئلة فارغ")
        self.env["azm.question.comment"].with_user(self.reviewer).save_note(
            "financial", question.id, "wording", "مسودة")
        question.invalidate_recordset()
        self.assertEqual(question.comment_count, 0, "المسودة رأي لم يُقَل بعد")
        self.env["azm.question.comment"].with_user(self.reviewer).send_my_notes()
        question.invalidate_recordset()
        self.assertEqual(question.comment_count, 1)


@tagged("post_install", "-at_install")
class TestTheReviewWorkspace(TransactionCase):
    """مساحة المراجعة: نموذجان ثم أقسام ثم أسئلة، والرأي تحت كل سؤال."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reviewer = new_test_user(
            cls.env, "qc_ws", groups="azm_operating_model.azm_group_question_reviewer")
        cls.C = cls.env["azm.question.comment"].with_user(cls.reviewer)

    def test_the_landing_shows_both_models(self):
        home = self.C.review_models()
        self.assertTrue(home["available"])
        self.assertEqual([m["key"] for m in home["models"]], ["financial", "procurement"])
        for model in home["models"]:
            self.assertTrue(model["total"], model["key"])
        self.assertTrue(home["verdicts"], "والآراء التي تُختار منها")

    def test_each_model_opens_into_its_sections(self):
        for key in ("financial", "procurement"):
            nodes = self.C.review_nodes(key)
            self.assertTrue(nodes, key)
            for node in nodes:
                self.assertTrue(node["questions"], f"{key}/{node['code']} بلا أسئلة")

    def test_a_section_opens_into_its_questions(self):
        nodes = self.C.review_nodes("financial")
        data = self.C.review_questions("financial", nodes[0]["code"])
        self.assertTrue(data["groups"], "الأسئلة مجموعة كما تُقرأ")
        self.assertEqual(
            data["count"], sum(len(g["questions"]) for g in data["groups"]))
        question = data["groups"][0]["questions"][0]
        for field in ("id", "code", "label", "note"):
            self.assertIn(field, question)

    def test_an_opinion_written_here_is_read_back_here(self):
        nodes = self.C.review_nodes("procurement")
        code = nodes[0]["code"]
        data = self.C.review_questions("procurement", code)
        question = data["groups"][0]["questions"][0]
        self.assertFalse(question["note"], "لا رأي بعد")

        self.C.save_note("procurement", question["id"], "options", "ينقصه خيار")
        again = self.C.review_questions("procurement", code)
        found = next(q for g in again["groups"] for q in g["questions"]
                     if q["id"] == question["id"])
        self.assertTrue(found["note"])
        self.assertEqual(found["note"]["verdict"], "options")
        self.assertEqual(again["reviewed"], data["reviewed"] + 1)

    def test_the_workspace_is_for_the_role_only(self):
        plain = new_test_user(self.env, "qc_plain", groups="base.group_user")
        for method in ("review_models", "review_nodes", "review_questions"):
            with self.assertRaises(UserError, msg=method):
                args = {"review_nodes": ["financial"],
                        "review_questions": ["financial", "GOV"]}.get(method, [])
                getattr(self.env["azm.question.comment"].with_user(plain), method)(*args)
