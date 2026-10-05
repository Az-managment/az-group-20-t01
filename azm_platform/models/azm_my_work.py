"""مساحتي · My work — what one person owes, and where their work stands.

The Home page is the group's cockpit: every entity, every model, the whole picture. It
is the right page for somebody who runs the group and the wrong one for somebody whose
job is to answer their own entity's questions — they opened it onto figures they cannot
act on, next to a technical menu holding the question catalogue.

This is the other page. One person, the entities they are assigned to, the models they
can answer, how far they have got, what is left, who has their work now, what it has
produced, and the projects and tasks around it. Everything it reads is already narrowed
by the record rules — azm.entity is readable only where ``user_ids`` contains the
reader — so a manager opening it sees their own work, not everybody's.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

# the two models somebody answers, and how each is reached
MODELS = [
    {
        "key": "procurement",
        "model": "azm.assessment",
        "label": "دورة المشتريات",
        "en": "Procurement cycle",
        "icon": "shopping_cart",
        "tone": "blue",
        "action": "azm_operating_model.azm_assessment_action",
    },
    {
        "key": "financial",
        "model": "azm.fin.assessment",
        "label": "النموذج المالي الموحد",
        "en": "Unified financial model",
        "icon": "payments",
        "tone": "green",
    "action": "azm_operating_model.azm_fin_assessment_action",
    },
]

# what the state of somebody's work means to them, rather than to the workflow
STANDING = {
    "draft": ("معك الآن", "With you now", "warn",
              "لم تُرسل بعد — أكمل الإجابات ثم أرسلها للمراجعة."),
    "review": ("مع المراجع", "With the reviewer", "info",
               "أُرسلت للمراجعة؛ لا يمكن تعديلها حتى تعود."),
    "approved": ("معتمدة", "Approved", "ok",
                 "اعتُمدت. أي تعديل يبدأ نسخة جديدة."),
    "archived": ("نسخة سابقة", "Superseded", "muted",
                 "حلّت محلها نسخة أحدث."),
}


class AzmDashboard(models.AbstractModel):
    _inherit = "azm.dashboard"

    @api.model
    def _my_work_standing(self, state, mine=True):
        """Where the work stands, said from where this person is standing.

        A draft is "with you now" to the person preparing it and "with the preparer" to
        anybody else looking at it — a reviewer named on an assessment was being told
        that unanswered work was with them, which is the one thing it was not.
        """
        arabic, english, css, note = STANDING.get(state, STANDING["draft"])
        if state == "draft" and not mine:
            arabic, english = "مع المُعد", "With the preparer"
            note = "لم تُرسل بعد؛ ما زالت مع من يُعدّها."
        return {"state": state, "label": arabic, "en": english, "css": css, "note": note}

    @api.model
    def _my_work_assessments(self, entities):
        """``{(entity id, model key): (assessment, is it theirs)}`` for every entity.

        Read one entity at a time, this was a search per entity per model and — worse —
        a progress compute per single record. That compute rebuilds the rules, the
        stages and the whole catalogue on every call and runs the findings engine over
        every stage; its own docstring says it is written to be called on a whole page
        at once. So the assessments are read in one search per model and the compute is
        triggered once for all of them.

        Theirs first — the one they are preparing or reviewing — and only then the
        entity's own latest, so the page leads with the work they are actually on
        rather than with whatever was created most recently.
        """
        found, uid = {}, self.env.uid
        for spec in MODELS:
            Model = self.env.get(spec["model"])
            if Model is None or not Model.has_access("read"):
                continue
            rows = Model.search([("entity_id", "in", entities.ids),
                                 ("state", "!=", "archived")],
                                order="version desc, id desc")
            rows.mapped("progress")   # one compute for the whole page, not one each
            for entity in entities:
                ours = rows.filtered(lambda r, e=entity: r.entity_id == e)
                mine = ours.filtered(
                    lambda r: r.user_id.id == uid or r.reviewer_id.id == uid)[:1]
                picked = mine or ours[:1]
                if picked:
                    found[(entity.id, spec["key"])] = (picked, bool(mine))
        return found

    @api.model
    def _my_work_models(self, entity, assessments):
        """Each model this person can answer for one entity, with how far it has got."""
        rows = []
        for spec in MODELS:
            found = assessments.get((entity.id, spec["key"]))
            row = {key: spec[key] for key in ("key", "label", "en", "icon", "tone", "action")}
            row["res_model"] = spec["model"]
            row.update({"entity_id": entity.id, "entity": entity.name})
            if not found:
                # nothing to answer yet is a state of its own, not zero progress
                row.update({"started": False, "mine": False, "assessment_id": False,
                            "progress": 0, "answered": 0, "total": 0, "left": 0,
                            "standing": None, "reviewer": "", "version": 0,
                            "can_send": False, "preparing": False, "parts": [],
                            "whole_total": 0, "whole_answered": 0, "whole_left": 0})
                rows.append(row)
                continue
            assessment, _named = found
            # Where the whole of it stands, whoever is looking. This is what decides
            # whether it can go for review, and once the model has been divided it is
            # not the same as what this person still owes.
            whole = self._my_work_whole(assessment, spec)
            preparing = assessment.user_id.id == self.env.uid

            parts = self._my_work_parts(assessment, spec)
            if parts:
                # the model has been split and some of it is this person's: the count
                # has to be theirs too, or "14 questions left" is somebody else's
                total = sum(part.total for part in parts)
                answered = sum(part.answered for part in parts)
                mine = True
            else:
                # the whole of it — either because it was never split, or because this
                # person is watching it rather than answering it. A reviewer named on an
                # assessment sees how it is going; it is not theirs to fill in or send.
                total, answered = whole["total"], whole["answered"]
                mine = preparing
            row.update({
                "started": True,
                "mine": mine,
                "assessment_id": assessment.id,
                "progress": round(assessment.progress),
                "answered": answered,
                "total": total,
                "left": max(total - answered, 0),
                "standing": self._my_work_standing(assessment.state, mine=mine),
                # Sending it on is the preparer's act, and only once the whole of it is
                # answered. Keyed off this person's own count it appeared as soon as
                # they had finished their share, and would have sent everybody else's
                # unanswered work for review along with it.
                "can_send": assessment._azm_can_send(),
                "preparing": preparing,
                "whole_total": whole["total"],
                "whole_answered": whole["answered"],
                "whole_left": whole["left"],
                "reviewer": assessment.reviewer_id.name or "",
                "version": assessment.version,
                "parts": [{"name": part.part_name, "answered": part.answered,
                           "total": part.total, "left": part.left,
                           "progress": round(part.progress)}
                          for part in (parts or [])],
            })
            rows.append(row)
        return rows

    @api.model
    def _my_work_whole(self, assessment, spec):
        """Where the whole assessment stands, however it has been divided up."""
        if spec["key"] == "financial":
            total, answered = assessment.question_count, assessment.answered_count
        else:
            total, answered = assessment.visible_count, assessment.answered_count
        return {"total": total, "answered": answered,
                "left": max(total - answered, 0)}

    @api.model
    def _my_work_parts(self, assessment, spec):
        """The parts of this assessment given to this person, or ``None``.

        ``None`` means the model was never split, so the whole of it is theirs — which
        is the old behaviour, kept exactly for an entity that does not want to divide
        the work. An empty list means it *was* split and none of it is theirs.
        """
        field = ("fin_assessment_id" if spec["key"] == "financial"
                 else "proc_assessment_id")
        Assignment = self.env["azm.assignment"]
        if not Assignment.has_access("read"):
            return None
        split = Assignment.search([(field, "=", assessment.id)])
        if not split:
            return None
        return split.filtered(lambda a: a.user_id.id == self.env.uid)

    @api.model
    def _my_work_deliverables(self, companies):
        """What this person's answers have produced, counted over their own entities."""
        Pub = self.env.get("azm.doc.publication")
        if Pub is None or not companies or not Pub.has_access("read"):
            return {"ready": 0, "total": 0, "pending": 0}
        counts = {}
        for state, count in Pub._read_group(
                [("company_id", "in", companies.ids), ("artifact_id", "!=", False)],
                ["state"], ["__count"]):
            counts[state] = count
        return {
            "ready": counts.get("done", 0),
            "pending": counts.get("pending", 0),
            "total": sum(counts.values()),
        }

    @api.model
    def _my_work_around(self, companies):
        """The work around the answering: the projects, the tasks, the people.

        Each is guarded on its own — an answerer who has no access to projects simply
        does not get that part of the page, rather than the page failing.
        """
        out = {"projects": [], "tasks": [], "team": [], "department": ""}
        uid, now = self.env.uid, fields.Datetime.now()

        Task = self.env.get("project.task")
        if Task is not None and Task.has_access("read"):
            for task in Task.search(
                    [("user_ids", "in", uid), ("is_closed", "=", False),
                     ("project_id", "!=", False)],
                    order="priority desc, date_deadline asc, id desc", limit=8):
                out["tasks"].append({
                    "id": task.id, "name": task.name,
                    "project": task.project_id.display_name,
                    "deadline": fields.Date.to_string(task.date_deadline.date())
                                if task.date_deadline else "",
                    "overdue": bool(task.date_deadline and task.date_deadline < now),
                })

        Project = self.env.get("project.project")
        if Project is not None and Project.has_access("read"):
            for project in Project.search(
                    ["|", ("user_id", "=", uid), ("message_partner_ids", "in",
                                                  self.env.user.partner_id.ids)],
                    order="id desc", limit=6):
                open_tasks = 0
                if Task is not None and Task.has_access("read"):
                    open_tasks = Task.search_count(
                        [("project_id", "=", project.id), ("is_closed", "=", False)])
                out["projects"].append({
                    "id": project.id, "name": project.display_name,
                    "entity": project.company_id.name or "",
                    "open_tasks": open_tasks,
                })

        Employee = self.env.get("hr.employee")
        if Employee is not None and Employee.has_access("read"):
            me = Employee.search([("user_id", "=", uid)], limit=1)
            if me and me.department_id:
                out["department"] = me.department_id.name
                for mate in Employee.search(
                        [("department_id", "=", me.department_id.id), ("id", "!=", me.id)],
                        order="name", limit=10):
                    out["team"].append({
                        "id": mate.id, "name": mate.name,
                        "job": mate.job_title or mate.job_id.name or "",
                    })
        return out

    @api.model
    def _my_work_record(self, res_model, record_id):
        """One of the two things this page deals in, checked rather than taken.

        The model name arrives from a browser: tested against the pair this page knows
        before it is used to reach the registry, so one page does not become a way to
        call anything.
        """
        if res_model not in {spec["model"] for spec in MODELS}:
            raise UserError(_("This is not something this page can open."))
        try:
            record_id = int(record_id)
        except (TypeError, ValueError):
            raise UserError(_("This assessment no longer exists.")) from None
        record = self.env[res_model].browse(record_id).exists()
        if not record:
            raise UserError(_("This assessment no longer exists."))
        return record

    @api.model
    def open_my_workspace(self, res_model, assessment_id):
        """Open the answering workspace, which is where the questions actually are.

        "Open the answers" used to land on the assessment's form, from which the reader
        had to find and press another button to reach the place they were going. Both
        models have their own workspace and both are opened the same way.
        """
        record = self._my_work_record(res_model, assessment_id)
        record.check_access("read")
        return record.action_open_workspace()

    @api.model
    def accept_my_review(self, res_model, assessment_id):
        """Accept the answers that were sent for review, and hand the page back."""
        record = self._my_work_record(res_model, assessment_id)
        record.check_access("write")
        record.action_approve()
        return {"done": True, "state": record.state, "work": self.get_my_work()}

    @api.model
    def return_my_review(self, res_model, assessment_id):
        """Send it back for more work, rather than accepting it."""
        record = self._my_work_record(res_model, assessment_id)
        record.check_access("write")
        if record.state != "review":
            raise UserError(_("Only work that is under review can be sent back."))
        record.action_back_to_draft()
        preparer = record.user_id or record.create_uid
        if preparer:
            # they are not watching this page; put it on their list
            record.sudo().activity_schedule(
                "mail.mail_activity_data_todo", user_id=preparer.id,
                summary=_("Your assessment was sent back for more work"))
        return {"done": True, "state": record.state, "work": self.get_my_work()}

    @api.model
    def submit_my_work(self, res_model, assessment_id):
        """Send one assessment for review, and hand back the page as it now stands.

        The model is checked against the two this page offers rather than taken as
        given: this is reached from a browser, and a method name plus a model name from
        the client is how one page becomes a way to call anything.
        """
        record = self._my_work_record(res_model, assessment_id)
        # Said here rather than left to action_submit, which quietly skips anything not
        # in draft: the page would have reported "sent for review" over work that had
        # not moved, because nothing came back to say otherwise.
        if record.state != "draft":
            raise UserError(_("This has already been sent; it is not yours to send again."))
        # The pages offer this to the preparer alone and only when the whole of it is
        # answered, but a page is not the control. Said here too, in words, because what
        # used to surface was a bare access error in answer to a reasonable act.
        preparer = record.user_id or record.create_uid
        if preparer.id != self.env.uid \
                and not self.env.user.has_group("azm_operating_model.azm_group_manager"):
            raise UserError(_(
                "Your part is done, but sending the assessment on is %s's to do.",
                preparer.name))
        outstanding = record._azm_outstanding()
        if outstanding:
            raise UserError(_(
                "%s questions have not been answered yet. The assessment goes for "
                "review once all of it is answered.", outstanding))
        # the record rules decide whether this person may touch it
        record.check_access("write")
        reviewers = record._reviewers()
        record.action_submit()
        return {
            "sent": True,
            "reviewers": sorted(reviewers.mapped("name")) if reviewers else [],
            "work": self.get_my_work(),
        }

    @api.model
    def _my_work_reviews(self):
        """Work other people have sent for review that this person is to look at.

        Submitting names no one by default, so this is not "assessments where I am the
        named reviewer" — it is everything under review on an entity I am a reviewer of.
        The record rules say the same thing, so this list and what the reader may open
        cannot drift apart.
        """
        if not self.env.user.has_group("azm_operating_model.azm_group_reviewer"):
            return []
        rows = []
        for spec in MODELS:
            Model = self.env.get(spec["model"])
            if Model is None or not Model.has_access("read"):
                continue
            for found in Model.search([("state", "=", "review")],
                                      order="write_date desc", limit=50):
                if found.user_id == self.env.user:
                    continue   # you do not review your own work
                rows.append({
                    "id": found.id,
                    "res_model": spec["model"],
                    "key": spec["key"],
                    "model_label": spec["label"],
                    "model_en": spec["en"],
                    "icon": spec["icon"],
                    "tone": spec["tone"],
                    "entity": found.entity_id.name,
                    "preparer": (found.user_id or found.create_uid).name,
                    "mine": found.reviewer_id == self.env.user,
                    "version": found.version,
                    "progress": round(found.progress),
                    "since": fields.Date.to_string(found.write_date.date())
                             if found.write_date else "",
                })
        return rows

    @api.model
    def get_my_work(self):
        """The whole page: whose it is, what they owe, and what it has produced."""
        Entity = self.env.get("azm.entity")
        if Entity is None or not Entity.has_access("read"):
            return {"available": False}
        # the record rule narrows this to the entities the reader is assigned to
        entities = Entity.search([], order="sequence, id")
        companies = entities.company_id.filtered(lambda c: c.id in self.env.companies.ids)

        assessments = self._my_work_assessments(entities)
        models_rows = []
        for entity in entities:
            models_rows.extend(self._my_work_models(entity, assessments))
        started = [row for row in models_rows if row["started"]]

        return {
            "available": True,
            "user": {"id": self.env.uid, "name": self.env.user.name},
            "entities": [{"id": e.id, "name": e.name, "code": e.code,
                          "company_id": e.company_id.id} for e in entities],
            "models": models_rows,
            "reviews": self._my_work_reviews(),
            "is_reviewer": self.env.user.has_group("azm_operating_model.azm_group_reviewer"),
            "deliverables": self._my_work_deliverables(companies),
            "around": self._my_work_around(companies),
            "totals": {
                "entities": len(entities),
                "left": sum(row["left"] for row in started),
                "progress": round(sum(row["progress"] for row in started) / len(started))
                            if started else 0,
                "mine": len([row for row in started if row["mine"]]),
            },
        }
