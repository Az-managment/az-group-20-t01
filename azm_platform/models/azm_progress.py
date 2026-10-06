"""التقدّم · Progress — who is doing what, and how far they have got.

مساحتي is one person's own page. This is the other half of the same subject and it is
not that: an administrator does not want their own work, they want everybody's. Who
prepares each model for each entity, who reviews it, where it stands, how much is
answered, and — where the work has been divided — which part belongs to whom and how
far each of them has got.

Read through the record rules like everything else, so an administrator sees the
entities they have, not every entity there is.
"""
from odoo import api, fields, models

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
                        # a shared part is shared work: each person is credited with
                        # what they wrote rather than with the whole part
                        written = {person["id"]: person["answers"] for person in people_on_it}
                        for who in part.user_ids:
                            note(who, "answers", written.get(who.id, 0),
                                 part.total if len(part.user_ids) == 1 else 0,
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
