"""The trees of the platform.

A tree is one operating model read from its catalogue down to its leaf, with one
entity's own answers hanging off every node. There is more than one: the unified
financial model (module › topic › requirement) and the procurement cycle (stage ›
group › question), and the page that lists them is built so a third costs a section.

This file holds what every tree shares — which entity a tree is read for — and the
landing page: a section per model, a card per entity under it, each card opening that
entity's tree.
"""
from odoo import _, api, models
from odoo.exceptions import UserError

from .azm_documents import MODULE_OUTPUTS
from .azm_proc_documents import PROC_OUTPUTS

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

    # ------------------------------------------------------------------ documents
    @api.model
    def open_tree_document(self, kind, node_id=None, tab=None, company_id=None, download=False):
        """Open the document a tree node stands for, building it if it has never been read.

        The tree offers every output the catalogue defines, whether or not a document
        has been published for it yet; this is where that offer is honoured. The entity
        is clamped to the ones the user works in, and azm.doc.publication._open() checks
        that the user may read the document before handing anything back.
        """
        # (model of the node, the argument _get() wants it under, the outputs it may ask
        # for). A kind, a node and a tab that do not belong together never reach _get():
        # this method is callable over RPC, and an unknown kind used to resolve quietly
        # to the entity summary while a mismatched tab filed a document in the wrong place.
        NODES = {
            "requirement": ("azm.fin.requirement", "requirement", None),
            "module": ("azm.fin.module", "module", MODULE_OUTPUTS),
            "question": ("azm.question", "question", None),
            "stage": ("azm.stage", "stage", PROC_OUTPUTS),
            "summary": (None, None, None),
            "cycle": (None, None, None),
        }
        if kind not in NODES:
            raise UserError(_("There is no document of this kind."))
        model, argument, outputs = NODES[kind]
        if (tab or None) is not None and (outputs is None or tab not in outputs):
            raise UserError(_("This document has no output called %s.", tab))
        if outputs and not tab:
            raise UserError(_("Which output of this node do you want to read?"))

        company = self._tree_company(company_id)
        if not company:
            raise UserError(_("You do not work in any entity, so there is no document to open."))
        env = self._env_all_companies()
        node = {}
        if model:
            record = env[model].browse(node_id).exists()
            if not record:
                raise UserError(_("That part of the model no longer exists."))
            record.check_access("read")   # the catalogue decides who may ask for it
            node[argument] = record
        pub = env["azm.doc.publication"]._get(company, kind, tab=tab or None, **node)
        return pub._open(download=download)

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
