from odoo import fields, models


class AzmAssessmentVersion(models.Model):
    _name = "azm.assessment.version"
    _description = "AZM Approved Snapshot"
    _order = "approved_date desc, id desc"

    assessment_id = fields.Many2one("azm.assessment", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="assessment_id.company_id", store=True)
    version = fields.Integer(required=True)
    approved_date = fields.Datetime(required=True, default=fields.Datetime.now)
    approved_by_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user)
    answers_json = fields.Text("الإجابات (JSON)", readonly=True)
    snapshot_html = fields.Html("نسخة الوثائق المعتمدة", sanitize=False, readonly=True)
