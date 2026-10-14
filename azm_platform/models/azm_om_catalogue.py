from odoo import api, fields, models

MODEL_DOMAINS = [
    ('governance', 'Governance'),
    ('procurement', 'Procurement Operations'),
    ('financial', 'Financial'),
]

# Stages of the procurement cycle that belong to the financial model
# (budget, invoices, advances, payment, closing). Editable per stage afterwards.
FINANCIAL_STAGE_CODES = {'BUD', 'INV', 'ADV', 'PAY', 'CLS'}


class AzmStage(models.Model):
    _inherit = 'azm.stage'

    azm_domain = fields.Selection(
        MODEL_DOMAINS, 'Model Domain', compute='_compute_azm_domain',
        inverse='_inverse_azm_domain', store=True, readonly=False,
        help='Which part of the operating model this question area belongs to '
             '(used by the AZM Platform cards and statistics).')
    # Whether somebody chose the domain rather than the code and the governance flag
    # deciding it. The computation used to infer that from "a value is already there",
    # which is true of every value it had itself just written — so after the first pass
    # it could never change its mind. A stage created as operational and later ticked
    # as governance stayed in the procurement column of every card and filter.
    azm_domain_manual = fields.Boolean(
        'Domain set by hand', default=False, copy=False,
        help='Set when the domain was chosen rather than derived; the derivation then '
             'leaves it alone.')

    def _inverse_azm_domain(self):
        for stage in self:
            stage.azm_domain_manual = True

    @api.depends('code', 'is_governance')
    def _compute_azm_domain(self):
        for stage in self:
            if stage.azm_domain_manual:
                continue   # chosen by hand; the derivation does not argue
            if stage.is_governance:
                stage.azm_domain = 'governance'
            elif stage.code in FINANCIAL_STAGE_CODES:
                stage.azm_domain = 'financial'
            else:
                stage.azm_domain = 'procurement'


class AzmQuestion(models.Model):
    _inherit = 'azm.question'

    azm_domain = fields.Selection(related='stage_id.azm_domain', store=True, string='Model Domain')


class AzmRiskRule(models.Model):
    _inherit = 'azm.risk.rule'

    azm_domain = fields.Selection(related='stage_id.azm_domain', store=True, string='Model Domain')


class AzmFinding(models.Model):
    _inherit = 'azm.finding'

    azm_domain = fields.Selection(related='stage_id.azm_domain', store=True, string='Model Domain')


class AzmEntity(models.Model):
    _inherit = 'azm.entity'

    @api.model
    def _azm_autolink_companies(self):
        """Kept for compatibility: entities are now created from the companies by azm_operating_model."""
        return self._azm_sync_companies()


class ResCompany(models.Model):
    _inherit = 'res.company'

    azm_om_entity_ids = fields.One2many('azm.entity', 'company_id', string='Operating Model Entities')
