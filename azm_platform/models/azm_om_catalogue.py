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
        MODEL_DOMAINS, 'Model Domain', compute='_compute_azm_domain', store=True, readonly=False,
        help='Which part of the operating model this question area belongs to '
             '(used by the AZM Platform cards and statistics).')

    @api.depends('code', 'is_governance')
    def _compute_azm_domain(self):
        for stage in self:
            if stage.azm_domain:
                stage.azm_domain = stage.azm_domain  # keep a value chosen by hand
            elif stage.is_governance:
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
