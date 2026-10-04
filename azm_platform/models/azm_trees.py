"""The trees of the platform.

A tree is one operating model read from its catalogue down to its leaf, with one
entity's own answers hanging off every node. There is more than one: the unified
financial model (module › topic › requirement) and the procurement cycle (stage ›
group › question), and the page that lists them is built so a third costs a section.

This file holds what every tree shares — which entity a tree is read for — and the
landing page: a section per model, a card per entity under it, each card opening that
entity's tree.
"""
from odoo import api, models

# The models that can be walked as a tree, in the order the page shows them.
TREES = [
    {
        "key": "financial",
        "tag": "azm_fin_tree",
        "action": "azm_platform.action_azm_fin_tree",
        "icon": "payments",
        "tone": "green",
    },
    {
        "key": "procurement",
        "tag": "azm_proc_tree",
        "action": "azm_platform.action_azm_proc_tree",
        "icon": "shopping_cart",
        "tone": "blue",
    },
]


class AzmDashboard(models.AbstractModel):
    _inherit = "azm.dashboard"

    # ------------------------------------------------------------------ shared
    @api.model
    def _tree_company(self, company_id=None):
        """The entity a tree is read for: the one asked for, else the active one.

        A company the user was never given is not read: the tree falls back to one
        they actually work in, so a hand-made URL cannot widen what they see.
        """
        companies = self._companies()
        if company_id:
            picked = companies.filtered(lambda c: c.id == company_id)
            if picked:
                return picked[0]
        active = companies.filtered(lambda c: c.id == self.env.company.id)
        return active[0] if active else companies[:1]

    @api.model
    def _tree_card(self, company, row, figures):
        """One entity's card under a tree: who it is, how far it got, what is left."""
        return {
            "company_id": company.id,
            "entity_id": row["id"] if row else False,
            "name": company.name,
            "code": row["code"] if row else "",
            "company": self._om_company(company),
            "assessments": row["assessments"] if row else 0,
            "status": row["status"] if row else "not_started",
            "completion": row["completion"] if row else None,
            "figures": figures,
        }

    # ------------------------------------------------------------------ the page
    @api.model
    def get_trees_hub(self):
        """A section per model that can be walked as a tree, a card per entity in it."""
        companies = self._companies()
        by_company = {}
        sections = []

        if self._fin_available():
            data = self.get_financial_model_data()
            if data.get("available"):
                rows = {r["company"]["id"]: r for r in data["entities"] if r["company"]}
                k = data["kpis"]
                cards = []
                for company in companies:
                    row = rows.get(company.id)
                    cards.append(self._tree_card(company, row, [
                        {"key": "applicable", "value": row["applicable"] if row else 0},
                        {"key": "gaps", "value": row["gaps"] if row else 0, "tone": "warn"},
                    ]))
                sections.append({
                    **TREES[0],
                    "levels": ["module", "topic", "requirement"],
                    "units": k["modules"], "items": k["catalogue_questions"],
                    "leaves": k["requirements"],
                    "cards": cards,
                })

        if self._om_available():
            data = self.get_operating_model_data()
            if data.get("available"):
                rows = {}
                for row in data["entities"]:
                    if row["company"]:
                        rows[row["company"]["id"]] = row
                k = data["kpis"]
                cards = []
                for company in companies:
                    row = rows.get(company.id)
                    cards.append(self._tree_card(company, row, [
                        {"key": "answered", "value": row["answered"] if row else 0},
                        {"key": "findings", "value": row["findings_open"] if row else 0, "tone": "warn"},
                    ]))
                sections.append({
                    **TREES[1],
                    "levels": ["stage", "group", "question"],
                    "units": k["stages"], "items": k["questions"],
                    "leaves": k["questions"],
                    "cards": cards,
                })

        for section in sections:
            for card in section["cards"]:
                if card["status"] != "not_started":
                    by_company.setdefault(card["company_id"], set()).add(section["key"])

        return {
            "available": bool(sections),
            "sections": sections,
            "totals": {
                "trees": len(sections),
                "entities": len(companies),
                "entities_covered": len(by_company),
                "leaves": sum(s["leaves"] for s in sections),
                "units": sum(s["units"] for s in sections),
            },
        }
