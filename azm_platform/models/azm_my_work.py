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
        return split.filtered(lambda a: self.env.uid in a.user_ids.ids)

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
    def _my_work_team(self, entities):
        """Who else is working the same models, and how far each has got.

        Not a department: the people this page is about are the ones holding the other
        parts of the same assessments, because they are who a person waits on and who
        waits on them.
        """
        Assignment = self.env.get("azm.assignment")
        if Assignment is None or not entities or not Assignment.has_access("read"):
            return []
        mine = Assignment.search([("entity_id", "in", entities.ids)])
        people = {}
        for part in mine:
            for user in part.user_ids:
                row = people.setdefault(user.id, {
                    "id": user.id, "name": user.name, "parts": 0,
                    "answered": 0, "total": 0, "entities": set(), "me": user.id == self.env.uid,
                })
                row["parts"] += 1
                row["answered"] += part.answered
                row["total"] += part.total
                row["entities"].add(part.entity_id.name)
        rows = []
        for row in people.values():
            left = max(row["total"] - row["answered"], 0)
            rows.append({**row,
                         "entities": sorted(row["entities"]),
                         "left": left,
                         "progress": round(100.0 * row["answered"] / row["total"]) if row["total"] else 0})
        # the most owed first: who needs help is the reason to look
        return sorted(rows, key=lambda person: (-person["left"], person["name"]))

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
    def open_my_workspace(self, res_model, assessment_id, focus=None):
        """Open the answering workspace, which is where the questions actually are.

        "Open the answers" used to land on the assessment's form, from which the reader
        had to find and press another button to reach the place they were going. Both
        models have their own workspace and both are opened the same way.
        """
        record = self._my_work_record(res_model, assessment_id)
        record.check_access("read")
        return record.action_open_workspace(focus=focus)

    @api.model
    def review_parts(self, res_model, assessment_id):
        """What a reviewer may send back, for the page to choose from.

        The workspace knows the part being looked at, so it can offer a button in
        place. مساحتي does not — a review row there is the whole assessment — so the
        parts are listed for it to pick from without opening the work first.
        """
        record = self._my_work_record(res_model, assessment_id)
        record.check_access("read")
        rows = []
        if res_model == "azm.fin.assessment":
            for module in record.answer_ids.module_id.sorted("sequence"):
                rows.append({"level": "module", "id": module.id, "depth": 0,
                             "name": f"FIN.{module.code} · {module.name}"})
                lines = record.answer_ids.filtered(lambda a, m=module: a.module_id == m)
                for topic in lines.topic_id.sorted("sequence"):
                    rows.append({"level": "topic", "id": topic.id, "depth": 1,
                                 "name": f"{topic.code or ''} · {topic.name or ''}".strip(" ·")})
                    for line in lines.filtered(lambda a, t=topic: a.topic_id == t):
                        rows.append({"level": "requirement", "id": line.requirement_id.id,
                                     "depth": 2, "name": f"{line.code} · {line.title}"})
        else:
            visible = record.answer_ids.filtered("is_visible")
            for stage in visible.stage_id.sorted("sequence"):
                rows.append({"level": "stage", "id": stage.id, "depth": 0,
                             "name": f"PUR-{stage.code} · {stage.name}"})
                for line in visible.filtered(lambda a, s=stage: a.stage_id == s):
                    rows.append({"level": "question", "id": line.question_id.id, "depth": 1,
                                 "name": f"{line.code} · {line.label}"})
        return {"parts": rows, "state": record.state}

    @api.model
    def return_review_parts(self, res_model, assessment_id, parts):
        """Send several named parts back at once, each with its reason."""
        record = self._my_work_record(res_model, assessment_id)
        record.check_access("write")
        record.action_return_parts(parts)
        return {"done": True, "state": record.state,
                "open_returns": record.open_return_count, "work": self.get_my_work()}

    @api.model
    def return_review_part(self, res_model, assessment_id, level, part_id, note):
        """Send one named part back to be done again, with the reason why.

        Reached from the review workspace. The record's own action does the checking —
        that this reader reviews rather than prepares, that the work is under review,
        that the part is named and the reason given — so this adds only the access
        check every entry point owes.
        """
        record = self._my_work_record(res_model, assessment_id)
        record.check_access("write")
        record.action_return_parts([{"level": level, "id": part_id, "note": note}])
        return {"done": True, "state": record.state,
                "open_returns": record.open_return_count}

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
    def _my_work_returned(self):
        """The parts a review sent back to this person, and why.

        These come first on the page: until they are dealt with, nothing else in that
        assessment can be answered, so a list of everything else would only say what is
        shut.
        """
        Return = self.env.get("azm.review.return")
        if Return is None or not Return.has_access("read"):
            return []
        rows = []
        for item in Return.search([("state", "=", "open"), ("user_id", "=", self.env.uid)]):
            assessment = item.fin_assessment_id or item.proc_assessment_id
            rows.append({
                "id": item.id,
                "part": item.part_name,
                "level": item.level,
                # which record the level names, so opening it can land on that part
                "part_id": (item.module_id.id or item.topic_id.id or item.requirement_id.id
                            or item.stage_id.id or item.question_id.id),
                "level_label": dict(Return._fields["level"].selection).get(item.level, ""),
                "note": item.note,
                "reviewer": item.reviewer_id.name,
                "since": str(item.create_date or ""),
                "entity": item.entity_id.name,
                "model_key": item.model_key,
                "res_model": assessment._name if assessment else "",
                "res_id": assessment.id if assessment else False,
                "state": assessment.state if assessment else "",
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
            "returned": self._my_work_returned(),
            "is_reviewer": self.env.user.has_group("azm_operating_model.azm_group_reviewer"),
            "team": self._my_work_team(entities),
            "around": self._my_work_around(companies),
            "totals": {
                "entities": len(entities),
                "left": sum(row["left"] for row in started),
                "progress": round(sum(row["progress"] for row in started) / len(started))
                            if started else 0,
                "mine": len([row for row in started if row["mine"]]),
            },
        }
