"""Work that is prepared by one person and then reviewed by another.

Both assessments follow the same path — draft, review, approved — and both used to
leave review by writing the state and scheduling an activity *if* a reviewer happened
to be named on the record. Where none was, the work left the preparer's hands and
arrived in nobody's: the state said "under review" and no human had been told.

So the two of them share this: who should be looking at it now, and a submit that
refuses to send work somewhere nobody is standing.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AzmReviewable(models.AbstractModel):
    _name = "azm.reviewable"
    _description = "AZM prepared-then-reviewed work"

    # The state is a workflow, and a workflow is the buttons, not a column anyone with
    # write access can set. The access rules cannot enforce this on their own: a row's
    # domain is checked against the record as it was *before* the write, so a rule
    # saying "you may write work that is under review" cannot also say "but not to
    # approve it" — `{'state': 'approved'}` passes the check and lands.
    #
    # That let a reviewer approve work directly: no version snapshot taken, no
    # approved_by, no approved_date, and none of the separation of duties that
    # action_approve exists to enforce. It let a preparer approve their own draft, too.
    # So every state change goes through the buttons, which carry this flag.
    AZM_WORKFLOW = "azm_workflow"

    def _workflow(self):
        """This record, with the right to move itself along."""
        return self.with_context(**{self.AZM_WORKFLOW: True})

    def write(self, vals):
        if "state" in vals and not self.env.context.get(self.AZM_WORKFLOW) \
                and not self.env.su:
            for record in self:
                if record.state != vals["state"]:
                    raise UserError(_(
                        "The state of an assessment is changed with its buttons — "
                        "send for review, approve, send back — not by writing to it."))
        return super().write(vals)

    # Who may be put on this, for the two Many2ones to choose from. Assigning somebody
    # who is not on the entity hands them work they cannot open — the record rules read
    # the entity's own list — so the choice is narrowed to people who could actually do
    # the job rather than to every user in the database.
    allowed_preparer_ids = fields.Many2many(
        "res.users", string="من يمكن أن يُعدّها", compute="_compute_allowed_people")
    allowed_reviewer_ids = fields.Many2many(
        "res.users", string="من يمكن أن يراجعها", compute="_compute_allowed_people")

    @api.depends("entity_id")
    def _compute_allowed_people(self):
        preparers = self.env.ref("azm_operating_model.azm_group_user",
                                 raise_if_not_found=False)
        reviewers = self.env.ref("azm_operating_model.azm_group_reviewer",
                                 raise_if_not_found=False)
        for record in self:
            # sudo: who is assigned to an entity is not something the reader of this
            # record necessarily may list, but it is what decides who can be put here
            assigned = record.entity_id.sudo().user_ids.filtered(lambda u: u.active)
            for field, group in (("allowed_preparer_ids", preparers),
                                 ("allowed_reviewer_ids", reviewers)):
                people = assigned.filtered(lambda u, g=group: g in u.all_group_ids) \
                    if group else assigned
                if not people and group:
                    # nobody assigned to this entity yet: offer the role at large rather
                    # than an empty list that cannot be got out of
                    people = group.sudo().all_user_ids.filtered(
                        lambda u: u.active and not u.share)
                record[field] = people

    def _review_group(self):
        return "azm_operating_model.azm_group_reviewer"

    def _reviewers(self):
        """Who should be looking at this now, in order of how directly it is theirs.

        The named reviewer if there is one. Otherwise the reviewers of this entity —
        the people already trusted with it — and failing that the model's managers, who
        can at least name somebody. The preparer is never their own reviewer: that is
        the separation of duties the approval step enforces further on.
        """
        self.ensure_one()
        if self.reviewer_id:
            return self.reviewer_id
        group = self.env.ref(self._review_group(), raise_if_not_found=False)
        if not group:
            return self.env["res.users"]
        preparer = self.user_id or self.create_uid
        # the entity's own people first: they are assigned to it already
        assigned = self.entity_id.sudo().user_ids.filtered(
            lambda u: u.active and group in u.all_group_ids and u != preparer)
        if assigned:
            return assigned
        managers = self.env.ref("azm_operating_model.azm_group_manager",
                                raise_if_not_found=False)
        if not managers:
            return self.env["res.users"]
        return managers.sudo().all_user_ids.filtered(lambda u: u.active and u != preparer)

    def _notify_reviewers(self, reviewers, summary):
        """Put it on each reviewer's list.

        As superuser on purpose: submitting is the moment the preparer loses write
        access to the record, so they cannot be the one to write the activity onto it.
        """
        self.ensure_one()
        for reviewer in reviewers:
            self.sudo().activity_schedule(
                "mail.mail_activity_data_todo", user_id=reviewer.id, summary=summary)

    @api.model
    def _review_summary(self):
        return _("Review an AZM assessment")

    def _submit_for_review(self, summary=None):
        """Hand the work to whoever reviews it, or say why it cannot be handed over."""
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("Only a draft can be sent for review."))
        reviewers = self._reviewers()
        if not reviewers:
            # better to stop here than to park the work in a state nobody is watching
            raise UserError(_(
                "There is nobody to review this. Ask an administrator to name a "
                "reviewer on it, or to assign a reviewer to %s.",
                self.entity_id.name or ""))
        self._workflow().state = "review"
        self._notify_reviewers(reviewers, summary or self._review_summary())
        return reviewers
