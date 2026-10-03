"""Serve the financial questions to the workspace, with follow-ups resolved.

The visibility rule is the procurement one, reused rather than reimplemented:
`engine.condition` over a dict of answers keyed by question key. The scope here
is the requirement, playing the part the stage plays on the procurement side.

The walk is deliberately order-sensitive. An answer only enters the dict once
its own question has been shown, so a value typed before its trigger changed is
ignored rather than counted. That is what keeps a hidden follow-up from
influencing anything.
"""

import json

from odoo import api, models
from odoo.exceptions import UserError

from . import engine, fin_engine


class AzmFinAnswer(models.Model):
    _inherit = "azm.fin.answer"

    def _visible_questions(self):
        """The question answers to show, in order, for this requirement."""
        self.ensure_one()
        visible = self.env["azm.fin.qanswer"]
        answers = {}
        for line in self.qanswer_ids.sorted(lambda l: (l.sequence, l.id)):
            question = line.question_id
            condition = json.loads(question.condition) if question.condition else None
            if not engine.condition(condition, answers):
                continue
            visible |= line
            value = line._engine_value()
            if value is not None:
                answers[question.key] = value
        return visible

    def _refresh_visibility(self):
        """Persist which questions are showing, so counts and lists agree."""
        for answer in self:
            visible = set(answer._visible_questions().ids)
            for line in answer.qanswer_ids:
                flag = line.id in visible
                if line.is_visible != flag:
                    line.with_context(
                        azm_no_visibility=True, azm_skip_lock=True).is_visible = flag

    def _question_dicts(self):
        self.ensure_one()
        payload = []
        for line in self._visible_questions():
            question = line.question_id
            payload.append({
                "line_id": line.id,
                "code": question.code,
                "key": question.key,
                "label": question.label,
                "role": question.role,
                "qtype": question.qtype,
                "unit": question.unit or "",
                "help": question.help_text or "",
                "text_label": question.text_label or "",
                # [{label, options}] — a column that lists its choices renders
                # as a dropdown, one that does not stays a free-text cell.
                "columns": fin_engine.typed_columns(question._columns()),
                "options": [{"id": o.id, "name": o.name, "kind": o.kind}
                            for o in question.option_ids],
                "option_id": line.option_id.id or False,
                "option_ids": line.option_ids.ids,
                "value_number": line.value_number or False,
                "text": line.text or "",
                "table": json.loads(line.table_json) if line.table_json else [],
            })
        return payload

    def _workspace_dict(self, light=False):
        data = super()._workspace_dict(light=light)
        if not light:
            data["questions"] = self._question_dicts()
        return data


class AzmFinRequirement(models.Model):
    _inherit = "azm.fin.requirement"

    def _schema(self):
        """Same schema, with the widget each column should use."""
        schema = super()._schema()
        schema["columns"] = fin_engine.typed_columns(schema.get("columns"))
        return schema


class AzmFinQAnswer(models.Model):
    _inherit = "azm.fin.qanswer"

    def _workspace_write(self, vals):
        """Store one question's answer, whatever shape it has."""
        self.ensure_one()
        question = self.question_id
        clean = {}
        if "option_id" in vals:
            option = self.env["azm.fin.option"].browse(vals["option_id"] or 0).exists()
            if option and option.question_id != question:
                raise UserError(self.env._("هذا الاختيار مش تابع للسؤال."))
            clean["option_id"] = option.id if option else False
        if "option_ids" in vals:
            options = self.env["azm.fin.option"].browse(vals["option_ids"] or []).exists()
            stray = options.filtered(lambda o: o.question_id != question)
            if stray:
                raise UserError(self.env._("بعض الاختيارات مش تابعة للسؤال."))
            clean["option_ids"] = [(6, 0, options.ids)]
        if "value_number" in vals:
            clean["value_number"] = vals["value_number"] or 0.0
        if "text" in vals:
            clean["text"] = vals["text"] or False
        if "table" in vals:
            rows = [[str(cell or "") for cell in row]
                    for row in (vals["table"] or []) if isinstance(row, list)]
            clean["table_json"] = json.dumps(rows, ensure_ascii=False) if rows else False
        if clean:
            self.write(clean)

    def write(self, vals):
        res = super().write(vals)
        touched = {"option_id", "option_ids", "value_number", "text", "table_json"} & set(vals)
        if touched and not self.env.context.get("azm_no_visibility"):
            # Only the requirement that changed: the conditions never cross one.
            self.answer_id._refresh_visibility()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.answer_id._refresh_visibility()
        return records


class AzmFinAssessment(models.Model):
    _inherit = "azm.fin.assessment"

    def workspace_answer_question(self, line_id, vals, module_code=None, tab="book",
                                  scope="module"):
        """Answer one question and return the refreshed payload.

        The whole payload comes back because answering may reveal or hide a
        follow-up, and that decision is made on the server.
        """
        self.ensure_one()
        if self.state != "draft":
            raise UserError(self.env._("الإفادة مش في حالة مسودة؛ لا يمكن تعديل الإجابات."))
        line = self.env["azm.fin.qanswer"].browse(line_id).exists()
        if not line or line.assessment_id != self:
            raise UserError(self.env._("السؤال مش تابع لهذه الإفادة."))
        line._workspace_write(vals)
        return self.workspace_data(module_code=module_code, tab=tab, scope=scope)
