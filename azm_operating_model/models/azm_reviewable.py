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

# The value that marks a state change as coming from a workflow button. It is an object
# rather than True because a caller supplies the context of an RPC call: any value that
# can be written in JSON can be forged by whoever is asking.
AZM_WORKFLOW_TOKEN = object()



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

    # ... and the value under that key is this object, compared by identity.
    #
    # A context key alone cannot carry authority: the context of an RPC call is sent by
    # the caller, so `{"azm_workflow": true}` in the request body used to satisfy this
    # guard and hand the sender everything it exists to withhold. A plain user could
    # write {"state": "approved"} over their own draft and have it stick — no version
    # snapshot, no approved_by, no separation of duties. A sentinel survives
    # with_context inside the server and cannot be written in JSON.

    # When the work last changed hands. A tracking page wants to know how long something
    # has been sitting where it is — a draft nobody has touched for a fortnight and one
    # opened this morning read the same without it — and write_date cannot answer that,
    # because a recompute touches the row without the work having moved at all.
    state_since = fields.Datetime(
        "منذ", readonly=True, copy=False,
        help="متى انتقلت هذه الإفادة إلى حالتها الحالية.")

    return_ids = fields.One2many("azm.review.return", compute="_compute_returns",
                                 string="الأجزاء المُعادة")
    open_return_count = fields.Integer("أجزاء مُعادة", compute="_compute_returns")

    def _invalidate_returns(self):
        """Forget a cached count of returns, because one of them has just moved."""
        if self:
            self.invalidate_recordset(["return_ids", "open_return_count"])

    def _compute_returns(self):
        Return = self.env["azm.review.return"]
        for record in self:
            found = Return._open_for(record) if record.id else Return.browse()
            record.return_ids = found
            record.open_return_count = len(found)

    def action_return_parts(self, parts):
        """Send named parts back to be done again, each with the reason why.

        ``parts`` is a list of ``{"level", "id", "note"}``. The assessment goes back to
        its preparer, but only these parts are open: see azm.review.return.
        """
        self.ensure_one()
        if self.state != "review":
            raise UserError(_("Work is sent back from review."))
        if not (self.env.user.has_group("azm_operating_model.azm_group_reviewer")
                or self.env.user.has_group("azm_operating_model.azm_group_manager")):
            raise UserError(_("Only a reviewer sends work back."))
        if not parts:
            raise UserError(_("Say which part is coming back, and why."))
        financial = self._name == "azm.fin.assessment"
        allowed = {"module": "module_id", "topic": "topic_id", "requirement": "requirement_id"} \
            if financial else {"stage": "stage_id", "question": "question_id"}
        side = "fin_assessment_id" if financial else "proc_assessment_id"
        rows = []
        for part in parts:
            field = allowed.get(part.get("level"))
            if not field or not part.get("id"):
                raise UserError(_("A returned part must name what it is."))
            if not (part.get("note") or "").strip():
                raise UserError(_("A returned part carries the reason it came back."))
            rows.append({side: self.id, field: int(part["id"]),
                         "note": part["note"].strip(),
                         "reviewer_id": self.env.user.id,
                         "user_id": self._return_owner(part.get("level"), int(part["id"])).id})
        self.env["azm.review.return"].create(rows)
        self._workflow().write({"state": "draft"})
        self._notify_returned(rows)
        return True

    def _return_owner(self, level, part_id):
        """Who has to deal with a returned part: whoever was given it, else the preparer.

        Work is handed out per module and per stage, so a return on anything narrower
        is traced up to the part that was assigned before asking who holds it.
        """
        Assignment = self.env["azm.assignment"].sudo()
        if self._name == "azm.fin.assessment":
            owner_of = {
                "module": lambda: self.env["azm.fin.module"].browse(part_id),
                "topic": lambda: self.env["azm.fin.topic"].browse(part_id).module_id,
                "requirement": lambda: self.env["azm.fin.requirement"].browse(part_id).module_id,
            }
            module = owner_of[level]()
            found = Assignment.search([("fin_assessment_id", "=", self.id),
                                       ("module_id", "=", module.id)], limit=1)
        else:
            stage = (self.env["azm.stage"].browse(part_id) if level == "stage"
                     else self.env["azm.question"].browse(part_id).stage_id)
            found = Assignment.search([("proc_assessment_id", "=", self.id),
                                       ("stage_id", "=", stage.id)], limit=1)
        return found.user_ids[:1] or self.user_id

    def _notify_returned(self, rows):
        """Tell whoever must deal with it. Overridden where a model has its own wording."""
        return

    def _workflow(self):
        """This record, with the right to move itself along."""
        return self.with_context(**{self.AZM_WORKFLOW: AZM_WORKFLOW_TOKEN})

    def write(self, vals):
        if "state" in vals \
                and self.env.context.get(self.AZM_WORKFLOW) is not AZM_WORKFLOW_TOKEN \
                and not self.env.su:
            for record in self:
                if record.state != vals["state"]:
                    raise UserError(_(
                        "The state of an assessment is changed with its buttons — "
                        "send for review, approve, send back — not by writing to it."))
        if "state" in vals and "state_since" not in vals:
            moved = self.filtered(lambda record: record.state != vals["state"])
            if moved:
                # stamped on the ones that actually move, so re-saving a record in the
                # state it is already in does not look like fresh movement
                super(AzmReviewable, moved).write({"state_since": fields.Datetime.now()})
        return super().write(vals)

    # Who may be put on this, for the two Many2ones to choose from. Assigning somebody
    # who is not on the entity hands them work they cannot open — the record rules read
    # the entity's own list — so the choice is narrowed to people who could actually do
    # the job rather than to every user in the database.
    allowed_preparer_ids = fields.Many2many(
        "res.users", string="من يمكن أن يُعدّها", compute="_compute_allowed_people")
    allowed_reviewer_ids = fields.Many2many(
        "res.users", string="من يمكن أن يراجعها", compute="_compute_allowed_people")

    # the entity's membership is read below, so adding somebody to an entity has to
    # refresh the dropdown that offers them
    @api.depends("entity_id", "entity_id.user_ids")
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

    def _azm_outstanding(self):
        """Visible questions of the whole assessment still unanswered. Per model."""
        self.ensure_one()
        return 0

    def _azm_check_not_own_work(self):
        """Refuse to sign off work this person did themselves.

        Being the named preparer was the whole of the test, and it is not the whole of
        the question: a reviewer may also hold a part of the model through an
        assignment, answer it, and then approve the assessment that contains it. The
        separation of duties this check exists for is about who wrote the answers, so
        that is what it asks.
        """
        self.ensure_one()
        if self.env.is_superuser():
            return
        if self.user_id == self.env.user:
            raise UserError(_("The preparer of an assessment does not approve it "
                              "(separation of duties)."))
        holding = self.assignment_ids.filtered(lambda a: self.env.user in a.user_ids)
        if holding:
            raise UserError(_(
                "You hold %s of this model and answered it, so it is not yours to "
                "approve. Ask another reviewer.", holding[0].part_name or ""))

    def _azm_can_send(self):
        """Whether this can go for review now, and by this person.

        One answer for every way of asking — the workspace's last-step button, مساحتي's
        row, and the server that honours either. It is the preparer's act, only from
        draft, and only once the whole of it is answered: somebody who has finished
        their own share of a divided model has not finished the assessment.
        """
        self.ensure_one()
        if self.state != "draft":
            return False
        preparer = self.user_id or self.create_uid
        if preparer.id != self.env.uid \
                and not self.env.user.has_group("azm_operating_model.azm_group_manager"):
            return False
        returns = self.env["azm.review.return"]._open_for(self)
        if returns:
            # It came back for named parts, and nothing outside them can even be
            # written. Asking for the whole assessment here would strand work that was
            # sent back with a question unanswered somewhere else: unable to answer it,
            # unable to send what was fixed.
            return not self._azm_returned_outstanding(returns)
        return not self._azm_outstanding()

    def _azm_returned_outstanding(self, returns):
        """Unanswered questions inside the parts that came back. Per model."""
        self.ensure_one()
        return 0

    def _azm_review_header(self):
        """What a workspace needs to show the review side of the work.

        Whether this reader may send a part back, and what is already back with its
        note — so somebody fixing a return reads the reason beside the questions rather
        than having to remember it from another page.
        """
        self.ensure_one()
        reviewing = self.state == "review" and (
            self.env.user.has_group("azm_operating_model.azm_group_reviewer")
            or self.env.user.has_group("azm_operating_model.azm_group_manager"))
        returns = self.env["azm.review.return"]._open_for(self)
        return {
            "can_return": reviewing and self.user_id != self.env.user,
            "returns": [{
                "id": item.id,
                "level": item.level,
                "part": item.part_name,
                "note": item.note,
                "reviewer": item.reviewer_id.name,
                "module_id": item.module_id.id,
                "topic_id": item.topic_id.id,
                "requirement_id": item.requirement_id.id,
                "stage_id": item.stage_id.id,
                "question_id": item.question_id.id,
            } for item in returns],
        }

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
        # whatever came back has now been looked at again: sending it up closes the
        # returns, so the next reviewer sees the work rather than last round's notes
        self.env["azm.review.return"]._open_for(self).action_done()
        self._workflow().state = "review"
        self._notify_reviewers(reviewers, summary or self._review_summary())
        return reviewers
