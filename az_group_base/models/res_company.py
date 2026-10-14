from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    code = fields.Char(
        string="Entity Code",
        help="Short code identifying the entity, used as a prefix for its journals.",
    )
    name_ar = fields.Char(string="Arabic Name")

    # The code prefixes the journals of the entity, hence the sequences of its
    # documents. Two entities sharing one would number their documents alike:
    # the journal codes stay unique per company, so nothing else catches it.
    _code_uniq = models.UniqueIndex(
        "(code) WHERE code IS NOT NULL",
        "Another company already uses this entity code.",
    )
