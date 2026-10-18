"""بنك الأسئلة في ملف واحد، ومعه ما قيل عن كل سؤال.

الصفحة تعرض ما وصل؛ والملف يُعطى لمن يريد أن يقرأ البنك كله خارجها — ورقة فيها
كل سؤال في النموذجين بكوده ونصّه وخياراته، وأمامه عدد ما قيل فيه ونصّه، وورقة
ثانية فيها كل ملاحظة على حدة. والأسئلة كلها لا المعلّق عليها وحدها: سؤال لم يقل
فيه أحد شيئًا خبرٌ عن المراجعة كالسؤال الذي قيل فيه.
"""
import io

from odoo import _, api, models
from odoo.exceptions import UserError

from .azm_question_comment import VERDICTS

# عرض الأعمدة بالحروف: الكود ضيق، ونصّ السؤال والملاحظة يحتاجان مدى يُقرأ فيه
BANK_COLUMNS = [
    ("النموذج", 22), ("الموضع", 14), ("الكود", 26), ("المفتاح", 10),
    ("السؤال", 60), ("المطلوب في الإجابة", 36), ("شكل الإجابة", 14),
    ("الخيارات", 48), ("عدد الملاحظات", 12), ("الآراء", 26), ("الملاحظات", 60),
]
NOTE_COLUMNS = [
    ("النموذج", 22), ("الموضع", 14), ("الكود", 26), ("السؤال", 60),
    ("الرأي", 26), ("يحتاج نظرًا", 11), ("الملاحظة", 60),
    ("المراجع", 22), ("تاريخ الإرسال", 20),
]


class AzmQuestionBankExport(models.AbstractModel):
    """تصدير بنك الأسئلة وملاحظات المراجعين إلى ملف إكسل."""
    _name = "azm.question.bank.export"
    _description = "تصدير بنك الأسئلة"

    @api.model
    def _bank_rows(self):
        """كل سؤال في النموذجين، بالترتيب الذي يُقرأ به."""
        rows = []
        fin = self.env["azm.fin.question"].sudo().search(
            [], order="module_sequence, sequence, id")
        for q in fin:
            rows.append({
                "model": "financial", "model_name": "النموذج المالي الموحد",
                "node": f"FIN.{q.module_id.code}" if q.module_id else "FIN",
                "code": q.code or q.key or "", "key": q.key or "",
                "label": q.label or "", "hint": q.hint or "",
                "qtype": q.qtype or "",
                "options": " | ".join(o.name for o in q.option_ids if o.name),
            })
        proc = self.env["azm.question"].sudo().search(
            [], order="stage_sequence, sequence, id")
        for q in proc:
            rows.append({
                "model": "procurement", "model_name": "دورة المشتريات",
                "node": f"PUR-{q.stage_id.code}" if q.stage_id else "PUR",
                "code": q.code or q.key or "", "key": q.key or "",
                "label": q.label or "", "hint": q.help_text or "",
                "qtype": q.qtype or "",
                "options": " | ".join(o.name for o in q.option_ids if o.name),
            })
        return rows

    @api.model
    def _sent_notes(self):
        """ما أُرسل إلى مدير النموذج، مرتبًا حسب موضعه."""
        return self.env["azm.question.comment"].sudo().search(
            [("state", "=", "sent")], order="model_key, node, question_code, id")

    @api.model
    def question_bank_xlsx(self):
        """الملف بتمامه. يُبنى في الذاكرة ويعود بايتاتٍ، ليُختبر بلا متصفّح."""
        if not self.env.user.has_group("azm_operating_model.azm_group_manager"):
            raise UserError(_("تصدير بنك الأسئلة لمدير النموذج."))
        import xlsxwriter

        verdicts = dict(VERDICTS)
        notes_by_question = {}
        for note in self._sent_notes():
            notes_by_question.setdefault(
                (note.model_key, note.question_code), []).append(note)

        stream = io.BytesIO()
        book = xlsxwriter.Workbook(stream, {"in_memory": True,
                                            "default_date_format": "yyyy-mm-dd"})
        head = book.add_format({"bold": True, "bg_color": "#142b3d",
                                "font_color": "#ffffff", "valign": "vcenter",
                                "text_wrap": True, "border": 1})
        cell = book.add_format({"valign": "top", "text_wrap": True, "border": 1})
        code = book.add_format({"valign": "top", "border": 1,
                                "font_name": "Consolas"})
        flagged = book.add_format({"valign": "top", "text_wrap": True, "border": 1,
                                   "bg_color": "#fdf0e6"})

        # ------------------------------------------------------ ورقة: بنك الأسئلة
        bank = book.add_worksheet("بنك الأسئلة")
        bank.right_to_left()
        bank.freeze_panes(1, 0)
        for i, (title, width) in enumerate(BANK_COLUMNS):
            bank.write(0, i, title, head)
            bank.set_column(i, i, width)
        questions = self._bank_rows()
        bank.autofilter(0, 0, max(len(questions), 1), len(BANK_COLUMNS) - 1)
        for r, row in enumerate(questions, start=1):
            mine = notes_by_question.get((row["model"], row["code"]), [])
            said = [verdicts.get(n.verdict, n.verdict) for n in mine]
            texts = [f"{n.user_id.name}: {n.comment or ''}" for n in mine]
            style = flagged if any(n.needs_work for n in mine) else cell
            bank.write(r, 0, row["model_name"], style)
            bank.write(r, 1, row["node"], style)
            bank.write(r, 2, row["code"], code)
            bank.write(r, 3, row["key"], style)
            bank.write(r, 4, row["label"], style)
            bank.write(r, 5, row["hint"], style)
            bank.write(r, 6, row["qtype"], style)
            bank.write(r, 7, row["options"], style)
            bank.write_number(r, 8, len(mine), style)
            bank.write(r, 9, " | ".join(said), style)
            bank.write(r, 10, "\n".join(texts), style)

        # -------------------------------------------------- ورقة: ملاحظة ملاحظة
        sheet = book.add_worksheet("ملاحظات المراجعين")
        sheet.right_to_left()
        sheet.freeze_panes(1, 0)
        for i, (title, width) in enumerate(NOTE_COLUMNS):
            sheet.write(0, i, title, head)
            sheet.set_column(i, i, width)
        notes = self._sent_notes()
        sheet.autofilter(0, 0, max(len(notes), 1), len(NOTE_COLUMNS) - 1)
        names = dict(self.env["azm.question.comment"]._fields["model_key"].selection)
        for r, note in enumerate(notes, start=1):
            style = flagged if note.needs_work else cell
            sheet.write(r, 0, names.get(note.model_key, note.model_key or ""), style)
            sheet.write(r, 1, note.node or "", style)
            sheet.write(r, 2, note.question_code or "", code)
            sheet.write(r, 3, note.question_label or "", style)
            sheet.write(r, 4, verdicts.get(note.verdict, note.verdict), style)
            sheet.write(r, 5, "نعم" if note.needs_work else "لا", style)
            sheet.write(r, 6, note.comment or "", style)
            sheet.write(r, 7, note.user_id.name or "", style)
            sheet.write(r, 8, str(note.sent_on or ""), style)

        book.close()
        return stream.getvalue()
