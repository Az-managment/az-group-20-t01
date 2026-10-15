"""تحميل الترجمة الإنجليزية لبنك الأسئلة من ورقة عمل.

بنك الأسئلة ليس ثنائي اللغة. تُخزَّن القيمة الإنجليزية في Odoo تحت ``en_US``،
وتحمل النص المصدر نفسه حين لا توجد ترجمة — فتبدو الحقول ممتلئة وهي فارغة. والقياس
على هذه النسخة: 1136 من 1136 سؤالًا ماليًا، و396 من 396 سؤال مشتريات، و5779 من
6121 خيارًا تحمل عربيًا في حقل الإنجليزية. أي نحو 7,311 نصًّا.

وهذه ترجمة محتوى مالي ورقابي، لا ترجمة واجهة: «الضابط التعويضي» و«المخصص
المحاسبي» و«الالتزام التعاقدي» مصطلحات يُخطئ فيها النقل الحرفي خطأً لا يُرى إلا
متأخرًا. فالمكتوب هنا آلة التحميل وحدها؛ النص يكتبه أصحابه ويُراجعونه، ويُحمَّل
من العمود ``label_en`` في ورقة العمل المصدَّرة.

ما تلتزم به هذه الآلة:
  - لا تكتب إلا حيث وُجدت إنجليزية مكتوبة؛ الفارغ يُترك ولا يُملأ بالعربية.
  - لا تمس العربية إطلاقًا.
  - تقول ما فعلت وما لم تفعل ولماذا، صفًّا صفًّا.
  - تُعاد بلا أثر: تحميل الورقة مرتين كتحميلها مرة.
"""
import csv
import io
import logging

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

SOURCE = "en_US"
ARABIC = "ar_001"
SEPARATOR = " | "


class AzmTranslations(models.AbstractModel):
    _name = "azm.translations"
    _description = "تحميل ترجمة بنك الأسئلة"

    # ------------------------------------------------------------------ أدوات
    @api.model
    def _is_arabic(self, text):
        """النص عربي — أي أنه المصدر لا ترجمته."""
        return any("؀" <= ch <= "ۿ" for ch in text or "")

    @api.model
    def _set_english(self, record, field, value):
        """يكتب الإنجليزية وحدها، ولا يلمس العربية.

        القيمة التي تساوي المصدر ليست ترجمة، والقيمة العربية في خانة الإنجليزية
        هي العطل نفسه الذي نصلحه — فكلتاهما تُرفض بدل أن تُكتب.
        """
        value = (value or "").strip()
        if not value or self._is_arabic(value):
            return False
        if record.with_context(lang=SOURCE)[field] == value:
            return False
        # العربية تُثبَّت أولًا، وإلا محتها الترجمة.
        #
        # النص العربي مخزَّن تحت en_US لأنه المصدر ولا ترجمة له. فالكتابة في
        # en_US إعادةُ كتابةٍ للمصدر، وتتبعها كل لغة لم تُفرد لها قيمة — ومنها
        # العربية. فأول ترجمة تُحمَّل كانت تمحو السؤال العربي وتضع مكانه
        # الإنجليزي في اللغتين. تُكتب العربية في خانتها صراحةً قبل أي شيء،
        # فتصير قيمةً قائمة بذاتها لا ظلًّا للمصدر.
        arabic = record.with_context(lang=ARABIC)[field]
        if arabic and self._is_arabic(arabic):
            # تُكتب اللغتان معًا في نداء واحد. الكتابة العادية في ar_001 لا تفعل
            # شيئًا هنا لأن Odoo يقرأ ارتدادًا إلى المصدر فيرى القيمة نفسها ولا
            # تغيير — فيبقى المفتاح العربي غير موجود، ثم تمحوه الكتابة في en_US.
            record.update_field_translations(field, {ARABIC: arabic, SOURCE: value})
        else:
            record.with_context(lang=SOURCE).write({field: value})
        return True

    # ------------------------------------------------------------------ التحميل
    @api.model
    def load_english(self, content, dry_run=False):
        """يحمّل الإنجليزية من ورقة عمل بشكل التصدير الأساسي.

        الأعمدة المقروءة: ``model`` و``code`` و``key`` للتعرّف، ثم ``label_en``
        و``hint_en`` و``options_en`` للنص. و``options_en`` خيارات مفصولة بـ" | "
        بترتيب ``options`` نفسه — فإن اختلف عددها تُرفض الصف كله بدل أن تُسند
        ترجمة إلى خيار غير خيارها.
        """
        if isinstance(content, bytes):
            content = content.decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(content)))
        if not rows:
            raise UserError(_("الورقة فارغة."))
        missing = {"model", "code", "key"} - set(rows[0] or {})
        if missing:
            raise UserError(_("الورقة ينقصها عمود: %s", ", ".join(sorted(missing))))

        report = {"questions": 0, "hints": 0, "options": 0,
                  "blank": 0, "unmatched": [], "mismatched": []}
        Fin = self.env["azm.fin.question"].sudo().with_context(active_test=False)
        Proc = self.env["azm.question"].sudo().with_context(active_test=False)

        for row in rows:
            key = (row.get("key") or "").strip()
            code = (row.get("code") or "").strip()
            english = (row.get("label_en") or "").strip()
            if row.get("model") == "procurement":
                question = Proc.search([("code", "=", code)], limit=1) or \
                    Proc.search([("key", "=", key)], limit=1)
                hint_field = "help_text"
            else:
                question = Fin.search([("code", "=", code)], limit=1)
                hint_field = "hint"
            if not question:
                report["unmatched"].append(code or key)
                continue
            if not english:
                report["blank"] += 1

            if self._set_english(question, "label", english):
                report["questions"] += 1
            if self._set_english(question, hint_field, row.get("hint_en")):
                report["hints"] += 1

            wanted = [x for x in (row.get("options_en") or "").split(SEPARATOR)]
            # الخيارات الحيّة وحدها. السجل يُقرأ بسياق active_test=False ليجد
            # سؤالًا أُرشف، فيرث option_ids ذلك السياق ويعدّ خيارات مؤرشفة لا
            # وجود لها في الورقة — فيختلف العدد ويُرفض كل صف بلا سبب ظاهر.
            options = (question.option_ids.filtered("active")
                       if "option_ids" in question._fields
                       else self.env["azm.fin.option"])
            if any(w.strip() for w in wanted):
                if len(wanted) != len(options):
                    # ترجمة تُسند إلى خيار غير خيارها أسوأ من لا ترجمة
                    report["mismatched"].append(code or key)
                else:
                    for option, text in zip(options, wanted):
                        if self._set_english(option, "name", text):
                            report["options"] += 1

        if dry_run:
            self.env.cr.rollback()
        _logger.info("ترجمة: أسئلة=%s مساعدات=%s خيارات=%s فارغ=%s غير مطابق=%s مجهول=%s",
                     report["questions"], report["hints"], report["options"],
                     report["blank"], len(report["mismatched"]), len(report["unmatched"]))
        return report

    # ------------------------------------------------------------------ القياس
    @api.model
    def english_coverage(self):
        """كم نصًّا ما زال عربيًا في خانة الإنجليزية — القياس لا الانطباع."""
        counts = {}
        for label, model, fields_ in (
                ("أسئلة مالية", "azm.fin.question", ("label", "hint")),
                ("أسئلة مشتريات", "azm.question", ("label", "help_text")),
                ("خيارات مالية", "azm.fin.option", ("name",)),
        ):
            records = self.env[model].sudo().with_context(
                active_test=False, lang=SOURCE).search([])
            pending = total = 0
            for record in records:
                for field in fields_:
                    value = record[field]
                    if not value:
                        continue
                    total += 1
                    if self._is_arabic(value):
                        pending += 1
            counts[label] = {"pending": pending, "total": total}
        return counts
