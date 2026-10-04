"""The unified financial model as a tree: FIN › module › topic › requirement.

The page reads the tree from the catalogue itself (azm.fin.module → azm.fin.topic →
azm.fin.requirement) and hangs each entity's own answers off it, so a node's status is
the status of that entity's assessment and nothing else. The detail of a requirement is
built by azm.doc.publication._item(), the very method the PDF uses, so the page and the
document filed in Documents always say the same thing.
"""
from odoo import api, models

from odoo.addons.azm_operating_model.models.azm_fin_catalogue import PROFILES, SCOPES
from odoo.addons.azm_platform.models.azm_documents import STATUS


def _pct(part, whole):
    return round(100.0 * part / whole, 1) if whole else None


class AzmDashboard(models.AbstractModel):
    _inherit = "azm.dashboard"

    # ------------------------------------------------------------------ helpers
    @api.model
    def _fin_tree_company(self, company_id=None):
        """The entity the tree is read for: the one asked for, else the active one."""
        companies = self._companies()
        if company_id:
            picked = companies.filtered(lambda c: c.id == company_id)
            if picked:
                return picked[0]
        active = companies.filtered(lambda c: c.id == self.env.company.id)
        return active[0] if active else companies[:1]

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
        company = self._fin_tree_company(company_id)
        if not company:
            return {"available": False}
        env = self._env_all_companies()

        Pub = env["azm.doc.publication"]
        summary = Pub._get(company, "summary")
        assessment = summary.sudo()._assessment()
        # the entity's answers, by requirement, so a node knows its own state
        lines = {}
        if assessment:
            for line in assessment.sudo().answer_ids:
                lines[line.requirement_id.id] = line
        # the document of each requirement, so a node can be opened and read
        docs = {}
        for pub in Pub.sudo().search([("company_id", "=", company.id), ("kind", "=", "requirement")]):
            docs[pub.requirement_id.id] = {"id": pub.id, "state": pub.state}

        modules = []
        totals = {"requirements": 0, "applicable": 0, "done": 0, "gaps": 0}
        for module in env["azm.fin.module"].search([]):
            requirements = env["azm.fin.requirement"].search([("module_id", "=", module.id)])
            topics, seen = [], {}
            m_fig = {"requirements": 0, "applicable": 0, "done": 0, "gaps": 0}
            for req in requirements:
                line = lines.get(req.id)
                state = (line.state or "open") if line else "open"
                if line and not line.applicable:
                    state = "na"
                item = {
                    "id": req.id,
                    "tree_ref": req.tree_ref or req.code,
                    "title": req.title,
                    "owner": req.owner or "",
                    "profile": PROFILES[req.profile][0],
                    "scope": SCOPES.get(req.scope_code, ""),
                    "questions": len(req.question_ids),
                    "status": self._fin_tree_status(state),
                    "doc": docs.get(req.id),
                }
                topic = req.topic_id
                key = topic.id or 0
                if key not in seen:
                    seen[key] = {
                        "id": topic.id or 0,
                        "code": topic.code or "",
                        "name": topic.name or "بدون موضوع",
                        "items": [], "requirements": 0, "done": 0, "gaps": 0,
                    }
                    topics.append(seen[key])
                node = seen[key]
                node["items"].append(item)
                node["requirements"] += 1
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
                node["completion"] = _pct(node["done"], node["requirements"])
            modules.append({
                "id": module.id,
                "code": f"FIN.{module.code}",
                "name": module.name,
                "topics": topics,
                **m_fig,
                "completion": _pct(m_fig["done"], m_fig["applicable"]),
            })
            for k in totals:
                totals[k] += m_fig[k]
        totals["completion"] = _pct(totals["done"], totals["applicable"])
        totals["topics"] = sum(len(m["topics"]) for m in modules)
        totals["modules"] = len(modules)

        return {
            "available": True,
            "company": {"id": company.id, "name": company.name},
            "entity_options": [{"id": c.id, "name": c.name} for c in self._companies()],
            "assessment": {
                "id": assessment.id, "name": assessment.name, "version": assessment.version,
                "state": assessment.state, "is_demo": assessment.is_demo,
            } if assessment else None,
            "summary_doc": {"id": summary.id, "state": summary.state},
            "totals": totals,
            "modules": modules,
        }

    # ------------------------------------------------------------------ one requirement
    @api.model
    def get_fin_tree_node(self, requirement_id, company_id=None):
        """One requirement in full, built by the same method that writes its PDF."""
        if not self._fin_available():
            return {"available": False}
        company = self._fin_tree_company(company_id)
        requirement = self._env_all_companies()["azm.fin.requirement"].browse(requirement_id)
        requirement.check_access("read")
        Pub = self.env["azm.doc.publication"]
        pub = Pub._get(company, "requirement", requirement=requirement)
        assessment = pub.sudo()._assessment()
        line = pub.sudo()._lines(assessment)[:1] if assessment else None
        item = Pub._item(requirement, line or None)
        item.update({
            "id": requirement.id,
            "company": company.name,
            "doc": {"id": pub.id, "state": pub.state},
            "available": True,
        })
        return item
