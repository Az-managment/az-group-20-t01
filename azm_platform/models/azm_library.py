"""The outputs library: every deliverable the group produces, in one place.

The trees read one model for one entity. This reads the other way round — one
deliverable across every entity — which is the question nobody could ask before:
*how many of our entities have a procurement policy, and which ones are missing it?*

A deliverable is the master artifact of the coding registry, so it appears once however
many entities hold a copy; what differs between them is the state of their copy, which
is what the coverage figure counts.
"""
from odoo import _, api, models
from odoo.exceptions import UserError

from .azm_coding import DOMAINS, LIFECYCLE_LABELS, TYPE_LABELS, WHOLE_MODEL, copy_code
from .azm_documents import FIN_ARTIFACTS, FIN_KIND_ARTIFACTS, MODULE_OUTPUTS
from .azm_proc_documents import PROC_ARTIFACTS, PROC_KIND_ARTIFACTS, PROC_OUTPUTS

# how a document's state reads in the library
STATES = {
    "done": ("جاهز", "Ready", "ok"),
    "pending": ("لم يُقرأ بعد", "Not read yet", "muted"),
    "empty": ("لا يوجد محتوى", "Nothing in it", "muted"),
    "error": ("تعذّر إصداره", "Failed", "bad"),
}
# Where the answers behind a copy stand. A deliverable built from a draft is a draft
# deliverable however finished the file looks; one built from an approved assessment has
# been issued. "بلا مصدر" is a document nobody has opened yet, so nothing has been built
# from anything.
APPROVALS = [
    ("approved", "معتمدة", "Approved"),
    ("review", "تحت المراجعة", "In review"),
    ("draft", "مسودة", "Draft"),
    ("archived", "نسخة سابقة", "Superseded"),
]

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
        """What this deliverable is called.

        A module's gap register is named by the output it is; an individual policy is
        named by the policy it is. Falling back to the kind — "سياسة" against every one
        of a hundred and twenty-three policies — tells the reader nothing about which.
        """
        tab = self._library_tab(artifact)
        if tab in MODULE_OUTPUTS:
            return MODULE_OUTPUTS[tab][1], MODULE_OUTPUTS[tab][2]
        if tab in PROC_OUTPUTS:
            return PROC_OUTPUTS[tab][1], PROC_OUTPUTS[tab][2]
        # the node name carries "FIN.GOV · الفترات المالية"; the title is what names it
        title = (artifact.node_name or "").split(" · ")[-1].strip()
        kind = TYPE_LABELS.get(artifact.atype, ("", ""))
        return (title or kind[0]), kind[1]

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
                            node=None, query=None, sheets=False, approval=None):
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

        # How far each entity has got with its copy, and where the answers behind it
        # stand, counted per deliverable in one pass rather than a query per row.
        # Narrowing by approval counts only the copies issued from that kind of
        # assessment, so the coverage bar answers "how many have it approved" rather
        # than "how many have a file".
        states, approvals = {}, {}
        for artifact, state, source, count in self.env["azm.doc.publication"].sudo()._read_group(
                [("artifact_id", "!=", False), ("company_id", "in", companies.ids)],
                ["artifact_id", "state", "source_state"], ["__count"]):
            if artifact.id in in_scope:
                approvals[source or False] = approvals.get(source or False, 0) + count
            if approval and (source or False) != approval:
                continue
            bucket = states.setdefault(artifact.id, {})
            bucket[state] = bucket.get(state, 0) + count
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
        # A row is one artifact however many entities hold it, so it carries the master
        # code. Narrowed to a single entity, the row *is* that entity's copy and names
        # it the way that entity's document does.
        holder = self._library_holder(companies)
        rows, total = [], 0
        for entry in scoped:
            if not passes(entry):
                continue
            artifact, life, branch = entry
            counts = states.get(artifact.id, {})
            if approval and not counts:
                continue   # nobody holds a copy of this one in that state
            total += 1
            if len(rows) >= LIMIT:
                continue
            ready = counts.get("done", 0)
            held = sum(counts.values())
            arabic, english = self._library_output_name(artifact)
            rows.append({
                "id": artifact.id,
                "code": copy_code(artifact.code, holder),
                "master_code": artifact.code,
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
                "tree": self._library_branch(artifact),
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
                        "approval": approval or False,
                        "company_ids": sorted(companies.ids)},
            "approvals": [{"key": key, "label": arabic, "en": english,
                           "count": approvals.get(key, 0)}
                          for key, arabic, english in APPROVALS
                          if approvals.get(key)],
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
                "approved": approvals.get("approved", 0),
                "unissued": sum(approvals.get(key, 0) for key in ("draft", False)),
                "types": len({a.atype for a in shelf}),
                "entities": len(companies),
            },
        }

    @api.model
    def _library_node(self, artifact):
        """The branch of the structure a deliverable hangs on: FIN.GOV, PUR-REQ, or the
        model itself for the ones that belong to the whole of it.

        Read off the artifact's own node rather than parsed back out of its name, now
        that the node is part of what it is and of what it is called.
        """
        node = (artifact.node or "").strip()
        if not node or node == WHOLE_MODEL:
            return artifact.domain
        return f"FIN.{node}" if artifact.domain == "FIN" else f"PUR-{node}"

    @api.model
    def _library_branch(self, artifact):
        """``(node id, output)`` — the branch of the tree this deliverable hangs on.

        Not the same as how the document is asked for: a requirement's policy is opened
        as that requirement, and found on the tree under its *module*. Handing the tree
        the requirement's id would send it looking for a branch that is a leaf.
        """
        ref = (artifact.ref or "").split(",")
        model = ref[0] if ref else ""
        if len(ref) < 2:
            return {}
        rid, tab = int(ref[1]), (ref[2] if len(ref) > 2 else None)
        if model == "azm.fin.requirement":
            req = self.env["azm.fin.requirement"].sudo().browse(rid).exists()
            return {"node_id": req.module_id.id, "family": tab} if req else {}
        if model == "azm.question":
            question = self.env["azm.question"].sudo().browse(rid).exists()
            return {"node_id": question.stage_id.id} if question else {}
        if model in ("azm.fin.module", "azm.stage"):
            return {"node_id": rid, "family": tab}
        return {}

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
    def open_outputs_book(self, atype, company_id, domain=None, download=True):
        """All of one kind of deliverable for one entity, bound as a single document.

        The entity book binds one model whole; this binds one kind across the branches,
        which is what somebody asking for "our policies" means. The entity is checked
        against the ones the reader works in rather than clamped to them: binding a
        different entity's manual than the one asked for would be worse than refusing.
        """
        allowed = self._library_domains()
        if not allowed:
            raise UserError(_("No deliverables are available for your user."))
        if domain and domain not in allowed:
            raise UserError(_("This model is not available for your user."))
        company = self._companies().filtered(lambda c: c.id == company_id)[:1]
        if not company:
            raise UserError(_("This entity is not one you work in."))
        pub = self.env["azm.doc.publication"]._get_type_book(company, atype, domain)
        return pub._open(download=download)

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
                ["company_id", "state", "generated_on", "source_state"]):
            by_company[pub["company_id"][0]] = pub
        doc = self._library_doc_ref(artifact)
        codes = self._library_entity_codes(companies)
        rows = []
        for company in companies:
            found = by_company.get(company.id)
            state = found["state"] if found else "pending"
            arabic, english, css = STATES.get(state, STATES["pending"])
            source = (found or {}).get("source_state") or False
            approval = next((a for a in APPROVALS if a[0] == source), None)
            rows.append({
                "company_id": company.id,
                "name": company.name,
                # one artifact, one serial, nine copies — the row says which copy it is
                "code": copy_code(artifact.code, codes.get(company.id, "")),
                "approval": source,
                "approval_label": approval[1] if approval else "",
                "approval_en": approval[2] if approval else "",
                "state": state,
                "state_label": arabic,
                "state_en": english,
                "css": css,
                "generated": str(found["generated_on"] or "") if found else "",
                "doc": {**doc, "company_id": company.id},
            })
        return {"available": True, "code": artifact.code, "rows": rows}

    def _library_entity_codes(self, companies):
        """``{company id: its entity code}``, read once for a list rather than per row."""
        entities = self.env["azm.entity"].sudo().with_context(active_test=False).search(
            [("company_id", "in", companies.ids)])
        return {e.company_id.id: e.code or "" for e in entities}

    def _library_holder(self, companies):
        """The entity a listing belongs to, when it belongs to exactly one.

        With several in scope there is no single copy to name and the master code
        stands, which is also what the coverage columns are counting.
        """
        if len(companies) != 1:
            return ""
        return self._library_entity_codes(companies).get(companies.id, "")
