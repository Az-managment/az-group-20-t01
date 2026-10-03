from odoo import api, fields, models
from odoo.exceptions import UserError

LEVELS = [("1", "1 · منخفض جدًا"), ("2", "2 · منخفض"), ("3", "3 · متوسط"), ("4", "4 · مرتفع"), ("5", "5 · مرتفع جدًا")]


class AzmFinding(models.Model):
    _name = "azm.finding"
    _description = "ملاحظة خطر AZM"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "stage_sequence, code"

    assessment_id = fields.Many2one("azm.assessment", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="assessment_id.company_id", store=True)
    entity_id = fields.Many2one(related="assessment_id.entity_id", store=True)
    stage_id = fields.Many2one("azm.stage", "المرحلة", required=True)
    stage_sequence = fields.Integer(related="stage_id.sequence", store=True)
    code = fields.Char("الكود", required=True, readonly=True)
    fact = fields.Char("الممارسة المبلّغ عنها", required=True)
    risk = fields.Char("الأثر المحتمل")
    control = fields.Char("الضابط المقترح")
    owner_hint = fields.Char("مسؤول المراجعة المقترح")
    triggered = fields.Boolean("ما زالت مفعّلة", default=True,
                               help="بتتلغي لو الإجابات اتغيرت والقاعدة مبقتش منطبقة.")
    state = fields.Selection([
        ("candidate", "مرشح للتحقق"),
        ("confirmed", "مؤكد"),
        ("treatment", "تحت المعالجة"),
        ("closed", "مغلق بدليل"),
        ("dismissed", "مستبعد"),
    ], default="candidate", required=True, tracking=True, string="الحالة", group_expand=True)
    likelihood = fields.Selection(LEVELS, "الاحتمال", tracking=True)
    impact = fields.Selection(LEVELS, "الأثر", tracking=True)
    score = fields.Integer("الدرجة", compute="_compute_score", store=True)
    user_id = fields.Many2one("res.users", "مالك المعالجة", tracking=True)
    due_date = fields.Date("موعد المعالجة", tracking=True)
    evidence = fields.Text("دليل الإقفال")

    _assessment_code_uniq = models.Constraint("UNIQUE(assessment_id, code)", "الملاحظة متكررة.")

    @api.depends("likelihood", "impact")
    def _compute_score(self):
        for f in self:
            f.score = int(f.likelihood or 0) * int(f.impact or 0)

    def action_confirm(self):
        self.write({"state": "confirmed"})

    def action_treat(self):
        self.write({"state": "treatment"})
        for f in self.filtered("user_id"):
            f.activity_schedule("mail.mail_activity_data_todo", user_id=f.user_id.id,
                                date_deadline=f.due_date, summary=f"معالجة: {f.fact}")

    def action_close(self):
        for f in self:
            if not f.evidence:
                raise UserError("الإقفال يحتاج دليل مكتوب في «دليل الإقفال».")
        self.write({"state": "closed"})

    def action_dismiss(self):
        self.write({"state": "dismissed"})
