from odoo import fields, models


class AzmRiskRule(models.Model):
    _name = "azm.risk.rule"
    _description = "AZM Risk Rule"
    _order = "stage_id, sequence, id"

    code = fields.Char(required=True, index=True)
    stage_id = fields.Many2one("azm.stage", required=True, ondelete="cascade")
    question_id = fields.Many2one("azm.question", required=True, ondelete="cascade",
                                  domain="[('stage_id', '=', stage_id)]")
    trigger_option_id = fields.Many2one("azm.option", required=True, ondelete="cascade",
                                        domain="[('question_id', '=', question_id)]",
                                        string="الإجابة المفعّلة")
    sequence = fields.Integer(default=10)
    fact = fields.Char("الممارسة", required=True, translate=True)
    risk = fields.Char("الأثر المحتمل", required=True, translate=True)
    control = fields.Char("الضابط المقترح", required=True, translate=True)
    owner_hint = fields.Char("مسؤول المراجعة المقترح", translate=True)
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint("UNIQUE(code)", "كود القاعدة لازم يكون فريد.")

    def _engine_dict(self):
        self.ensure_one()
        return {
            "code": self.code, "stage": self.stage_id.code, "key": self.question_id.key,
            "trigger": self.trigger_option_id.name, "fact": self.fact, "risk": self.risk,
            "control": self.control, "owner": self.owner_hint or "",
        }
