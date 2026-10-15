"""تحميل الإنجليزية لا يجوز أن يكلّف العربية."""
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

ARABIC, ENGLISH = "ar_001", "en_US"


@tagged("post_install", "-at_install")
class TestLoadingEnglishKeepsArabic(TransactionCase):
    """بنك الأسئلة عربي، ونصه مخزَّن تحت en_US لأنه المصدر ولا ترجمة له.

    وهذا فخّ: الكتابة في en_US إعادةُ كتابةٍ للمصدر، وتتبعها كل لغة لم تُفرد لها
    قيمة. فأول تحميل للترجمة كان يمحو السؤال العربي ويضع الإنجليزي في اللغتين —
    سبعة آلاف نص عربي تُستبدل، ولا شيء يشكو.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.T = cls.env["azm.translations"].sudo()
        cls.question = cls.env["azm.fin.question"].sudo().search(
            [("option_ids", "!=", False)], limit=1)

    def _sheet(self, **cells):
        row = {"model": "financial", "code": self.question.code,
               "key": self.question.key, "label_en": "", "hint_en": "",
               "options": "", "options_en": ""}
        row.update(cells)
        head = ",".join(row)
        body = ",".join(f'"{v}"' for v in row.values())
        return f"{head}\n{body}\n"

    def _arabic(self, field="label"):
        self.question.invalidate_recordset()
        return self.question.with_context(lang=ARABIC)[field]

    def _english(self, field="label"):
        self.question.invalidate_recordset()
        return self.question.with_context(lang=ENGLISH)[field]

    def test_the_arabic_survives_being_translated(self):
        if not self.question:
            self.skipTest("لا توجد أسئلة")
        before = self._arabic()
        self.T.load_english(self._sheet(label_en="Operational authority"))
        self.assertEqual(self._arabic(), before,
                         "الترجمة أضافت لغة، ولم تستبدل لغة")
        self.assertEqual(self._english(), "Operational authority")

    def test_an_option_keeps_its_arabic_too(self):
        if not self.question:
            self.skipTest("لا توجد أسئلة")
        option = self.question.option_ids[0]
        before = option.with_context(lang=ARABIC).name
        names = " | ".join(f"Option {i + 1}" for i in range(len(self.question.option_ids)))
        self.T.load_english(self._sheet(options_en=names))
        option.invalidate_recordset()
        self.assertEqual(option.with_context(lang=ARABIC).name, before)
        self.assertEqual(option.with_context(lang=ENGLISH).name, "Option 1")

    def test_arabic_in_the_english_column_is_refused(self):
        """العربية في خانة الإنجليزية هي العطل نفسه، لا إصلاحه."""
        if not self.question:
            self.skipTest("لا توجد أسئلة")
        before = self._english()
        report = self.T.load_english(self._sheet(label_en="صلاحيات العمليات"))
        self.assertEqual(self._english(), before)
        self.assertEqual(report["questions"], 0)

    def test_a_blank_cell_is_left_alone_and_counted(self):
        if not self.question:
            self.skipTest("لا توجد أسئلة")
        before = self._english()
        report = self.T.load_english(self._sheet(label_en=""))
        self.assertEqual(self._english(), before, "الفارغ لا يُملأ بالعربية")
        self.assertEqual(report["blank"], 1)

    def test_options_of_a_different_length_are_refused_whole(self):
        """ترجمة تُسند إلى خيار غير خيارها أسوأ من لا ترجمة."""
        if not self.question or len(self.question.option_ids) < 2:
            self.skipTest("يحتاج سؤالًا متعدد الخيارات")
        option = self.question.option_ids[0]
        before = option.with_context(lang=ENGLISH).name
        report = self.T.load_english(self._sheet(options_en="One"))
        option.invalidate_recordset()
        self.assertTrue(report["mismatched"])
        self.assertEqual(option.with_context(lang=ENGLISH).name, before)

    def test_a_code_that_matches_nothing_is_reported_not_guessed(self):
        report = self.T.load_english(
            'model,code,key,label_en\nfinancial,NO-SUCH-CODE,Q999,"Nothing"\n')
        self.assertEqual(report["unmatched"], ["NO-SUCH-CODE"])

    def test_loading_the_same_sheet_twice_writes_nothing_the_second_time(self):
        if not self.question:
            self.skipTest("لا توجد أسئلة")
        sheet = self._sheet(label_en="Operational authority")
        self.T.load_english(sheet)
        again = self.T.load_english(sheet)
        self.assertEqual(again["questions"], 0, "ما كُتب لا يُعاد كتابته")

    def test_a_sheet_without_the_identifying_columns_is_refused(self):
        with self.assertRaises(UserError):
            self.T.load_english('label_en\n"Nothing to attach this to"\n')

    def test_coverage_counts_what_is_still_arabic(self):
        counts = self.T.english_coverage()
        self.assertIn("أسئلة مالية", counts)
        for label, numbers in counts.items():
            self.assertLessEqual(numbers["pending"], numbers["total"], label)
