"""Derive the per-requirement roll-up from the standard questions.

`azm.fin.answer` stays exactly what every output, dashboard and register reads,
but it stops being typed directly: `state`, `impl`, `current` and `future` are
now computed from the four standard questions the spreadsheet repeats on every
requirement. Keeping two writable copies of the same fact is how these drift,
so the derived fields are stored and NOT `readonly=False` — a leftover direct
write fails loudly instead of silently disagreeing with the questionnaire.

`gap`, `reason` and the N/A declaration have no question behind them; they stay
typed on the requirement.
"""

from odoo import api, fields, models
from odoo.exceptions import UserError

# The الوضع الحالي scale, mapped onto the state codes every output already uses.
# "لا أعرف" deliberately maps to nothing: an unknown state is not a state.
STATE_BY_OPTION = {
    "مطبق بالكامل": "full",
    "مطبق جزئيًا": "partial",
    "غير منفذ": "unavailable",
}
OPTION_BY_STATE = {code: name for name, code in STATE_BY_OPTION.items()}

# Written only by _compute_rollup, never by hand.
DERIVED_FIELDS = {"state", "impl", "current", "future", "rule_status", "future_stance"}


class AzmFinQAnswer(models.Model):
    _inherit = "azm.fin.qanswer"

    answer_id = fields.Many2one("azm.fin.answer", "إجابة المتطلب", ondelete="cascade",
                                compute="_compute_answer_id", store=True, index=True)

    @api.depends("assessment_id", "question_id.requirement_id")
    def _compute_answer_id(self):
        """Link each question answer to its requirement's roll-up row."""
        pairs = {(a.assessment_id.id, a.question_id.requirement_id.id) for a in self}
        rollups = self.env["azm.fin.answer"].search([
            ("assessment_id", "in", [p[0] for p in pairs]),
            ("requirement_id", "in", [p[1] for p in pairs]),
        ])
        by_pair = {(r.assessment_id.id, r.requirement_id.id): r.id for r in rollups}
        for answer in self:
            answer.answer_id = by_pair.get(
                (answer.assessment_id.id, answer.question_id.requirement_id.id), False)


class AzmFinAnswer(models.Model):
    _inherit = "azm.fin.answer"

    qanswer_ids = fields.One2many("azm.fin.qanswer", "answer_id", string="إجابات الأسئلة")
    na_declared = fields.Boolean(
        "لا ينطبق", copy=True,
        help="لا يوجد سؤال يعبّر عن «لا ينطبق»؛ تُعلَن على مستوى المتطلب.")

    # Derived from the standard questions. Stored so every existing reader keeps
    # working, and intentionally without readonly=False.
    state = fields.Selection(compute="_compute_rollup", store=True)
    impl = fields.Char(compute="_compute_rollup", store=True)
    current = fields.Text(compute="_compute_rollup", store=True)
    future = fields.Text(compute="_compute_rollup", store=True)
    rule_status = fields.Char("حالة القاعدة", compute="_compute_rollup", store=True)
    future_stance = fields.Char("التوجه المستهدف", compute="_compute_rollup", store=True)

    @api.depends("na_declared", "qanswer_ids.role", "qanswer_ids.option_id",
                 "qanswer_ids.option_ids", "qanswer_ids.text")
    def _compute_rollup(self):
        for answer in self:
            by_role = {line.role: line for line in answer.qanswer_ids}
            state_line = by_role.get("state")
            target_line = by_role.get("target")
            impl_line = by_role.get("impl")
            rule_line = by_role.get("rule")

            chosen = state_line.option_id.name if state_line else False
            answer.state = "na" if answer.na_declared else STATE_BY_OPTION.get(chosen, False)
            answer.impl = ",".join(
                impl_line.option_ids.sorted("sequence").mapped("name")) or False if impl_line else False
            answer.current = (state_line.text or False) if state_line else False
            answer.future = (target_line.text or False) if target_line else False
            answer.rule_status = (rule_line.option_id.name or False) if rule_line else False
            answer.future_stance = (target_line.option_id.name or False) if target_line else False

    def write(self, vals):
        """Refuse a direct write to a derived field.

        Odoo does not stop code writing a stored computed field, so without this
        a leftover writer would set `state` and have it quietly disagree with the
        questionnaire until the next recompute. Writes must go through the
        questions, which is what _workspace_write does.
        """
        derived = DERIVED_FIELDS & set(vals)
        if derived and not self.env.context.get("azm_rollup_sync"):
            raise UserError(self.env._(
                "القيم %(fields)s مشتقّة من الأسئلة القياسية؛ عدّل إجابة السؤال بدل الكتابة عليها.",
                fields=", ".join(sorted(derived))))
        return super().write(vals)

    def _standard_line(self, role):
        self.ensure_one()
        return self.qanswer_ids.filtered(lambda line: line.role == role)[:1]

    def _workspace_write(self, vals):
        """Forward the derived values onto the questions they come from.

        Everything already calls this — the OWL workspace, action_fill_demo and
        the tests — so routing here keeps all of them working untouched while the
        questionnaire becomes the single source of truth.
        """
        vals = dict(vals)
        forwarded = {key: vals.pop(key) for key in ("state", "impl", "current", "future")
                     if key in vals}
        if forwarded:
            self._write_standard_questions(forwarded)
        super()._workspace_write(vals)

    def _write_standard_questions(self, vals):
        for answer in self:
            if "state" in vals:
                answer.na_declared = vals["state"] == "na"
                line = answer._standard_line("state")
                if line:
                    name = OPTION_BY_STATE.get(vals["state"])
                    option = line.question_id.option_ids.filtered(
                        lambda o: o.name == name)[:1] if name else False
                    line.option_id = option.id if option else False
            if "impl" in vals:
                line = answer._standard_line("impl")
                if line:
                    wanted = set(vals["impl"] or [])
                    options = line.question_id.option_ids.filtered(lambda o: o.name in wanted)
                    line.option_ids = [(6, 0, options.ids)]
            if "current" in vals:
                line = answer._standard_line("state")
                if line:
                    line.text = vals["current"] or False
            if "future" in vals:
                line = answer._standard_line("target")
                if line:
                    line.text = vals["future"] or False


class AzmFinAssessment(models.Model):
    _inherit = "azm.fin.assessment"

    def action_reset_answers(self):
        """Clear the questions as well as the typed fields.

        The base implementation writes state / impl / current / future directly;
        those are derived now, so clearing has to happen where the values live.
        """
        for record in self:
            if record.state != "draft":
                raise UserError(self.env._("المسح متاح للمسودة فقط."))
            record.qanswer_ids.write({
                "option_id": False, "option_ids": [(5, 0, 0)], "value_number": 0.0,
                "text": False, "table_json": False,
            })
            record.answer_ids.write({
                "na_declared": False, "gap": False, "reason": False,
                "table_json": False, "branch_json": False,
            })
            record.is_demo = False
        return True
