"""التقدّم · Progress — who is doing what, and how far they have got.

مساحتي is one person's own page. This is the other half of the same subject and it is
not that: an administrator does not want their own work, they want everybody's. Who
prepares each model for each entity, who reviews it, where it stands, how much is
answered, and — where the work has been divided — which part belongs to whom and how
far each of them has got.

Read through the record rules like everything else, so an administrator sees the
entities they have, not every entity there is.
"""
from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

from .azm_my_work import MODELS

# How long work may sit in one state before the page says so. A week is a reporting
# cycle: anything that has not moved in one is something somebody has stopped chasing.
STALE_AFTER = 7


class AzmDashboard(models.AbstractModel):
    _inherit = "azm.dashboard"

    @api.model
    def _progress_person(self, user, bucket):
        return {
            "id": user.id,
            "name": user.name,
            "parts": bucket["parts"],
            "answered": bucket["answered"],
            "total": bucket["total"],
            "left": max(bucket["total"] - bucket["answered"], 0),
            "progress": round(100.0 * bucket["answered"] / bucket["total"])
                        if bucket["total"] else 0,
            "entities": sorted(bucket["entities"]),
            "roles": sorted(bucket["roles"]),
            # what else they are on, so somebody who answers nothing is not written up
            # as having nothing: a reviewer's work is the reviewing
            "preparing": bucket["preparing"],
            "reviewing": bucket["reviewing"],
            "awaiting": bucket["awaiting"],
            "outstanding": bucket["outstanding"],
        }

    @api.model
    def get_progress(self):
        """Every model of every entity in reach, with the people on it."""
        Entity = self.env.get("azm.entity")
        if Entity is None or not Entity.has_access("read"):
            return {"available": False}
        entities = Entity.search([], order="sequence, id")
        Assignment = self.env["azm.assignment"]
        may_see_parts = Assignment.has_access("read")

        rows, people = [], {}

        def note(user, role, answered=0, total=0, entity="", part=False, waiting=False,
                 outstanding=0):
            if not user:
                return
            bucket = people.setdefault(user.id, {
                "user": user, "parts": 0, "answered": 0, "total": 0,
                "entities": set(), "roles": set(),
                "preparing": 0, "reviewing": 0, "awaiting": 0, "outstanding": 0})
            bucket["roles"].add(role)
            if entity:
                bucket["entities"].add(entity)
            if part:
                bucket["parts"] += 1
                bucket["answered"] += answered
                bucket["total"] += total
            elif role == "prepares":
                bucket["preparing"] += 1
                bucket["outstanding"] += outstanding
            elif role == "reviews":
                bucket["reviewing"] += 1
                if waiting:
                    bucket["awaiting"] += 1

        for spec in MODELS:
            Model = self.env.get(spec["model"])
            if Model is None or not Model.has_access("read"):
                continue
            found = Model.search([("entity_id", "in", entities.ids),
                                  ("state", "!=", "archived")],
                                 order="version desc, id desc")
            found.mapped("progress")   # one compute for the whole page
            # Every live one, not the newest per entity. An entity holds a procurement
            # assessment per kind and scenario — أصناف/عاجل is not a newer version of
            # أصناف/قياسي — and keeping one hid the others: an approved assessment
            # disappeared behind a draft of a different kind. Superseded versions are
            # already out, because action_new_version archives them.
            for assessment in found:
                if spec["key"] == "financial":
                    total, answered = assessment.question_count, assessment.answered_count
                else:
                    total, answered = assessment.visible_count, assessment.answered_count
                # Nobody's own work is on this page, so nothing here is "with you now":
                # a draft is with whoever prepares it, and this reads it from where
                # somebody tracking it stands. The chip says which stage; the line under
                # it names the people.
                standing = self._my_work_standing(assessment.state, mine=False)
                parts = []
                if may_see_parts:
                    field = ("fin_assessment_id" if spec["key"] == "financial"
                             else "proc_assessment_id")
                    for part in Assignment.search([(field, "=", assessment.id)]):
                        people_on_it = part._answered_by()
                        parts.append({
                            # keyed on by the page: two parts of one model can carry
                            # the same name, and two equal keys blank the render
                            "id": part.id,
                            "name": part.part_name,
                            "level": "topic" if part.topic_id else (
                                "module" if part.module_id else "stage"),
                            "user": "، ".join(part.user_ids.mapped("name")),
                            "user_ids": part.user_ids.ids,
                            # what each of them has actually written
                            "people": people_on_it,
                            "answered": part.answered,
                            "total": part.total,
                            "left": part.left,
                            "progress": round(part.progress),
                        })
                        # A shared part is shared work: each person is credited with
                        # what they wrote rather than with the whole part. They are
                        # measured against a share of it, not against nothing — the
                        # total used to be zeroed the moment a part had two people on
                        # it, so both of them read 0% however much they had written,
                        # and the page's "most owed first" order put them last.
                        written = {person["id"]: person["answers"] for person in people_on_it}
                        holders = len(part.user_ids) or 1
                        share = part.total // holders
                        for index, who in enumerate(part.user_ids):
                            # the division rarely comes out even; the remainder goes to
                            # the first holder rather than being dropped
                            mine = share + (part.total % holders if index == 0 else 0)
                            note(who, "answers", written.get(who.id, 0), mine,
                                 assessment.entity_id.name, part=True)
                preparer = assessment.user_id or assessment.create_uid
                # only what is still owed: an assessment under review or approved is no
                # longer waiting on the person who prepared it
                note(preparer, "prepares", entity=assessment.entity_id.name,
                     outstanding=max(total - answered, 0)
                     if assessment.state == "draft" else 0)
                note(assessment.reviewer_id, "reviews",
                     entity=assessment.entity_id.name,
                     waiting=assessment.state == "review")
                since = assessment.state_since
                # how long it has sat where it is: the figure a tracking page is read
                # for, because a draft untouched for a fortnight and one opened this
                # morning say the same thing without it
                waiting = (fields.Datetime.now() - since).days if since else None
                rows.append({
                    "id": assessment.id,
                    "ref": assessment.name,
                    "since": str(since or ""),
                    "waiting": waiting,
                    # settled work is not late, however long it has been settled
                    "stalled": bool(waiting is not None and waiting >= STALE_AFTER
                                    and assessment.state != "approved"),
                    "gaps": (assessment.gap_count if spec["key"] == "financial"
                             else assessment.finding_count),
                    "res_model": spec["model"],
                    "key": spec["key"],
                    "label": spec["label"],
                    "en": spec["en"],
                    "icon": spec["icon"],
                    "tone": spec["tone"],
                    "entity": assessment.entity_id.name,
                    "entity_id": assessment.entity_id.id,
                    "preparer": preparer.name or "",
                    "reviewer": assessment.reviewer_id.name or "",
                    "state": assessment.state,
                    "standing": standing["label"],
                    "standing_en": standing["en"],
                    "css": standing["css"],
                    "progress": round(assessment.progress),
                    "answered": answered,
                    "total": total,
                    "left": max(total - answered, 0),
                    "version": assessment.version,
                    "parts": parts,
                })

        ranked = sorted((self._progress_person(b["user"], b) for b in people.values()),
                        key=lambda p: (-p["left"], -p["outstanding"], -p["awaiting"],
                                       p["name"]))
        return {
            "available": True,
            # whether this reader may hand parts out at all: the page offers the form
            # only to somebody who could save it
            "can_assign": Assignment.has_access("write"),
            "rows": sorted(rows, key=lambda r: (r["entity"], r["key"], r["ref"])),
            "people": ranked,
            "totals": {
                "entities": len(entities),
                "models": len(rows),
                "people": len(ranked),
                "left": sum(row["left"] for row in rows),
                "in_review": len([r for r in rows if r["state"] == "review"]),
                "approved": len([r for r in rows if r["state"] == "approved"]),
                "progress": round(sum(r["progress"] for r in rows) / len(rows))
                            if rows else 0,
                "stalled": len([r for r in rows if r["stalled"]]),
                "gaps": sum(r["gaps"] for r in rows),
            },
        }

    # ------------------------------------------------------------- assigning parts
    # Giving a part to somebody used to mean leaving this page for the backend list,
    # where the reader had to rebuild from scratch the thing they were just looking at:
    # which entity, which model, which parts are already held. These three methods let
    # the page ask the same questions it already displays, and answer them in place.

    @api.model
    def _assign_part_row(self, level, part_id, name, depth, held):
        row = held.get((level, part_id))
        return {
            "level": level, "id": part_id, "name": name, "depth": depth,
            "assignment_id": row.id if row else False,
            "user_ids": row.user_ids.ids if row else [],
            "users": row.user_ids.mapped("name") if row else [],
            "answered": row.answered if row else 0,
            "total": row.total if row else 0,
            "note": (row.note or "") if row else "",
        }

    @api.model
    def _assign_held(self, record):
        """Every part of this assessment that is already in somebody's hands."""
        field = ("fin_assessment_id" if record._name == "azm.fin.assessment"
                 else "proc_assessment_id")
        held = {}
        for row in self.env["azm.assignment"].search([(field, "=", record.id)]):
            if row.topic_id:
                held[("topic", row.topic_id.id)] = row
            elif row.module_id:
                held[("module", row.module_id.id)] = row
            elif row.stage_id:
                held[("stage", row.stage_id.id)] = row
        return held

    @api.model
    def assignable_parts(self, res_model, assessment_id):
        """The parts of one model, each saying who holds it, and who may be given it.

        The same broad-to-narrow shape the rest of the system uses: a module, then the
        topics under it, either of which can be handed out; or a stage, which cannot be
        divided further.
        """
        record = self._my_work_record(res_model, assessment_id)
        record.check_access("read")
        self.env["azm.assignment"].check_access("read")
        held = self._assign_held(record)
        parts = []
        if res_model == "azm.fin.assessment":
            for module in record.answer_ids.module_id.sorted("sequence"):
                parts.append(self._assign_part_row(
                    "module", module.id, f"FIN.{module.code} · {module.name}", 0, held))
                lines = record.answer_ids.filtered(lambda a, m=module: a.module_id == m)
                for topic in lines.topic_id.sorted("sequence"):
                    label = f"{topic.code or ''} · {topic.name or ''}".strip(" ·")
                    parts.append(self._assign_part_row("topic", topic.id, label, 1, held))
        else:
            visible = record.answer_ids.filtered("is_visible")
            for stage in visible.stage_id.sorted("sequence"):
                parts.append(self._assign_part_row(
                    "stage", stage.id, f"{stage.code} · {stage.name}", 0, held))
        # who may be given a part: the people on this entity, plus anybody already
        # holding one — somebody taken off the entity still shows on what they hold,
        # rather than vanishing from the form that is supposed to move it off them
        candidates = record.entity_id.user_ids.filtered(lambda u: not u.share)
        for row in held.values():
            candidates |= row.user_ids
        return {
            "parts": parts,
            "can_write": self.env["azm.assignment"].has_access("write"),
            "candidates": [{"id": u.id, "name": u.name} for u in candidates.sorted("name")],
        }

    @api.model
    def set_part_assignment(self, res_model, assessment_id, level, part_id, user_ids):
        """Give one part to these people — or, with nobody named, take it back.

        A part nobody holds is not an empty assignment row but no row at all: that is
        what the rest of the system reads as "this stays with whoever prepares the
        assessment", so clearing one has to remove it rather than blank it.
        """
        record = self._my_work_record(res_model, assessment_id)
        record.check_access("read")
        Assignment = self.env["azm.assignment"]
        # the part must be one of this assessment's own: a level and an id arrive from
        # a browser, and without this a stray id would hand out somebody else's module
        allowed = {(p["level"], p["id"]) for p in
                   self.assignable_parts(res_model, assessment_id)["parts"]}
        if (level, int(part_id)) not in allowed:
            raise UserError(_("That part does not belong to this model."))
        people = self.env["res.users"].browse([int(uid) for uid in user_ids or []]).exists()
        if any(user.share for user in people):
            raise UserError(_("A portal user cannot be given a part."))
        row = self._assign_held(record).get((level, int(part_id)))
        if not people:
            if row:
                row.unlink()
            return {"done": True, "progress": self.get_progress()}
        if row:
            row.write({"user_ids": [Command.set(people.ids)]})
        else:
            field = ("fin_assessment_id" if res_model == "azm.fin.assessment"
                     else "proc_assessment_id")
            key = {"module": "module_id", "topic": "topic_id", "stage": "stage_id"}[level]
            Assignment.create({
                field: record.id, key: int(part_id),
                "user_ids": [Command.set(people.ids)],
            })
        return {"done": True, "progress": self.get_progress()}
