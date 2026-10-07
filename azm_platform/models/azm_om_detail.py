"""What is behind a figure on an operating model page, without leaving it.

Every count on those pages used to be a door into the backend: clicking the questions
of a stage, the findings of a domain, the requirements of a module or the gaps of an
entity swapped the page for a list view, with its own filters, its own breadcrumb and
none of the context the reader had built up. Coming back meant rebuilding it.

So the rows are fetched and shown in place instead. One method serves all four kinds,
because they are the same question — *what is behind this number* — asked of four
models.
"""
from odoo import _, api, models
from odoo.exceptions import UserError

# How many rows a panel will show. Past this nobody is reading, they are searching, and
# the panel says so rather than quietly cutting the list off.
DETAIL_LIMIT = 300


class AzmDashboard(models.AbstractModel):
    _inherit = "azm.dashboard"

    # ------------------------------------------------------------------ the kinds
    def _detail_questions(self, stage_id=None, domain_key=None, **_kw):
        domain = []
        if stage_id:
            domain.append(("stage_id", "=", int(stage_id)))
        elif domain_key:
            domain.append(("azm_domain", "=", domain_key))
        groups = dict(self.env["azm.question"]._fields["group"].selection)
        types = dict(self.env["azm.question"]._fields["qtype"].selection)
        rows = []
        for q in self.env["azm.question"].search(domain, limit=DETAIL_LIMIT,
                                                 order="stage_sequence, sequence, id"):
            rows.append({
                "id": q.id, "code": q.code or "", "title": q.label or "",
                "meta": [m for m in (q.stage_id.name, groups.get(q.group), types.get(q.qtype)) if m],
                "detail": q.help_text or q.clause or "",
                "tone": "blue",
            })
        return {"title": _("Questions"), "rows": rows}

    def _detail_findings(self, assessment_ids=None, stage_id=None, domain_key=None,
                         only_open=False, finding_id=None, **_kw):
        domain = [("assessment_id", "in", [int(i) for i in assessment_ids or []])]
        if finding_id:
            # one finding, opened from a list that names it: the panel still goes
            # through the same door rather than the record form
            domain.append(("id", "=", int(finding_id)))
        if stage_id:
            domain.append(("stage_id", "=", int(stage_id)))
        elif domain_key:
            domain.append(("azm_domain", "=", domain_key))
        if only_open:
            domain.append(("state", "not in", ("closed", "accepted")))
        states = dict(self.env["azm.finding"]._fields["state"].selection)
        rows = []
        for f in self.env["azm.finding"].search(domain, limit=DETAIL_LIMIT,
                                                order="score desc, stage_sequence, id"):
            rows.append({
                "id": f.id, "code": f.code or "", "title": f.fact or "",
                "meta": [m for m in (f.entity_id.name, f.stage_id.name, states.get(f.state)) if m],
                # the two things somebody reading a finding wants next
                "detail": "\n".join(part for part in (
                    f.risk and _("Impact: %s", f.risk),
                    f.control and _("Control: %s", f.control),
                    f.owner_hint and _("Owner: %s", f.owner_hint)) if part),
                "score": f.score,
                "tone": "orange" if f.score and f.score >= 6 else "slate",
            })
        return {"title": _("Risk Register"), "rows": rows}

    def _detail_requirements(self, module_code=None, source=None, profile=None, **_kw):
        domain = []
        if module_code:
            domain.append(("module_id.code", "=", module_code))
        if source:
            domain.append(("source", "=", source))
        if profile:
            domain.append(("profile", "=", profile))
        rows = []
        for r in self.env["azm.fin.requirement"].search(
                domain, limit=DETAIL_LIMIT, order="module_sequence, sequence, id"):
            rows.append({
                "id": r.id, "code": r.code or "", "title": r.title or "",
                "meta": [m for m in (r.module_id.name, r.topic_id.name) if m],
                "detail": r.question or "",
                "tone": "teal",
            })
        return {"title": _("Requirements"), "rows": rows}

    def _detail_gaps(self, assessment_ids=None, module_code=None, **_kw):
        domain = [("assessment_id", "in", [int(i) for i in assessment_ids or []]),
                  ("applicable", "=", True), ("state", "in", ("partial", "unavailable"))]
        if module_code:
            domain.append(("module_id.code", "=", module_code))
        states = dict(self.env["azm.fin.answer"]._fields["state"].selection)
        rows = []
        for a in self.env["azm.fin.answer"].search(
                domain, limit=DETAIL_LIMIT, order="module_sequence, requirement_sequence, id"):
            rows.append({
                "id": a.id, "code": a.code or "", "title": a.title or "",
                "meta": [m for m in (a.entity_id.name, a.module_id.name, states.get(a.state)) if m],
                "detail": a.current or "",
                "tone": "orange" if a.state == "unavailable" else "purple",
            })
        return {"title": _("Gaps"), "rows": rows}

    # ------------------------------------------------------------------ the door
    @api.model
    def om_detail(self, kind, **scope):
        """The rows behind one figure on an operating model page.

        The scope arrives from a browser as named parts — a stage, a module code, the
        assessments in view — and the domain is built here from them. A domain itself
        is never taken from the client: it would turn one page's "show me this stage"
        into a way to read any table the reader's rules happen to allow.
        """
        kinds = {
            "questions": self._detail_questions,
            "findings": self._detail_findings,
            "requirements": self._detail_requirements,
            "gaps": self._detail_gaps,
        }
        if kind not in kinds:
            raise UserError(_("Unknown detail: %s", kind))
        out = kinds[kind](**scope)
        out["kind"] = kind
        # said rather than left for the reader to infer from a list that stops
        out["limited"] = len(out["rows"]) >= DETAIL_LIMIT
        out["limit"] = DETAIL_LIMIT
        return out
