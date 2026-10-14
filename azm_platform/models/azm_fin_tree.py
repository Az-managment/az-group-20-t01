"""The unified financial model as a tree: FIN › module › topic › requirement.

The page reads the tree from the catalogue itself (azm.fin.module → azm.fin.topic →
azm.fin.requirement) and hangs each entity's own answers off it, so a node's status is
the status of that entity's assessment and nothing else. The detail of a requirement is
built by azm.doc.publication._item(), the very method the PDF uses, so the page and the
document filed in Documents always say the same thing.

The payload is shaped like every other tree of the platform — a model, an entity, three
levels of nodes and a status on each leaf — so one page component draws them all.
"""
from odoo import api, models

from odoo.addons.azm_operating_model.models.azm_fin_catalogue import PROFILES, SCOPES
from odoo.addons.azm_platform.models.azm_documents import (
    FIN_ARTIFACTS, MODULE_OUTPUTS, STATUS)


def _pct(part, whole):
    return round(100.0 * part / whole, 1) if whole else None


class AzmDashboard(models.AbstractModel):
    _inherit = "azm.dashboard"

    # ------------------------------------------------------------------ helpers
    @api.model
    def _fin_assessment(self, company):
        """The financial assessment the tree reads, in the caller's own right.

        Read through the user, never elevated. The access rules scope an assessment to
        the person preparing or reviewing it, while a published *document* is scoped to
        the company — two different decisions, both deliberate. The tree shows the
        answers themselves, so it must follow the first: somebody who may not open an
        assessment does not get to read it here either. The procurement tree has always
        worked this way; this one used to elevate and show everyone everything.
        """
        env = self._env_all_companies()
        entity = env["azm.entity"].search([("company_id", "=", company.id)], limit=1)
        if not entity:
            return env["azm.fin.assessment"]
        Assessment = env["azm.fin.assessment"]
        return (Assessment.search([("entity_id", "=", entity.id), ("state", "=", "approved")],
                                  order="version desc, id desc", limit=1)
                or Assessment.search([("entity_id", "=", entity.id), ("state", "!=", "archived")],
                                     order="version desc, id desc", limit=1))

    @api.model
    def _fin_tree_status(self, key):
        arabic, english, css = STATUS.get(key or "open", STATUS["open"])
        return {"key": key or "open", "label": arabic, "en": english, "css": css}

    # ------------------------------------------------------------------ the tree
    @api.model
    def get_fin_tree(self, company_id=None):
        """FIN › module › topic › requirement, with every node's status for one entity."""
        if not self._fin_available():
            return {"available": False}
        company = self._tree_company(company_id)
        if not company:
            return {"available": False}
        env = self._env_all_companies()

        assessment = self._fin_assessment(company)
        # the entity's answers, by requirement, so a node knows its own state — read as
        # the user, so a node is blank for somebody who may not read the assessment
        lines = {}
        for line in assessment.answer_ids:
            lines[line.requirement_id.id] = line
        # Every output of the model hangs on its node. The list comes from the
        # catalogue, not from the documents already published, so a module shows all
        # of its outputs from the first visit; the document itself is resolved — and
        # built, if this is the first time — when somebody opens it.
        Artifact = env["azm.artifact"]
        empty = self._tree_known_empty(company, "module")

        codes = self._tree_codes(company)
        Pub = env["azm.doc.publication"]

        def module_outputs(module):
            """What this entity actually has here: an output the module can have, and
            that its own answers put something in."""
            return [{"kind": "module", "id": module.id, "tab": tab,
                     "label": MODULE_OUTPUTS[tab][1], "en": MODULE_OUTPUTS[tab][2],
                     "atype": FIN_ARTIFACTS[tab][0], "stage": FIN_ARTIFACTS[tab][1],
                     # the compiled outputs are a binding of the deliverables under
                     # them, so only the module-wide ones carry a code of their own
                     "azm_code": codes.get(f"azm.fin.module,{module.id},{tab}", "")}
                    for tab in module._azm_outputs() if (module.id, tab) not in empty]

        nodes = []
        totals = {"requirements": 0, "applicable": 0, "done": 0, "gaps": 0}
        # one search for the whole catalogue, grouped here, instead of one per module
        by_module = {}
        for req in env["azm.fin.requirement"].search([]):
            by_module.setdefault(req.module_id.id, env["azm.fin.requirement"])
            by_module[req.module_id.id] |= req
        for module in env["azm.fin.module"].search([]):
            requirements = by_module.get(module.id, env["azm.fin.requirement"])
            topics, seen = [], {}
            m_fig = {"requirements": 0, "applicable": 0, "done": 0, "gaps": 0}
            for req in requirements:
                line = lines.get(req.id)
                state = (line.state or "open") if line else "open"
                if line and not line.applicable:
                    state = "na"
                item = {
                    "id": req.id,
                    "code": req.tree_ref or req.code,
                    "title": req.title,
                    "owner": req.owner or "",
                    "profile": PROFILES[req.profile][0],
                    "scope": SCOPES.get(req.scope_code, ""),
                    "questions": len(req.question_ids),
                    "status": self._fin_tree_status(state),
                    # The requirement *is* the deliverable, so the tree says what it is
                    # called as well as where it sits. Its gap and its direction are
                    # deliverables of their own and are read from the library, not here.
                    "azm_code": codes.get(
                        f"azm.fin.requirement,{req.id},{Pub._requirement_tab(req)}", ""),
                    "doc": {"kind": "requirement", "id": req.id},
                }
                topic = req.topic_id
                # a module's untitled requirements make a group of their own: keyed by
                # the module too, so folding one does not fold every module's
                key = topic.id or f"m{module.id}"
                if key not in seen:
                    seen[key] = {
                        "id": key,
                        "code": topic.code or "",
                        "name": topic.name or "بدون موضوع",
                        "items": [], "count": 0, "done": 0, "gaps": 0,
                    }
                    topics.append(seen[key])
                node = seen[key]
                node["items"].append(item)
                node["count"] += 1
                m_fig["requirements"] += 1
                if line and line.applicable:
                    m_fig["applicable"] += 1
                    if line.is_done:
                        node["done"] += 1
                        m_fig["done"] += 1
                    if state in ("partial", "unavailable"):
                        node["gaps"] += 1
                        m_fig["gaps"] += 1
            if not requirements:
                continue
            for node in topics:
                node["completion"] = _pct(node["done"], node["count"])
                node["meta"] = node["count"]
            nodes.append({
                "id": module.id,
                "code": f"FIN.{module.code}",
                "name": module.name,
                "docs": module_outputs(module),
                "children": topics,
                "meta": m_fig["requirements"],
                "gaps": m_fig["gaps"],
                "completion": _pct(m_fig["done"], m_fig["applicable"]),
                **m_fig,
            })
            for k in totals:
                totals[k] += m_fig[k]
        # how many documents of each family this entity has: how many policies, how
        # many SOPs, how many authority maps … counted from what the tree offers,
        # less the outputs the model found nothing to say in
        published = self._tree_published(company, ("requirement", "module", "summary"))
        # counted the same way the chips are offered: an output this entity actually
        # has, so the tile and the branches never disagree about how many there are
        offered = {tab: 0 for tab in MODULE_OUTPUTS}
        for node in nodes:
            for doc in node["docs"]:
                offered[doc["tab"]] += 1
        families = [{
            "tab": tab, "label": out[1], "en": out[2],
            "offered": offered[tab],
            # with no assessment behind them no module output has anything in it
            "empty": offered[tab] if not assessment else 0,
            "ready": published.get(("module", tab), {}).get("done", 0),
        } for tab, out in MODULE_OUTPUTS.items()]
        families.append({
            "tab": "requirement", "label": "أوراق المتطلبات", "en": "Requirement sheets",
            "offered": totals["requirements"], "empty": 0,
            "ready": published.get(("requirement", False), {}).get("done", 0),
        })
        families.append({
            "tab": "summary", "label": "ملخص الكيان", "en": "Entity summary",
            "offered": 1, "empty": 0,
            "ready": published.get(("summary", False), {}).get("done", 0),
        })
        outputs = self._tree_outputs(families)

        totals["completion"] = _pct(totals["done"], totals["applicable"])
        totals["topics"] = sum(len(n["children"]) for n in nodes)
        totals["modules"] = len(nodes)

        return {
            "available": True,
            "model": {"key": "financial", "root": "FIN"},
            "company": {"id": company.id, "name": company.name},
            "entity_options": [{"id": c.id, "name": c.name} for c in self._companies()],
            "assessment": {
                "id": assessment.id, "name": assessment.name, "version": assessment.version,
                "state": assessment.state, "is_demo": assessment.is_demo,
            } if assessment else None,
            "summary_doc": {"kind": "summary", "label": "ملخص الكيان", "en": "Entity summary"},
            "book_doc": {"kind": "book", "label": "الكتاب الكامل", "en": "Full book"},
            "totals": totals,
            "outputs": outputs,
            "nodes": nodes,
        }

    # ------------------------------------------------------------------ one requirement
    @api.model
    def get_fin_tree_node(self, requirement_id, company_id=None):
        """One requirement in full, built by the same method that writes its PDF."""
        if not self._fin_available():
            return {"available": False}
        company = self._tree_company(company_id)
        requirement = self._env_all_companies()["azm.fin.requirement"].browse(requirement_id)
        requirement.check_access("read")
        assessment = self._fin_assessment(company)
        line = assessment.answer_ids.filtered(
            lambda a: a.requirement_id == requirement)[:1] if assessment else None
        item = self.env["azm.doc.publication"]._item(requirement, line or None)
        item.update({
            # the document places a step as (label, code, name); a tree step is
            # (label, what to show), the same shape the procurement tree returns
            "path": [(label, " · ".join(x for x in (code, name) if x)) for label, code, name in item["path"]],
            "id": requirement.id,
            "company": company.name,
            "doc": {"kind": "requirement", "id": requirement.id},
            "available": True,
        })
        return item
