from odoo import fields, models


class AzmOption(models.Model):
    _name = "azm.option"
    _description = "AZM Answer Option"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    question_id = fields.Many2one("azm.question", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    kind = fields.Selection([
        ("normal", "إجابة"),
        ("unknown", "لا أعرف"),
        ("not_listed", "غير مدرج"),
        ("none", "لا يوجد"),
        ("na", "لا ينطبق"),
    ], default="normal", required=True)
    active = fields.Boolean(default=True)
