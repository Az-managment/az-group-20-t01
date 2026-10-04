"""The procurement cycle as a tree: cycle › stage › group › question.

The tree is read from the catalogue (azm.stage → azm.question) and one entity's
assessment is hung off it, so a leaf's status is what that entity actually answered.
Visibility is decided by the very engine that drives the answer workspace — a question
the preparer never sees is drawn as "not asked here" rather than as a hole — and the
detail of a leaf shows its options, the answer given, the sentence the book will print
and the risks the catalogue watches on it.
"""
from odoo import api, models

from odoo.addons.azm_operating_model.models import engine
from odoo.addons.azm_platform.models.azm_proc_documents import (
    PROC_ARTIFACTS, PROC_OUTPUTS, PROC_TAB_ORDER)

OPEN_FINDING_STATES = ("candidate", "confirmed", "treatment")

# What a question looks like once an entity has (or has not) answered it.
PROC_STATUS = {
    "answered": ("مُجاب", "Answered", "ok"),
    "unsure": ("غير مؤكد", "Not certain", "warn"),
    "open": ("لم تتم الإجابة", "Not answered", "muted"),
    # drawn hollow, not grey: a question this entity is never asked must not read
    # like one it simply has not answered yet
    "hidden": ("لا يُسأل هنا", "Not asked here", "off"),
}


def _pct(part, whole):
    return round(100.0 * part / whole, 1) if whole else None


class AzmDashboard(models.AbstractModel):
    _inherit = "azm.dashboard"

    # ------------------------------------------------------------------ helpers
    @api.model
    def _proc_status(self, key):
        arabic, english, css = PROC_STATUS.get(key or "open", PROC_STATUS["open"])
        return {"key": key or "open", "label": arabic, "en": english, "css": css}

    @api.model
    def _proc_assessments(self, company):
        """The procurement assessments of one entity, newest first."""
        env = self._env_all_companies()
        entity = env["azm.entity"].search([("company_id", "=", company.id)], limit=1)
        if not entity:
            return env["azm.assessment"], entity
        found = env["azm.assessment"].search(
            [("entity_id", "=", entity.id), ("state", "!=", "archived")], order="version desc, id desc")
        return found, entity

    @api.model
    def _proc_pick(self, assessments, assessment_id=None):
        """The one read: the one asked for, else the approved one, else the newest."""
        if assessment_id:
            picked = assessments.filtered(lambda a: a.id == assessment_id)
            if picked:
                return picked[0]
        approved = assessments.filtered(lambda a: a.state == "approved")
        if approved:
            return approved[0]
        return assessments[:1]

    @api.model
    def _proc_rule_questions(self):
        """Which question each risk rule hangs on, so a finding can find its leaf."""
        return {r.code: r.question_id.id
                for r in self._env_all_companies()["azm.risk.rule"].search([])}

    # ------------------------------------------------------------------ the tree
    @api.model
    def get_proc_tree(self, company_id=None, assessment_id=None):
        """Cycle › stage › group › question, with every leaf's status for one entity."""
        if not self._om_available():
            return {"available": False}
        company = self._tree_company(company_id)
        if not company:
            return {"available": False}
        env = self._env_all_companies()

        assessments, entity = self._proc_assessments(company)
        assessment = self._proc_pick(assessments, assessment_id)
        # the documents of an entity are built from one assessment — the approved one,
        # else the newest. Looking at a different one is allowed, but then the documents
        # would say something else, so the tree stops offering them rather than lie.
        source = self._proc_pick(assessments)

        # findings already raised on this assessment, placed on the question they came from
        by_question = {}
        if assessment:
            rule_question = self._proc_rule_questions()
            for finding in env["azm.finding"].search([("assessment_id", "=", assessment.id),
                                                      ("state", "in", OPEN_FINDING_STATES),
                                                      ("triggered", "=", True)]):
                qid = rule_question.get(finding.code)
                if qid:
                    by_question[qid] = by_question.get(qid, 0) + 1

        # Every output of the cycle hangs on its stage, in the order the engine lists
        # them. The list comes from the catalogue, not from the documents already
        # published, so a stage shows all of its outputs from the first visit; the
        # document is resolved — and built, if this is the first time — when opened.
        outputs = [{"kind": "stage", "tab": tab,
                    "label": PROC_OUTPUTS[tab][1], "en": PROC_OUTPUTS[tab][2],
                    "atype": PROC_ARTIFACTS[tab][0], "stage": PROC_ARTIFACTS[tab][1]}
                   for tab in PROC_TAB_ORDER]

        nodes = []
        totals = {"questions": 0, "asked": 0, "answered": 0, "known": 0, "findings": 0}
        for stage in env["azm.stage"].search([]):
            questions = stage.question_ids.sorted(lambda q: (q.group or "0", q.sequence, q.id))
            if not questions:
                continue
            answers, visible = {}, None
            if assessment:
                sdict, qdicts, answers, _by_q = assessment._stage_payload(stage)
                visible = {q["id"] for q in engine.visible_questions(sdict, qdicts, answers)}
                lines = {a.question_id.id: a for a in assessment.answer_ids if a.stage_id == stage}
            else:
                lines = {}

            groups, seen = [], {}
            s_fig = {"questions": 0, "asked": 0, "answered": 0, "known": 0, "findings": 0}
            for q in questions:
                line = lines.get(q.id)
                if visible is not None and q.id not in visible:
                    state = "hidden"
                elif line and line.has_value:
                    state = "answered" if line.is_known else "unsure"
                else:
                    state = "open"
                risks = by_question.get(q.id, 0)
                item = {
                    "id": q.id,
                    "code": q.code,
                    "title": q.label,
                    "status": self._proc_status(state),
                    "flag": risks,
                    "doc": {"kind": "question", "id": q.id},
                }
                key = q.group or "0"
                if key not in seen:
                    seen[key] = {
                        "id": f"{stage.id}-{key}",
                        "code": "",
                        "name": engine.GROUP_TITLES.get(key, key),
                        "items": [], "count": 0, "known": 0,
                    }
                    groups.append(seen[key])
                node = seen[key]
                node["items"].append(item)
                node["count"] += 1
                s_fig["questions"] += 1
                s_fig["findings"] += risks
                if state != "hidden":
                    s_fig["asked"] += 1
                    if state != "open":
                        s_fig["answered"] += 1
                    if state == "answered":
                        node["known"] += 1
                        s_fig["known"] += 1
            for node in groups:
                node["completion"] = _pct(node["known"], node["count"])
                node["meta"] = node["count"]
            nodes.append({
                "id": stage.id,
                "code": f"PUR-{stage.code}",
                "name": stage.name,
                "domain": stage.azm_domain,
                "governance": stage.is_governance,
                "docs": [{**out, "id": stage.id} for out in outputs],
                "children": groups,
                "meta": s_fig["asked"] or s_fig["questions"],
                "gaps": s_fig["findings"],
                "completion": _pct(s_fig["answered"], s_fig["asked"]),
                **s_fig,
            })
            for k in totals:
                totals[k] += s_fig[k]
        # how many policies, procedures, authority maps … this entity's cycle holds.
        # Without an assessment the engine has nothing to write, so the outputs are
        # counted as empty rather than promised and then found blank.
        published = self._tree_published(company, ("question", "stage", "cycle"))
        families = [{
            "tab": tab, "label": PROC_OUTPUTS[tab][1], "en": PROC_OUTPUTS[tab][2],
            "offered": len(nodes),
            "empty": 0 if assessment else len(nodes),
            "ready": published.get(("stage", tab), {}).get("done", 0),
        } for tab in PROC_TAB_ORDER]
        families.append({
            "tab": "question", "label": "أوراق الأسئلة", "en": "Question sheets",
            "offered": totals["questions"], "empty": 0,
            "ready": published.get(("question", False), {}).get("done", 0),
        })
        families.append({
            "tab": "cycle", "label": "ملخص الدورة", "en": "Cycle summary",
            "offered": 1, "empty": 0 if assessment else 1,
            "ready": published.get(("cycle", False), {}).get("done", 0),
        })
        outputs = self._tree_outputs(families)

        totals["stages"] = len(nodes)
        totals["groups"] = sum(len(n["children"]) for n in nodes)
        totals["completion"] = _pct(totals["answered"], totals["asked"])
        totals["certainty"] = _pct(totals["known"], totals["answered"])

        a_labels = dict(env["azm.assessment"]._fields["state"]._description_selection(env))
        return {
            "available": True,
            "model": {"key": "procurement", "root": "PUR"},
            "company": {"id": company.id, "name": company.name},
            "entity_options": [{"id": c.id, "name": c.name} for c in self._companies()],
            "assessment": {
                "id": assessment.id, "name": assessment.name, "version": assessment.version,
                "state": assessment.state, "state_label": a_labels.get(assessment.state, assessment.state),
                "is_demo": assessment.is_demo, "entity": entity.name,
            } if assessment else None,
            "assessment_options": [{"id": a.id, "name": f"{a.name} · v{a.version}"} for a in assessments],
            "summary_doc": {"kind": "cycle", "label": "ملخص الدورة", "en": "Cycle summary"},
            "book_doc": {"kind": "cycle_book", "label": "الكتاب الكامل", "en": "Full book"},
            "documents": {
                "match": bool(assessment) and assessment == source,
                "from": source.name if source else "",
            },
            "totals": totals,
            "outputs": outputs,
            "nodes": nodes,
        }

    # ------------------------------------------------------------------ one question
    @api.model
    def get_proc_tree_node(self, question_id, company_id=None, assessment_id=None):
        """One question in full: what is asked, what this entity answered, what it risks."""
        if not self._om_available():
            return {"available": False}
        company = self._tree_company(company_id)
        if not company:
            return {"available": False}
        env = self._env_all_companies()
        question = env["azm.question"].browse(question_id)
        question.check_access("read")
        stage = question.stage_id

        assessments, _entity = self._proc_assessments(company)
        assessment = self._proc_pick(assessments, assessment_id)

        answers, visible, line = {}, None, None
        if assessment:
            sdict, qdicts, answers, by_q = assessment._stage_payload(stage)
            visible = {q["id"] for q in engine.visible_questions(sdict, qdicts, answers)}
            line = by_q.get(question.id)

        if visible is not None and question.id not in visible:
            state = "hidden"
        elif line and line.has_value:
            state = "answered" if line.is_known else "unsure"
        else:
            state = "open"

        qdict = question._engine_dict()
        value = answers.get(question.key)
        chosen = set()
        if line:
            chosen = set((line.option_ids | line.option_id).ids)

        # the risks the catalogue watches on this question, and whether they fired here
        rules = env["azm.risk.rule"].search([("question_id", "=", question.id)])
        raised = {}
        if assessment:
            for finding in env["azm.finding"].search([("assessment_id", "=", assessment.id),
                                                      ("code", "in", rules.mapped("code"))]):
                raised[finding.code] = finding
        f_labels = dict(env["azm.finding"]._fields["state"]._description_selection(env))
        risks = []
        for rule in rules:
            finding = raised.get(rule.code)
            risks.append({
                "code": rule.code,
                "trigger": rule.trigger_option_id.name,
                "fact": rule.fact,
                "risk": rule.risk,
                "control": rule.control,
                "owner": rule.owner_hint or "",
                "finding_id": finding.id if finding else False,
                "state": finding.state if finding else False,
                "state_label": f_labels.get(finding.state, "") if finding else "",
                "score": finding.score if finding else 0,
                "live": bool(finding and finding.triggered and finding.state in OPEN_FINDING_STATES),
            })

        return {
            "available": True,
            "id": question.id,
            "code": question.code,
            "title": question.label,
            "company": company.name,
            "doc": {"kind": "question", "id": question.id},
            "status": self._proc_status(state),
            "path": [
                ("الدورة", "دورة المشتريات"),
                ("المرحلة", f"PUR-{stage.code} · {stage.name}"),
                ("المجموعة", engine.GROUP_TITLES.get(question.group or "0", "")),
                ("السؤال", question.code or question.key),
            ],
            "stage": {
                "id": stage.id, "code": stage.code, "name": stage.name,
                "input": stage.input_desc or "", "output": stage.output_desc or "",
                "owner": stage.default_owner or "", "governance": stage.is_governance,
                "domain": stage.azm_domain,
            },
            "group": engine.GROUP_TITLES.get(question.group or "0", ""),
            "qtype": self._selection_label("azm.question", "qtype", question.qtype),
            "raci": self._selection_label("azm.question", "raci", question.raci) if question.raci else "",
            "is_common": question.is_common,
            "help": question.help_text or "",
            "clause": question.clause or "",
            "sentence": engine.sentence(qdict, answers),
            "conditional": bool(question.condition),
            "options": [{"id": o.id, "name": o.name, "kind": o.kind, "chosen": o.id in chosen}
                        for o in question.option_ids],
            "answer": {
                "value": engine.show(value) if value is not None else "",
                "known": engine.known(value),
                "note": (line.note or "") if line else "",
                "evidence": len(line.attachment_ids) if line else 0,
            },
            "risks": risks,
            "assessment": {
                "id": assessment.id, "name": assessment.name, "state": assessment.state,
                "is_demo": assessment.is_demo,
            } if assessment else None,
        }
