"""Who answers which part of a model.

One person owning a whole assessment is the wrong shape for most entities: the financial
model is 19 modules and 167 requirements, and Treasury, HR and Procurement each know
their own part and not the others'. So a part can be given to somebody, and then it is
theirs: they answer it, and the people it was not given to can read it but not write it.

A part is a module of the financial model or a stage of the procurement cycle. Both live
here rather than in two parallel models, because the question an administrator asks —
*who is doing what, and how far have they got* — is one question across both.

Unassigned parts stay with whoever prepares the assessment, so an entity that does not
want to split the work does not have to: assigning nothing changes nothing.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AzmAssignment(models.Model):
    _name = "azm.assignment"
    _description = "AZM part assignment"
    _order = "company_id, user_id, sequence, id"
    _rec_name = "part_name"

    user_id = fields.Many2one("res.users", "المسؤول", required=True, index=True,
                              domain=[("share", "=", False)])
    note = fields.Char("ملاحظة")

    # one side or the other, never both — see _check_one_side
    fin_assessment_id = fields.Many2one("azm.fin.assessment", "الإفادة المالية",
                                        ondelete="cascade", index=True)
    module_id = fields.Many2one("azm.fin.module", "الموديول", ondelete="cascade")
    proc_assessment_id = fields.Many2one("azm.assessment", "إفادة المشتريات",
                                         ondelete="cascade", index=True)
    stage_id = fields.Many2one("azm.stage", "المرحلة", ondelete="cascade")

    entity_id = fields.Many2one("azm.entity", "الكيان", compute="_compute_source",
                                store=True, index=True)
    company_id = fields.Many2one("res.company", "الشركة", compute="_compute_source",
                                 store=True, index=True)
    model_key = fields.Selection([("financial", "النموذج المالي الموحد"),
                                  ("procurement", "دورة المشتريات")],
                                 "النموذج", compute="_compute_source", store=True)
    sequence = fields.Integer(compute="_compute_source", store=True)
    part_name = fields.Char("الجزء", compute="_compute_source", store=True)

    answered = fields.Integer("مُجاب", compute="_compute_progress")
    total = fields.Integer("الأسئلة", compute="_compute_progress")
    left = fields.Integer("المتبقي", compute="_compute_progress", search="_search_left")
    progress = fields.Float("نسبة الاكتمال", compute="_compute_progress")
    state = fields.Selection(related="fin_assessment_id.state", string="حالة الإفادة")

    _one_part = models.Constraint(
        "CHECK((fin_assessment_id IS NULL) <> (proc_assessment_id IS NULL))",
        "التوزيع يخص إفادة واحدة: مالية أو مشتريات.")
    _fin_uniq = models.Constraint(
        "UNIQUE(fin_assessment_id, module_id)",
        "هذا الموديول مُسند بالفعل في هذه الإفادة.")
    _proc_uniq = models.Constraint(
        "UNIQUE(proc_assessment_id, stage_id)",
        "هذه المرحلة مُسندة بالفعل في هذه الإفادة.")

    @api.depends("fin_assessment_id", "module_id", "proc_assessment_id", "stage_id")
    def _compute_source(self):
        for record in self:
            if record.fin_assessment_id:
                module = record.module_id
                record.entity_id = record.fin_assessment_id.entity_id
                record.company_id = record.fin_assessment_id.company_id
                record.model_key = "financial"
                record.sequence = module.sequence
                record.part_name = f"FIN.{module.code} · {module.name}" if module else ""
            else:
                stage = record.stage_id
                record.entity_id = record.proc_assessment_id.entity_id
                record.company_id = record.proc_assessment_id.company_id
                record.model_key = "procurement"
                record.sequence = stage.sequence
                record.part_name = f"PUR-{stage.code} · {stage.name}" if stage else ""

    def _compute_progress(self):
        """How far the person it was given to has got with it."""
        for record in self:
            lines = record._lines()
            if record.model_key == "financial":
                visible = lines.filtered("applicable")
                total, answered = visible._question_totals() if visible else (0, 0)
            else:
                visible = lines.filtered("is_visible")
                total, answered = len(visible), len(visible.filtered("has_value"))
            record.total = total
            record.answered = answered
            record.left = max(total - answered, 0)
            record.progress = 100.0 * answered / total if total else 0.0

    def _search_left(self, operator, value):
        """"What is still outstanding" is the question an administrator filters on, and
        it is counted from the answers rather than stored — so it is worked out here.

        Storing it would mean recomputing every assignment on every answer written,
        which is a great deal of churn for a figure read a few times a day. There are a
        few hundred assignments, so counting them when somebody asks is the cheaper
        side of that trade.
        """
        import operator as ops
        allowed = {"=": ops.eq, "!=": ops.ne, "<": ops.lt, "<=": ops.le,
                   ">": ops.gt, ">=": ops.ge}
        if operator not in allowed:
            raise NotImplementedError(operator)
        test = allowed[operator]
        # an empty domain, so this cannot re-enter itself
        hit = self.search([]).filtered(lambda r: test(r.left, value))
        return [("id", "in", hit.ids)]

    def _lines(self):
        """The answer lines this part covers."""
        self.ensure_one()
        if self.model_key == "financial":
            return self.fin_assessment_id.answer_ids.filtered(
                lambda a: a.module_id == self.module_id)
        return self.proc_assessment_id.answer_ids.filtered(
            lambda a: a.stage_id == self.stage_id)

    @api.constrains("module_id", "stage_id", "fin_assessment_id", "proc_assessment_id")
    def _check_part_matches_side(self):
        for record in self:
            if record.fin_assessment_id and not record.module_id:
                raise ValidationError(_("Name the module this covers."))
            if record.proc_assessment_id and not record.stage_id:
                raise ValidationError(_("Name the stage this covers."))

    @api.constrains("user_id", "entity_id")
    def _check_assignee_can_see_the_entity(self):
        """Giving somebody a part they cannot open is giving them nothing.

        The record rules read the entity's own list of people, so an assignee who is not
        on it would be shown work and then refused it.
        """
        group = self.env.ref("azm_operating_model.azm_group_user", raise_if_not_found=False)
        for record in self:
            user = record.user_id
            if not user or not record.entity_id:
                continue
            if group and group not in user.all_group_ids:
                raise ValidationError(_(
                    "%s is not an AZM user, so they cannot answer anything.", user.name))
            if user not in record.entity_id.sudo().user_ids:
                raise ValidationError(_(
                    "%(user)s is not on %(entity)s, so they could not open this part. "
                    "Add them to the entity first.",
                    user=user.name, entity=record.entity_id.name))


class AzmAssignable(models.AbstractModel):
    """An answer line that belongs to a part somebody may have been given."""
    _name = "azm.assignable"
    _description = "AZM assignable answer line"

    def _azm_part_key(self):
        """``(assessment id, part id)`` this line falls under. Overridden per model."""
        self.ensure_one()
        return None

    @api.model
    def _azm_assignments(self, lines):
        """``{(assessment id, part id): user id}`` for everything these lines touch."""
        raise NotImplementedError

    def _azm_check_assignee(self):
        """Refuse a write to a part that was given to somebody else.

        The access rules cannot say this: whether a line is writable depends on a row in
        another table matched on *this* line's module, which a record-rule domain cannot
        express. So it is said here, where every write passes — including over RPC.
        """
        if not self or self.env.su:
            return
        if self.env.user.has_group("azm_operating_model.azm_group_manager"):
            return
        assignments = self._azm_assignments(self)
        if not assignments:
            return
        uid = self.env.uid
        for line in self:
            key = line._azm_part_key()
            owner = assignments.get(key)
            if owner and owner != uid:
                raise UserError(_(
                    "%s is answered by somebody else. You can read it, but it is not "
                    "yours to fill in.", line._azm_part_name()))

    def _azm_check_returns(self):
        """Refuse a write to a part the reviewer did not send back.

        When a review returns named parts, the rest of the assessment stands as it was
        reviewed. Answering something outside them would change work that was already
        accepted, without the reviewer ever seeing it again — so while any return is
        open, only what it names may be touched.

        Said here rather than in an access rule for the same reason as above: whether a
        line is writable depends on rows in another table matched against this line's
        module, topic, requirement, stage or question.
        """
        if not self or self.env.su:
            return
        Return = self.env["azm.review.return"]
        by_assessment = {}
        for line in self:
            by_assessment.setdefault(line.assessment_id, self.browse())
            by_assessment[line.assessment_id] |= line
        for assessment, lines in by_assessment.items():
            returns = Return._open_for(assessment)
            if not returns:
                continue
            for line in lines:
                if not returns._covers(line):
                    raise UserError(_(
                        "This assessment came back with %s part(s) to deal with, and "
                        "%s is not one of them. Answer what was returned and send it "
                        "back for review.", len(returns), line._azm_part_name() or line.display_name))

    def _azm_part_name(self):
        self.ensure_one()
        return ""
