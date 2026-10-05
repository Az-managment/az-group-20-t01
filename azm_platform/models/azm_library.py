"""The outputs library: every deliverable the group produces, in one place.

The trees read one model for one entity. This reads the other way round — one
deliverable across every entity — which is the question nobody could ask before:
*how many of our entities have a procurement policy, and which ones are missing it?*

A deliverable is the master artifact of the coding registry, so it appears once however
many entities hold a copy; what differs between them is the state of their copy, which
is what the coverage figure counts.
"""
from odoo import api, models

from .azm_coding import DOMAINS, LIFECYCLE_LABELS, TYPE_LABELS
from .azm_documents import FIN_ARTIFACTS, FIN_KIND_ARTIFACTS, MODULE_OUTPUTS
from .azm_proc_documents import PROC_ARTIFACTS, PROC_KIND_ARTIFACTS, PROC_OUTPUTS

# how a document's state reads in the library
STATES = {
    "done": ("جاهز", "Ready", "ok"),
    "pending": ("لم يُقرأ بعد", "Not read yet", "muted"),
    "empty": ("لا يوجد محتوى", "Nothing in it", "muted"),
    "error": ("تعذّر إصداره", "Failed", "bad"),
}
# the leaves are many and are browsed in the tree; the library leads with what people file
SHEET_TYPES = {"REQ"}
LIMIT = 300


class AzmDashboard(models.AbstractModel):
    _inherit = "azm.dashboard"

    @api.model
    def _library_tab(self, artifact):
        """Which output of its node a deliverable is — the registry keeps it in the ref,
        `azm.fin.module,12,rules`, rather than as a column."""
        parts = (artifact.ref or "").split(",")
        return parts[2] if len(parts) > 2 else ""

    @api.model
    def _library_lifecycle(self, artifact):
        """Which stage of CS → GR → TD … a deliverable of this kind speaks from."""
        tab = self._library_tab(artifact)
        if artifact.domain == "PUR":
            if tab in PROC_ARTIFACTS:
                return PROC_ARTIFACTS[tab][1]
            return PROC_KIND_ARTIFACTS.get("question", ("", "CS"))[1]
        if tab in FIN_ARTIFACTS:
            return FIN_ARTIFACTS[tab][1]
        return FIN_KIND_ARTIFACTS.get("requirement", ("", "CS"))[1]

    @api.model
    def _library_output_name(self, artifact):
        """What kind of output it is, in words: "السياسات والقواعد", "الإجراء" …"""
        tab = self._library_tab(artifact)
        if tab in MODULE_OUTPUTS:
            return MODULE_OUTPUTS[tab][1], MODULE_OUTPUTS[tab][2]
        if tab in PROC_OUTPUTS:
            return PROC_OUTPUTS[tab][1], PROC_OUTPUTS[tab][2]
        return TYPE_LABELS.get(artifact.atype, ("", ""))

    @api.model
    def _library_companies(self, company_ids=None):
        """The entities the coverage is counted over.

        Always a subset of the ones the user works in — asking for others narrows to
        nothing rather than widening, so the filter can never be used to look outward.
        The argument arrives from a browser, so anything that is not an entity id is
        dropped rather than trusted: a string, a bool (which is an int in Python and
        would otherwise pick company 1) or a dict would each crash or mislead.
        """
        companies = self._companies()
        if not company_ids:
            return companies
        if not isinstance(company_ids, (list, tuple, set)):
            company_ids = [company_ids]
        wanted = {c for c in company_ids if isinstance(c, int) and not isinstance(c, bool)}
        if not wanted:
            return companies
        return companies.filtered(lambda c: c.id in wanted) or companies

    @api.model
    def _library_domains(self):
        """The models the reader may see at all.

        The library lists both, so it has to ask about both: a reader who may open the
        procurement cycle but not the financial model is shown the cycle alone, rather
        than every financial deliverable's code and coverage because one of the two
        answered yes.
        """
        allowed = set()
        if self._fin_available():
            allowed.add("FIN")
        if self._om_available():
            allowed.add("PUR")
        return allowed

    @api.model
    def get_outputs_library(self, company_ids=None, atype=None, domain=None, stage=None,
                            node=None, query=None, sheets=False):
        """Every deliverable, with how far each entity has got with its copy.

        The filters narrow by entity, by model, by the node in the structure, by kind of
        output and by lifecycle stage. Sheets — the per-requirement and per-question
        pages — are left out unless asked for: there are nine hundred of them and the
        tree is where they are read.
        """
        allowed = self._library_domains()
        if not allowed:
            return {"available": False}
        env = self._env_all_companies()
        companies = self._library_companies(company_ids)

        # the shelf: every deliverable of a model this reader may see, minus the sheets
        # unless they were asked for
        artifacts = env["azm.artifact"].sudo().search([])
        shelf = [a for a in artifacts
                 if a.domain in allowed and (sheets or a.atype not in SHEET_TYPES)]
        # read once per artifact, not once per filter that happens to need it
        scoped = [(a, self._library_lifecycle(a), self._library_node(a)) for a in shelf]
        in_scope = {a.id for a in shelf}

        # how far each entity has got with its copy, counted per deliverable in one pass
        # rather than a query per row
        states = {}
        for artifact, state, count in self.env["azm.doc.publication"].sudo()._read_group(
                [("artifact_id", "!=", False), ("company_id", "in", companies.ids)],
                ["artifact_id", "state"], ["__count"]):
            states.setdefault(artifact.id, {})[state] = count
        counted = {a: c for a, c in states.items() if a in in_scope}

        needle = (query or "").strip().lower()

        def passes(entry, skip=None):
            """Whether a deliverable survives the filters — all of them for the rows,
            all but one for that one's own chips."""
            artifact, life, branch = entry
            if skip != "atype" and atype and artifact.atype != atype:
                return False
            if skip != "domain" and domain and artifact.domain != domain:
                return False
            if skip != "stage" and stage and life != stage:
                return False
            if skip != "node" and node and branch != node:
                return False
            if needle and needle not in (artifact.code or "").lower() \
                    and needle not in (artifact.node_name or "").lower():
                return False
            return True

        # ------------------------------------------------------------------ facets
        # A chip counts what picking it would actually return, which means counting
        # under the filters already on but not under its own: with the procurement
        # cycle showing, "POL · 30" promised every policy in the group and then handed
        # back the fourteen procurement ones.
        facets, domains_facet, stages_facet, nodes_facet = {}, {}, {}, {}
        for entry in scoped:
            artifact, life, branch = entry
            if passes(entry, skip="atype"):
                facets[artifact.atype] = facets.get(artifact.atype, 0) + 1
            if passes(entry, skip="domain"):
                domains_facet[artifact.domain] = domains_facet.get(artifact.domain, 0) + 1
            if passes(entry, skip="stage"):
                stages_facet[life] = stages_facet.get(life, 0) + 1
            if branch and passes(entry, skip="node"):
                nodes_facet.setdefault(branch, [artifact.domain, 0])[1] += 1

        # ------------------------------------------------------------------ the rows
        rows, total = [], 0
        for entry in scoped:
            if not passes(entry):
                continue
            artifact, life, branch = entry
            total += 1
            if len(rows) >= LIMIT:
                continue
            counts = states.get(artifact.id, {})
            ready = counts.get("done", 0)
            held = sum(counts.values())
            arabic, english = self._library_output_name(artifact)
            rows.append({
                "id": artifact.id,
                "code": artifact.code,
                "atype": artifact.atype,
                "type_label": TYPE_LABELS.get(artifact.atype, ("", ""))[0],
                "type_en": TYPE_LABELS.get(artifact.atype, ("", ""))[1],
                "stage": life,
                "stage_label": LIFECYCLE_LABELS.get(life, ("", ""))[0],
                "stage_en": LIFECYCLE_LABELS.get(life, ("", ""))[1],
                "domain": artifact.domain,
                "node": branch,
                "node_name": artifact.node_name or "",
                "label": arabic,
                "label_en": english,
                "ready": ready,
                "held": held,
                "entities": len(companies),
                "doc": self._library_doc_ref(artifact),
            })

        return {
            "available": True,
            "rows": rows,
            "total": total,
            "shown": len(rows),
            "limit": LIMIT,
            "filters": {"atype": atype or False, "domain": domain or False,
                        "stage": stage or False, "node": node or False,
                        "query": query or "", "sheets": bool(sheets),
                        "company_ids": sorted(companies.ids)},
            "entity_options": [{"id": c.id, "name": c.name} for c in self._companies()],
            "nodes": [{"key": key, "domain": value[0], "count": value[1]}
                      for key, value in sorted(nodes_facet.items())],
            "types": [{"key": key, "label": TYPE_LABELS[key][0], "en": TYPE_LABELS[key][1],
                       "count": facets[key]}
                      for key in TYPE_LABELS if facets.get(key)],
            "domains": [{"key": key, "label": arabic, "en": english,
                         "count": domains_facet.get(key, 0)}
                        for key, arabic, english in DOMAINS if domains_facet.get(key)],
            "stages": [{"key": key, "label": LIFECYCLE_LABELS[key][0],
                        "en": LIFECYCLE_LABELS[key][1], "count": stages_facet[key]}
                       for key in LIFECYCLE_LABELS if stages_facet.get(key)],
            "totals": {
                "deliverables": len(shelf),
                "copies": sum(sum(c.values()) for c in counted.values()),
                "ready": sum(c.get("done", 0) for c in counted.values()),
                "types": len({a.atype for a in shelf}),
                "entities": len(companies),
            },
        }

    @api.model
    def _library_node(self, artifact):
        """The branch of the structure a deliverable hangs on: FIN.GOV, PUR-REQ, or the
        model itself for the ones that belong to the whole of it."""
        name = artifact.node_name or ""
        head = name.split(" · ")[0].strip()
        if head.startswith("FIN.") or head.startswith("PUR-"):
            return head
        return "FIN" if artifact.domain == "FIN" else "PUR"

    @api.model
    def _library_doc_ref(self, artifact):
        """How the page asks for one entity's copy of this deliverable."""
        ref = (artifact.ref or "").split(",")
        model = ref[0] if ref else ""
        kinds = {"azm.fin.module": "module", "azm.stage": "stage",
                 "azm.fin.requirement": "requirement", "azm.question": "question"}
        if model in kinds and len(ref) >= 2:
            return {"kind": kinds[model], "id": int(ref[1]),
                    "tab": ref[2] if len(ref) > 2 else None, "label": artifact.code}
        # the model-wide ones: fin:summary, fin:book, pur:cycle, pur:cycle_book
        kind = (artifact.ref or "").split(":")[-1]
        return {"kind": kind, "label": artifact.code}

    @api.model
    def get_output_entities(self, artifact_id, company_ids=None):
        """Which entities hold this deliverable, and how far each has got.

        Reached straight from the browser like any other method on this model, so it
        asks the same question the shelf asks before answering: both reads below are
        sudo, and without this a user outside the operating-model group could post an
        artifact id and read back its registry code and every entity's state for it —
        the very records ir.access denies them.
        """
        allowed = self._library_domains()
        if not allowed:
            return {"available": False}
        artifact = self.env["azm.artifact"].sudo().browse(artifact_id).exists()
        if not artifact or artifact.domain not in allowed:
            return {"available": False}
        companies = self._library_companies(company_ids)
        by_company = {}
        for pub in self.env["azm.doc.publication"].sudo().search_read(
                [("artifact_id", "=", artifact.id), ("company_id", "in", companies.ids)],
                ["company_id", "state", "generated_on"]):
            by_company[pub["company_id"][0]] = pub
        doc = self._library_doc_ref(artifact)
        rows = []
        for company in companies:
            found = by_company.get(company.id)
            state = found["state"] if found else "pending"
            arabic, english, css = STATES.get(state, STATES["pending"])
            rows.append({
                "company_id": company.id,
                "name": company.name,
                "state": state,
                "state_label": arabic,
                "state_en": english,
                "css": css,
                "generated": str(found["generated_on"] or "") if found else "",
                "doc": {**doc, "company_id": company.id},
            })
        return {"available": True, "code": artifact.code, "rows": rows}
