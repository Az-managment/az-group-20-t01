"""بنك الأسئلة ملفَّ إكسل: ما فيه، ولمن هو.

الملف يُبنى في النموذج لا في المسار، فيُقرأ هنا بلا متصفّح: يُفتح كما هو — ملف
مضغوط فيه ورقتان — ويُبحث في نصوصه عن سؤال بعينه وعن ملاحظة بعينها.
"""
import io
import zipfile

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestTheQuestionBankFile(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = new_test_user(
            cls.env, "qx_mgr", groups="azm_operating_model.azm_group_manager")
        cls.reviewer = new_test_user(
            cls.env, "qx_rev", groups="azm_operating_model.azm_group_question_reviewer")
        cls.X = cls.env["azm.question.bank.export"]

    def _text(self, content):
        """نصوص الملف كلها، كما كتبها إكسل داخل المضغوط."""
        with zipfile.ZipFile(io.BytesIO(content)) as book:
            names = [n for n in book.namelist()
                     if n.endswith(".xml") and ("sharedStrings" in n or "workbook" in n)]
            return "".join(book.read(n).decode("utf-8") for n in names)

    def test_it_is_a_workbook_of_two_sheets(self):
        content = self.X.with_user(self.manager).question_bank_xlsx()
        self.assertTrue(content.startswith(b"PK"), "ملف إكسل لا نصٌّ يُسمّى كذلك")
        text = self._text(content)
        self.assertIn("بنك الأسئلة", text)
        self.assertIn("ملاحظات المراجعين", text)

    def test_the_whole_bank_is_in_it_commented_or_not(self):
        """سؤال لم يقل فيه أحد شيئًا خبرٌ عن المراجعة كالذي قيل فيه."""
        spoken_for = self.env["azm.question.comment"].sudo().search(
            [("fin_question_id", "!=", False)]).fin_question_id.ids
        question = self.env["azm.fin.question"].sudo().search(
            [("id", "not in", spoken_for)], limit=1)
        if not question:
            self.skipTest("لا سؤال بلا ملاحظة")
        text = self._text(self.X.with_user(self.manager).question_bank_xlsx())
        self.assertIn(question.code or question.key, text)

    def test_what_was_sent_is_in_it_and_what_was_not_is_not(self):
        question = self.env["azm.fin.question"].sudo().search([], limit=2)
        if len(question) < 2:
            self.skipTest("يحتاج سؤالين")
        notes = self.env["azm.question.comment"].with_user(self.reviewer)
        notes.save_note("financial", question[0].id, "duplicate", "مُرسَلة فتُقرأ")
        notes.send_my_notes()
        notes.save_note("financial", question[1].id, "wording", "مسودة فلا تُقرأ")
        text = self._text(self.X.with_user(self.manager).question_bank_xlsx())
        self.assertIn("مُرسَلة فتُقرأ", text)
        self.assertNotIn("مسودة فلا تُقرأ", text,
                         "المسودة رأي لم يُقَل بعد، فلا تُصدَّر")

    def test_the_file_is_the_manager_s(self):
        with self.assertRaises(UserError):
            self.X.with_user(self.reviewer).question_bank_xlsx()

    def test_a_question_opens_with_its_options_and_its_notes(self):
        """من قرأ «ينقصه خيار» لا يسعه الحكم حتى يرى الخيارات التي عندها قيل."""
        C = self.env["azm.question.comment"]
        question = self.env["azm.fin.question"].sudo().search(
            [("option_ids", "!=", False)], limit=1)
        if not question:
            self.skipTest("لا سؤال بخيارات")
        C.with_user(self.reviewer).save_note(
            "financial", question.id, "options", "ينقصه خيار «لا ينطبق»")
        C.with_user(self.reviewer).send_my_notes()

        detail = C.with_user(self.manager).question_detail(
            "financial", question.code or question.key)
        self.assertEqual(detail["label"], question.label)
        self.assertEqual([o["name"] for o in detail["options"]],
                         question.option_ids.mapped("name"), "الخيارات بترتيبها")
        self.assertTrue(detail["place"], "وموضعه من الشجرة")
        self.assertIn("ينقصه خيار «لا ينطبق»",
                      [n["comment"] for n in detail["notes"]])

    def test_opening_a_question_is_the_manager_s(self):
        question = self.env["azm.fin.question"].sudo().search([], limit=1)
        with self.assertRaises(UserError):
            self.env["azm.question.comment"].with_user(
                self.reviewer).question_detail("financial", question.code)

    def test_a_draft_is_not_shown_under_the_question_either(self):
        """ما لم يُرسَل لا يُقرأ، في الصفحة وفي الملف وهنا."""
        C = self.env["azm.question.comment"]
        question = self.env["azm.fin.question"].sudo().search([], limit=1)
        C.with_user(self.reviewer).save_note(
            "financial", question.id, "wording", "مسودة لا تُقرأ هنا")
        detail = C.with_user(self.manager).question_detail(
            "financial", question.code or question.key)
        self.assertNotIn("مسودة لا تُقرأ هنا",
                         [n["comment"] for n in detail["notes"]])

    def test_the_route_exists_and_can_hand_the_file_over(self):
        """ما يسقط عند الطلب لا عند التحميل.

        أول نسخة من هذا المسار نادت content_disposition من odoo.http وليست فيه.
        الاستيراد مرّ، والاختبارات مرّت — لأنها كانت تختبر بناء الملف لا تسليمه —
        ومات عند أول ضغطة على الزر بخطأ 500. فيُستدعى هنا ما يستدعيه المسار.
        """
        from odoo.addons.azm_operating_model.controllers.question_export import (
            FILENAME, delivery_headers,
        )
        headers = dict(delivery_headers(b"x" * 11))
        self.assertEqual(headers["Content-Length"], 11)
        self.assertIn("spreadsheetml", headers["Content-Type"])
        self.assertIn(FILENAME, headers["Content-Disposition"])
        self.assertIn("attachment", headers["Content-Disposition"])

        routes = [r.rule for r in self.env["ir.http"].routing_map().iter_rules()]
        self.assertIn("/azm/question_bank.xlsx", routes, "والزر ينادي مسارًا قائمًا")
