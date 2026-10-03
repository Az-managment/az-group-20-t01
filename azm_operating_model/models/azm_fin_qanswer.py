from odoo import api, fields, models
from odoo.exceptions import UserError

# Answer values, kept out of the related/computed fields so that a new version
# copies them (action_new_version copies the assessment).
VALUE_FIELDS = ("option_id", "option_ids", "value_number", "text", "table_json")


class AzmFinAssessment(models.Model):
    _inherit = "azm.fin.assessment"

    qanswer_ids = fields.One2many("azm.fin.qanswer", "assessment_id",
                                  string="إجابات الأسئلة", copy=True)
    qanswer_count = fields.Integer("عدد الأسئلة", compute="_compute_qanswer_count")

    @api.depends("qanswer_ids")
    def _compute_qanswer_count(self):
        for record in self:
            record.qanswer_count = len(record.qanswer_ids)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ensure_qanswers()
        return records

    def _ensure_qanswers(self):
        """One answer row per catalogue question, created up front.

        Mirrors _ensure_answers for the per-requirement roll-up. Questions added
        by a later catalogue reload are backfilled on the next call, which is why
        the migration calls this explicitly for assessments that already exist.
        """
        questions = self.env["azm.fin.question"].search([])
        rows = []
        for record in self:
            have = set(record.qanswer_ids.question_id.ids)
            rows += [{"assessment_id": record.id, "question_id": question.id}
                     for question in questions if question.id not in have]
        if rows:
            self.env["azm.fin.qanswer"].create(rows)
        return True


class AzmFinQAnswer(models.Model):
    _name = "azm.fin.qanswer"
    _description = "إجابة سؤال مالي"
    # Same ordering as the questions themselves: a trigger always comes before
    # whatever depends on it.
    _order = "module_sequence, requirement_sequence, sequence, id"

    assessment_id = fields.Many2one("azm.fin.assessment", required=True,
                                    ondelete="cascade", index=True)
    company_id = fields.Many2one(related="assessment_id.company_id", store=True)
    entity_id = fields.Many2one(related="assessment_id.entity_id", store=True, string="الكيان")
    question_id = fields.Many2one("azm.fin.question", "السؤال", required=True,
                                  ondelete="restrict", index=True)
    requirement_id = fields.Many2one(related="question_id.requirement_id", store=True,
                                     string="المتطلب")
    module_id = fields.Many2one(related="question_id.module_id", store=True, string="الموديول")
    module_sequence = fields.Integer(related="question_id.module_sequence", store=True)
    requirement_sequence = fields.Integer(related="question_id.requirement_sequence", store=True)
    sequence = fields.Integer(related="question_id.sequence", store=True)
    code = fields.Char(related="question_id.code", store=True, string="الكود")
    label = fields.Text(related="question_id.label", string="نص السؤال")
    role = fields.Selection(related="question_id.role", store=True, string="الدور")
    qtype = fields.Selection(related="question_id.qtype", store=True, string="شكل الإجابة")

    option_id = fields.Many2one("azm.fin.option", string="الإجابة",
                                ondelete="restrict",
                                domain="[('question_id', '=', question_id)]")
    option_ids = fields.Many2many("azm.fin.option", string="الإجابات",
                                  domain="[('question_id', '=', question_id)]")
    value_number = fields.Float("القيمة")
    text = fields.Text("نص حر")
    table_json = fields.Text("جدول الإجابة (JSON)")

    is_visible = fields.Boolean("ظاهر", default=True, readonly=True)
    has_value = fields.Boolean(compute="_compute_state", store=True)
    is_known = fields.Boolean(compute="_compute_state", store=True)

    _assessment_question_uniq = models.Constraint(
        "UNIQUE(assessment_id, question_id)", "السؤال متكرر في نفس الإفادة.")

    @api.depends("option_id", "option_ids", "value_number", "table_json", "qtype")
    def _compute_state(self):
        """`is_known` is false for "لا أعرف" / "غير مدرج", which keeps the
        follow-ups depending on this question hidden — same rule as azm.answer."""
        for answer in self:
            if answer.qtype == "multi":
                answer.has_value = bool(answer.option_ids)
                answer.is_known = answer.has_value and not answer.option_ids.filtered(
                    lambda option: option.kind in ("unknown", "not_listed"))
            elif answer.qtype == "number":
                answer.has_value = answer.is_known = bool(answer.value_number)
            elif answer.qtype == "table":
                answer.has_value = answer.is_known = bool(answer.table_json)
            else:
                answer.has_value = bool(answer.option_id)
                answer.is_known = answer.has_value and answer.option_id.kind not in (
                    "unknown", "not_listed")

    def _engine_value(self):
        """What the visibility engine compares against: option names, never ids."""
        self.ensure_one()
        if self.qtype == "multi":
            return self.option_ids.sorted("sequence").mapped("name") or None
        if self.qtype == "number":
            return self.value_number or None
        if self.qtype == "table":
            return self.table_json or None
        return self.option_id.name or None

    def write(self, vals):
        if set(VALUE_FIELDS) & set(vals) and not self.env.context.get("azm_skip_lock"):
            if any(a.assessment_id.state != "draft" for a in self):
                raise UserError(self.env._("الإفادة مش في حالة مسودة؛ لا يمكن تعديل الإجابات."))
        return super().write(vals)
