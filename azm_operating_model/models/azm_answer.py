from odoo import api, fields, models
from odoo.exceptions import UserError


class AzmAnswer(models.Model):
    _name = "azm.answer"
    _inherit = ["azm.assignable"]
    _description = "AZM Answer"
    _order = "stage_sequence, group, question_sequence, id"

    assessment_id = fields.Many2one("azm.assessment", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="assessment_id.company_id", store=True)
    question_id = fields.Many2one("azm.question", required=True, ondelete="restrict", index=True)
    stage_id = fields.Many2one(related="question_id.stage_id", store=True)
    stage_sequence = fields.Integer(related="question_id.stage_sequence", store=True, string="ترتيب المرحلة")
    question_sequence = fields.Integer(related="question_id.sequence", store=True, string="ترتيب السؤال")
    group = fields.Selection(related="question_id.group", store=True)
    qtype = fields.Selection(related="question_id.qtype")
    code = fields.Char(related="question_id.code")
    label = fields.Char(related="question_id.label")
    option_id = fields.Many2one("azm.option", string="الإجابة",
                                domain="[('question_id', '=', question_id)]")
    option_ids = fields.Many2many("azm.option", string="الإجابات",
                                  domain="[('question_id', '=', question_id)]")
    value_number = fields.Float("القيمة")
    has_value = fields.Boolean(compute="_compute_state", store=True)
    is_known = fields.Boolean(compute="_compute_state", store=True)
    is_visible = fields.Boolean(default=True, readonly=True)
    note = fields.Text("ملاحظة")
    attachment_ids = fields.Many2many("ir.attachment", string="أدلة")

    _assessment_question_uniq = models.Constraint(
        "UNIQUE(assessment_id, question_id)", "السؤال متكرر في نفس الإفادة.")

    @api.depends("option_id", "option_ids", "value_number", "qtype")
    def _compute_state(self):
        for a in self:
            if a.qtype == "multi":
                a.has_value = bool(a.option_ids)
                a.is_known = a.has_value and not a.option_ids.filtered(
                    lambda o: o.kind in ("unknown", "not_listed"))
            elif a.qtype == "number":
                a.has_value = a.is_known = bool(a.value_number)
            else:
                a.has_value = bool(a.option_id)
                a.is_known = a.has_value and a.option_id.kind not in ("unknown", "not_listed")

    def _engine_value(self):
        self.ensure_one()
        if self.qtype == "multi":
            return self.option_ids.sorted("sequence").mapped("name") or None
        if self.qtype == "number":
            return self.value_number or None
        return self.option_id.name or None

    def write(self, vals):
        value_keys = {"option_id", "option_ids", "value_number"}
        if value_keys & set(vals) and not self.env.context.get("azm_skip_lock"):
            if any(a.assessment_id.state != "draft" for a in self):
                raise UserError("الإفادة مش في حالة مسودة؛ لا يمكن تعديل الإجابات.")
            self._azm_check_assignee()
            self._azm_check_returns()
        res = super().write(vals)
        if value_keys & set(vals) and not self.env.context.get("azm_no_visibility"):
            self.assessment_id._refresh_visibility()
        return res

    # ---------------------------------------------------------------- whose part
    def _azm_part_key(self):
        self.ensure_one()
        return (self.assessment_id.id, self.stage_id.id)

    def _azm_part_name(self):
        self.ensure_one()
        return f"PUR-{self.stage_id.code}"

    @api.model
    def _azm_assignments(self, lines):
        found = self.env["azm.assignment"].sudo().search(
            [("proc_assessment_id", "in", lines.assessment_id.ids)])
        return {(a.proc_assessment_id.id, a.stage_id.id): a.user_id.id for a in found}
