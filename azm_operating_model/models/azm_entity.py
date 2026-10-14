import re

from odoo import Command, api, fields, models


def _norm(text):
    return " ".join((text or "").split()).casefold()


# Words nobody puts in an acronym. "Future University in Egypt" is FUE to everyone who
# works there, and was FUIE here because the "in" counted — which is the sort of thing
# that only shows up once the code is printed on every document the entity issues.
# "Al" is not among them: it is part of a name, not a joining word.
_NOT_IN_AN_ACRONYM = {
    "in", "of", "the", "and", "for", "at", "on", "to", "a", "an", "by", "with",
    "من", "في", "و", "ال",
}


def _initials(text):
    """The letters somebody would actually write for a name of this shape."""
    words = [w for w in (text or "").split()
             if w[0].isalnum() and w.strip("-–—").lower() not in _NOT_IN_AN_ACRONYM]
    return "".join(w[0] for w in words).upper()


class AzmEntity(models.Model):
    """An entity of the operating models is a company of Odoo.

    One entity per company, created and kept up to date automatically (name, active):
    nothing to create by hand. The entity only adds what the operating models need on top
    of the company: a short code, the users allowed to answer for it and its activities."""
    _name = "azm.entity"
    _description = "AZM Entity"
    _order = "sequence, code"

    name = fields.Char("الكيان", required=True, translate=True)
    code = fields.Char("الكود", required=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one("res.company", "الشركة", index=True, ondelete="cascade",
                                 help="الشركة في Odoo التي يمثلها الكيان؛ الاسم والحالة يتبعانها.")
    user_ids = fields.Many2many(
        "res.users", "azm_entity_res_users_rel", "entity_id", "user_id", string="المستخدمون المصرح لهم",
        domain=[("share", "=", False)],
        help="معدّو الإفادات والمراجعون الذين يرون هذا الكيان وإفاداته ومخاطره. مدير النموذج يرى كل الكيانات.")
    color = fields.Integer()
    active = fields.Boolean(default=True)
    assessment_ids = fields.One2many("azm.assessment", "entity_id")
    assessment_count = fields.Integer(compute="_compute_assessment_count")

    _code_uniq = models.Constraint("UNIQUE(code)", "كود الكيان لازم يكون فريد.")
    _company_uniq = models.Constraint("UNIQUE(company_id)", "الشركة لها كيان بالفعل.")

    def _compute_assessment_count(self):
        counts = dict(self.env["azm.assessment"]._read_group(
            [("entity_id", "in", self.ids)], ["entity_id"], ["__count"]))
        for entity in self:
            entity.assessment_count = counts.get(entity, 0)

    # ---------------------------------------------------------------- companies → entities
    @api.model
    def _azm_new_code(self, company, taken):
        """The code this company is known by, preferring the one it already has.

        A company carries an entity code of its own — it prefixes the company's journals
        and therefore the numbering of everything it files — and that is the code the
        group knows it by. This used to ignore it and build initials from the name
        instead, so the two drifted apart: AZ Management & Development is AZM on its
        journals and was AMD here, and its documents printed AMD-FIN-POL-000001 for an
        entity nothing else in the system calls AMD.

        Initials are the fallback, for a company that has no code to go on.
        """
        own = re.sub(r"[^A-Z0-9]", "", (company.code or "").upper())
        base = own[:6] or re.sub(r"[^A-Z0-9]", "", _initials(company.name))[:6] or f"C{company.id}"
        code, n = base, 2
        while code in taken:
            code, n = f"{base}{n}", n + 1
        taken.add(code)
        return code

    @api.model
    def _azm_sync_companies(self, companies=None):
        """Give every company its entity (re-using a matching unlinked entity) and copy name / active.

        Called on install, on upgrade and whenever a company is created or renamed. With no
        companies given, entities left without a company and without assessments are archived."""
        Entity = self.sudo().with_context(active_test=False)
        everything = companies is None
        companies = (companies or self.env["res.company"]).sudo().with_context(active_test=False)
        if everything:
            companies = companies.search([])
        entities = Entity.search([])
        by_company = {e.company_id.id: e for e in entities if e.company_id}
        unlinked = entities.filtered(lambda e: not e.company_id)
        taken = set(entities.mapped("code"))
        for company in companies:
            entity = by_company.get(company.id)
            if not entity:
                names = {_norm(company.name), _norm(getattr(company, "azm_name_alt", ""))} - {""}
                match = unlinked.filtered(lambda e: {_norm(e.name), _norm(e.code)} & names)
                if not match:
                    match = unlinked.filtered(lambda e: e.code and e.code.upper() == _initials(company.name))
                entity = match[:1] if len(match) == 1 else Entity
                if entity:
                    unlinked -= entity
                    entity.company_id = company
            vals = {"name": company.name, "active": company.active}
            if entity:
                entity.write({k: v for k, v in vals.items() if entity[k] != v})
            else:
                Entity.create({**vals, "company_id": company.id, "code": self._azm_new_code(company, taken),
                               "sequence": company.sequence if "sequence" in company._fields else 10})
        if everything:
            for entity in unlinked.filtered("active"):
                used = self.env["azm.assessment"].sudo().with_context(active_test=False).search_count(
                    [("entity_id", "=", entity.id)])
                if "azm.fin.assessment" in self.env:
                    used += self.env["azm.fin.assessment"].sudo().search_count([("entity_id", "=", entity.id)])
                if not used:
                    entity.active = False
        return True

    def action_sync_companies(self):
        """Re-sync entities with companies. The work runs elevated — it touches every
        company — so the right to ask for it is checked here, or anyone could rename,
        relink and archive the whole group's entities over RPC."""
        self.env["azm.entity"].check_access("write")
        self._azm_sync_companies()
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"type": "success", "message": "تمت مزامنة الكيانات مع الشركات.",
                           "next": {"type": "ir.actions.client", "tag": "soft_reload"}}}

    def _azm_grant_existing_users(self):
        """Give each entity's existing preparers / reviewers access to it (used on upgrade)."""
        for entity in self.sudo().with_context(active_test=False).search([]):
            assessments = self.env["azm.assessment"].sudo().with_context(active_test=False).search(
                [("entity_id", "=", entity.id)])
            users = (assessments.user_id | assessments.reviewer_id | assessments.create_uid).filtered(
                lambda u: not u.share and u.id != 1)
            if users:
                entity.user_ids = [Command.link(u.id) for u in users]


class ResCompany(models.Model):
    _inherit = "res.company"

    azm_entity_ids = fields.One2many("azm.entity", "company_id", string="كيان نماذج التشغيل")

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        self.env["azm.entity"]._azm_sync_companies(companies)
        return companies

    def write(self, vals):
        res = super().write(vals)
        if {"name", "active"} & set(vals):
            self.env["azm.entity"]._azm_sync_companies(self)
        return res
