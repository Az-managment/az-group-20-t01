"""What is behind a figure on an operating model page, without leaving it.

Every count on those pages used to be a door into the backend: clicking the questions
of a stage, the findings of a domain, the requirements of a module or the gaps of an
entity swapped the page for a list view, with its own filters, its own breadcrumb and
none of the context the reader had built up. Coming back meant rebuilding it.

So the rows are fetched and shown in place instead. One method serves all four kinds,
because they are the same question — *what is behind this number* — asked of four
models.

Searching and paging are done here rather than in the page. The first version fetched
the first 300 rows and let the panel filter what it had been given, which meant a
catalogue of 396 questions could be searched only in its first 300: PUR-CLS is the last
stage, so every one of its 31 questions was outside the window and searching for it
found nothing at all. A search has to reach the whole catalogue to be a search.
"""
from odoo import _, api, models
from odoo.exceptions import UserError

from .azm_om_dashboard import OPEN_FINDING_STATES

# How many rows are sent at once. The panel asks for the next page when the reader
# wants it, and is always told how many there are in total.
DETAIL_PAGE = 60


class AzmDashboard(models.AbstractModel):
    _inherit = "azm.dashboard"

    # ------------------------------------------------------------------ the kinds
    # Each kind says what it searches, in what order, and how one record becomes a row.
    # The paging around them is written once, below.

    def _detail_spec_questions(self, stage_id=None, domain_key=None, **_kw):
        domain = []
        if stage_id:
            domain.append(("stage_id", "=", int(stage_id)))
        elif domain_key:
            domain.append(("azm_domain", "=", domain_key))
        groups = dict(self.env["azm.question"]._fields["group"].selection)
        types = dict(self.env["azm.question"]._fields["qtype"].selection)

        def row(q):
            return {
                "id": q.id, "code": q.code or "", "title": q.label or "",
                "meta": [m for m in (q.stage_id.name, groups.get(q.group), types.get(q.qtype)) if m],
                "detail": q.help_text or q.clause or "",
                "tone": "blue",
            }

        return {"model": "azm.question", "domain": domain, "title": _("Questions"),
                "order": "stage_sequence, sequence, id",
                "search": ["code", "label", "stage_id.code", "stage_id.name"], "row": row}

    def _detail_spec_findings(self, assessment_ids=None, stage_id=None, domain_key=None,
                              only_open=False, finding_id=None, **_kw):
        domain = [("assessment_id", "in", [int(i) for i in assessment_ids or []])]
        if finding_id:
            domain.append(("id", "=", int(finding_id)))
        if stage_id:
            domain.append(("stage_id", "=", int(stage_id)))
        elif domain_key:
            domain.append(("azm_domain", "=", domain_key))
        if only_open:
            # the states that mean open, named the way every other reader names them.
            # This filtered on "accepted", which azm.finding has never had, so the
            # panel counted dismissed findings as open and disagreed with the tile
            # that opened it.
            domain.append(("state", "in", OPEN_FINDING_STATES))
        states = dict(self.env["azm.finding"]._fields["state"].selection)

        def row(f):
            return {
                "id": f.id, "code": f.code or "", "title": f.fact or "",
                "meta": [m for m in (f.entity_id.name, f.stage_id.name, states.get(f.state)) if m],
                "detail": "\n".join(part for part in (
                    f.risk and _("Impact: %s", f.risk),
                    f.control and _("Control: %s", f.control),
                    f.owner_hint and _("Owner: %s", f.owner_hint)) if part),
                "score": f.score,
                "tone": "orange" if f.score and f.score >= 6 else "slate",
            }

        return {"model": "azm.finding", "domain": domain, "title": _("Risk Register"),
                "order": "score desc, stage_sequence, id",
                "search": ["code", "fact", "risk", "stage_id.name"], "row": row}

    def _detail_spec_requirements(self, module_code=None, source=None, profile=None, **_kw):
        domain = []
        if module_code:
            domain.append(("module_id.code", "=", module_code))
        if source:
            domain.append(("source", "=", source))
        if profile:
            domain.append(("profile", "=", profile))

        def row(r):
            return {
                "id": r.id, "code": r.code or "", "title": r.title or "",
                "meta": [m for m in (r.module_id.name, r.topic_id.name) if m],
                "detail": r.question or "",
                "tone": "teal",
            }

        return {"model": "azm.fin.requirement", "domain": domain, "title": _("Requirements"),
                "order": "module_sequence, sequence, id",
                "search": ["code", "title", "req_id", "module_id.code", "module_id.name"],
                "row": row}

    def _detail_spec_gaps(self, assessment_ids=None, module_code=None, **_kw):
        domain = [("assessment_id", "in", [int(i) for i in assessment_ids or []]),
                  ("applicable", "=", True), ("state", "in", ("partial", "unavailable"))]
        if module_code:
            domain.append(("module_id.code", "=", module_code))
        states = dict(self.env["azm.fin.answer"]._fields["state"].selection)

        def row(a):
            return {
                "id": a.id, "code": a.code or "", "title": a.title or "",
                "meta": [m for m in (a.entity_id.name, a.module_id.name, states.get(a.state)) if m],
                "detail": a.current or "",
                "tone": "orange" if a.state == "unavailable" else "purple",
            }

        return {"model": "azm.fin.answer", "domain": domain, "title": _("Gaps"),
                "order": "module_sequence, requirement_sequence, id",
                "search": ["code", "title", "module_id.code", "module_id.name",
                           "entity_id.name"],
                "row": row}

    # ------------------------------------------------------------------ the door
    @api.model
    def om_detail(self, kind, query="", offset=0, limit=None, **scope):
        """The rows behind one figure on an operating model page.

        The scope arrives from a browser as named parts — a stage, a module code, the
        assessments in view — and the domain is built here from them. A domain itself
        is never taken from the client: it would turn one page's "show me this stage"
        into a way to read any table the reader's rules happen to allow. The search
        text is the same: it is matched against the fields each kind names, never
        against a field the caller picks.
        """
        specs = {
            "questions": self._detail_spec_questions,
            "findings": self._detail_spec_findings,
            "requirements": self._detail_spec_requirements,
            "gaps": self._detail_spec_gaps,
        }
        if kind not in specs:
            raise UserError(_("Unknown detail: %s", kind))
        spec = specs[kind](**scope)

        domain = list(spec["domain"])
        words = (query or "").strip()
        if words:
            # every word must appear in one of the searched fields, so "CLS payment"
            # narrows rather than widening the way a flat OR over the lot would
            for word in words.split():
                fields = spec["search"]
                domain += ["|"] * (len(fields) - 1)
                domain += [(field, "ilike", word) for field in fields]

        Model = self.env[spec["model"]]
        total = Model.search_count(domain)
        page = max(1, min(int(limit or DETAIL_PAGE), 200))
        start = max(0, int(offset or 0))
        records = Model.search(domain, limit=page, offset=start, order=spec["order"])
        rows = [spec["row"](record) for record in records]
        return {
            "kind": kind,
            "title": spec["title"],
            "rows": rows,
            # said outright, so the panel can show "40 of 396" rather than leaving the
            # reader to wonder what it is not showing
            "total": total,
            "offset": start,
            "limit": page,
            "has_more": start + len(rows) < total,
            "query": words,
        }
