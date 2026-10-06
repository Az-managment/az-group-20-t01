"""A part of an assessment sent back to be done again, with the reason why.

A review used to be all or nothing: approve the whole thing, or push the whole thing
back to draft with no record of what was wrong. The reviewer then wrote the reason
somewhere else, and whoever picked the work up had to read every answer again to find
the three that were the problem.

A return names the part — a module, a topic, one requirement; a stage, one question —
and carries the note. While any is open the assessment is back with its preparer, and
only the named parts may be touched: the rest stands as it was reviewed, so answering
one thing cannot quietly change another that was already accepted.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# What a return may name, narrowest last. The order matters: a return on a module
# covers every requirement under it, so the levels are checked broad to narrow.
FIN_LEVELS = ("module_id", "topic_id", "requirement_id")
PROC_LEVELS = ("stage_id", "question_id")


class AzmReviewReturn(models.Model):
    _name = "azm.review.return"
    _description = "جزء مُعاد للمعالجة"
    _order = "create_date desc, id desc"
    _rec_name = "part_name"

    # one side or the other, the way an assignment does it
    fin_assessment_id = fields.Many2one("azm.fin.assessment", "الإفادة المالية",
                                        ondelete="cascade", index=True)
    module_id = fields.Many2one("azm.fin.module", "الموديول", ondelete="cascade")
    topic_id = fields.Many2one("azm.fin.topic", "الموضوع", ondelete="cascade")
    requirement_id = fields.Many2one("azm.fin.requirement", "المتطلب", ondelete="cascade")

    proc_assessment_id = fields.Many2one("azm.assessment", "إفادة المشتريات",
                                         ondelete="cascade", index=True)
    stage_id = fields.Many2one("azm.stage", "المرحلة", ondelete="cascade")
    question_id = fields.Many2one("azm.question", "السؤال", ondelete="cascade")

    note = fields.Text("الملاحظة", required=True,
                       help="ما الذي يحتاج معالجة في هذا الجزء.")
    state = fields.Selection([("open", "مفتوحة"), ("done", "عولجت")],
                             "الحالة", default="open", required=True, index=True)
    reviewer_id = fields.Many2one("res.users", "المراجع", required=True, index=True,
                                  default=lambda self: self.env.user)
    user_id = fields.Many2one("res.users", "المسؤول عن المعالجة", index=True,
                              help="من عليه معالجة هذا الجزء؛ يُقرأ من توزيع الأجزاء.")
    resolved_on = fields.Datetime("تاريخ المعالجة", readonly=True, copy=False)

    entity_id = fields.Many2one("azm.entity", "الكيان", compute="_compute_source",
                                store=True, index=True)
    company_id = fields.Many2one("res.company", "الشركة", compute="_compute_source",
                                 store=True, index=True)
    model_key = fields.Selection([("financial", "النموذج المالي الموحد"),
                                  ("procurement", "دورة المشتريات")],
                                 "النموذج", compute="_compute_source", store=True)
    level = fields.Selection([("module", "موديول"), ("topic", "موضوع"),
                              ("requirement", "متطلب"), ("stage", "مرحلة"),
                              ("question", "سؤال")],
                             "المستوى", compute="_compute_source", store=True)
    part_name = fields.Char("الجزء", compute="_compute_source", store=True)

    @api.depends("fin_assessment_id", "proc_assessment_id", "module_id", "topic_id",
                 "requirement_id", "stage_id", "question_id")
    def _compute_source(self):
        for record in self:
            assessment = record.fin_assessment_id or record.proc_assessment_id
            record.entity_id = assessment.entity_id
            record.company_id = assessment.company_id
            record.model_key = "financial" if record.fin_assessment_id else (
                "procurement" if record.proc_assessment_id else False)
            # narrowest first: a return naming a requirement is about that requirement,
            # whatever its module says
            if record.requirement_id:
                record.level, record.part_name = "requirement", record.requirement_id.display_name
            elif record.topic_id:
                record.level, record.part_name = "topic", record.topic_id.display_name
            elif record.module_id:
                record.level = "module"
                record.part_name = f"FIN.{record.module_id.code} · {record.module_id.name}"
            elif record.question_id:
                record.level, record.part_name = "question", record.question_id.display_name
            elif record.stage_id:
                record.level = "stage"
                record.part_name = f"PUR-{record.stage_id.code} · {record.stage_id.name}"
            else:
                record.level, record.part_name = False, ""

    @api.constrains("fin_assessment_id", "proc_assessment_id", "module_id", "topic_id",
                    "requirement_id", "stage_id", "question_id")
    def _check_one_part(self):
        for record in self:
            sides = bool(record.fin_assessment_id) + bool(record.proc_assessment_id)
            if sides != 1:
                raise ValidationError(_("A return belongs to one assessment."))
            named = [bool(record[name]) for name in FIN_LEVELS + PROC_LEVELS]
            if sum(named) != 1:
                raise ValidationError(_("A return names exactly one part."))
            if record.fin_assessment_id and not any(record[name] for name in FIN_LEVELS):
                raise ValidationError(_("A financial return names a module, a topic or a requirement."))
            if record.proc_assessment_id and not any(record[name] for name in PROC_LEVELS):
                raise ValidationError(_("A procurement return names a stage or a question."))

    def action_done(self):
        """Mark the part as dealt with — the preparer does this, or sending for review does."""
        self.write({"state": "done", "resolved_on": fields.Datetime.now()})

    # The assessments count these, and a count of rows in another table is not something
    # @api.depends can follow. So the assessments are told whenever a return appears or
    # changes, or they would answer from a cache taken before it did.
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._touch_assessments()
        return records

    def write(self, vals):
        before = self._assessment_sets()
        result = super().write(vals)
        for records in before + self._assessment_sets():
            records._invalidate_returns()
        return result

    def unlink(self):
        before = self._assessment_sets()
        result = super().unlink()
        for records in before:
            records._invalidate_returns()
        return result

    def _assessment_sets(self):
        """The two sides as separate recordsets: they are different models, so they
        cannot be added together."""
        return [self.fin_assessment_id, self.proc_assessment_id]

    def _touch_assessments(self):
        for records in self._assessment_sets():
            records._invalidate_returns()

    # ------------------------------------------------------------------ matching
    @api.model
    def _open_for(self, assessment):
        field = ("fin_assessment_id" if assessment._name == "azm.fin.assessment"
                 else "proc_assessment_id")
        return self.sudo().search([(field, "=", assessment.id), ("state", "=", "open")])

    def _covers(self, line):
        """Is ``line`` — one answer — inside any of these returns?

        A return on a module covers every requirement under it; one on a topic covers
        that topic; one on a requirement covers only itself. The same broad-to-narrow
        reading applies to a stage and the questions under it.
        """
        for record in self:
            if record.requirement_id and line._name == "azm.fin.answer":
                if line.requirement_id == record.requirement_id:
                    return True
            if record.topic_id and line._name == "azm.fin.answer":
                if line.topic_id == record.topic_id:
                    return True
            if record.module_id and line._name == "azm.fin.answer":
                if line.module_id == record.module_id:
                    return True
            if record.question_id and line._name == "azm.answer":
                if line.question_id == record.question_id:
                    return True
            if record.stage_id and line._name == "azm.answer":
                if line.stage_id == record.stage_id:
                    return True
        return False
