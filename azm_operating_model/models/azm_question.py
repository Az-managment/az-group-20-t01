import json

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AzmQuestion(models.Model):
    _name = "azm.question"
    _inherit = ["azm.reviewable.question"]
    _description = "AZM Question"
    _azm_comment_field = "proc_question_id"
    _order = "stage_sequence, group, sequence, id"
    _rec_names_search = ("label", "code")

    stage_id = fields.Many2one("azm.stage", "المرحلة", required=True, ondelete="cascade", index=True)
    stage_sequence = fields.Integer(related="stage_id.sequence", store=True, string="ترتيب المرحلة")
    key = fields.Char(required=True, help="المعرّف الداخلي المستخدم في الشروط والقواعد.")
    code = fields.Char("الكود", compute="_compute_code", store=True, index=True)
    label = fields.Char("السؤال", required=True, translate=True)
    clause = fields.Char("صيغة الجملة", required=True, translate=True,
                         help="بداية الجملة التي تُكتب في الوثيقة قبل الإجابة.")
    qtype = fields.Selection([("select", "اختيار واحد"), ("multi", "اختيار متعدد"), ("number", "رقم")],
                             default="select", required=True, string="النوع")
    group = fields.Selection([("0", "واقع المرحلة"), ("1", "المسؤوليات والمسار"), ("2", "النظام والإثبات")],
                             default="0", required=True, string="القسم")
    sequence = fields.Integer(default=10)
    condition = fields.Text("شرط الظهور (JSON)",
                            help='مثال: {"field": "boundary", "in": ["خارج النظام"]}')
    is_common = fields.Boolean("سؤال مشترك", help="من الأسئلة المشتركة بين كل المراحل التشغيلية.")
    is_role = fields.Boolean("سؤال دور")
    raci = fields.Selection([("R", "ينفذ"), ("V", "يراجع"), ("A", "يعتمد"), ("C", "يُستشار"), ("I", "يُبلّغ")])
    option_ids = fields.One2many("azm.option", "question_id", string="الاختيارات")
    help_text = fields.Text("شرح للمجيب", translate=True)
    active = fields.Boolean(default=True)

    _stage_key_uniq = models.Constraint("UNIQUE(stage_id, key)", "المفتاح مكرر في نفس المرحلة.")

    @api.depends("stage_id.code", "key")
    def _compute_code(self):
        for q in self:
            q.code = f"PUR-{q.stage_id.code}/{q.key}" if q.stage_id.code and q.key else False

    @api.depends("label", "code")
    def _compute_display_name(self):
        for q in self:
            q.display_name = f"[{q.code}] {q.label}" if q.code else q.label

    @api.constrains("condition")
    def _check_condition(self):
        for q in self.filtered("condition"):
            try:
                json.loads(q.condition)
            except ValueError as e:
                raise ValidationError(f"شرط الظهور في {q.code} مش JSON صحيح: {e}") from e

    def _engine_dict(self):
        self.ensure_one()
        return {
            "id": self.id, "key": self.key, "code": self.code, "label": self.label,
            "qtype": self.qtype, "group": self.group, "clause": self.clause,
            "condition": json.loads(self.condition) if self.condition else None,
            "raci": self.raci, "is_common": self.is_common, "is_role": self.is_role,
        }
