from odoo import Command, fields, models


class AzmEntity(models.Model):
    _name = "azm.entity"
    _description = "AZM Entity"
    _order = "sequence, code"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one("res.company", help="الشركة المقابلة في Odoo إن وجدت.")
    user_ids = fields.Many2many(
        "res.users", "azm_entity_res_users_rel", "entity_id", "user_id", string="المستخدمون المصرح لهم",
        domain=[("share", "=", False)],
        help="معدّو الإفادات والمراجعون الذين يرون هذا الكيان وإفاداته ومخاطره. مدير النموذج يرى كل الكيانات.")
    color = fields.Integer()
    active = fields.Boolean(default=True)
    assessment_ids = fields.One2many("azm.assessment", "entity_id")
    assessment_count = fields.Integer(compute="_compute_assessment_count")

    _code_uniq = models.Constraint("UNIQUE(code)", "كود الكيان لازم يكون فريد.")

    def _azm_grant_existing_users(self):
        """Give each entity's existing preparers / reviewers access to it (used on upgrade)."""
        for entity in self.sudo().with_context(active_test=False).search([]):
            assessments = self.env["azm.assessment"].sudo().with_context(active_test=False).search(
                [("entity_id", "=", entity.id)])
            users = (assessments.user_id | assessments.reviewer_id | assessments.create_uid).filtered(
                lambda u: not u.share and u.id != 1)
            if users:
                entity.user_ids = [Command.link(u.id) for u in users]

    def _compute_assessment_count(self):
        counts = dict(self.env["azm.assessment"]._read_group(
            [("entity_id", "in", self.ids)], ["entity_id"], ["__count"]))
        for entity in self:
            entity.assessment_count = counts.get(entity, 0)
