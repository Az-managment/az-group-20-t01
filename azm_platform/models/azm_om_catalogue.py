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
        """Match unlinked entities to companies by name, other-language name or initials."""
        companies = self.env['res.company'].sudo().search([])

        def norm(text):
            return ' '.join((text or '').split()).casefold()

        def initials(text):
            return ''.join(w[0] for w in (text or '').split() if w[0].isalnum()).upper()

        for entity in self.sudo().with_context(active_test=False).search([('company_id', '=', False)]):
            keys = {norm(entity.name), norm(entity.code)}
            match = companies.filtered(lambda c: keys & {norm(c.name), norm(c.azm_name_alt)})
            if not match:
                match = companies.filtered(lambda c: initials(c.name) == (entity.code or '').upper())
            if len(match) == 1:
                entity.company_id = match


class ResCompany(models.Model):
    _inherit = 'res.company'

    azm_om_entity_ids = fields.One2many('azm.entity', 'company_id', string='Operating Model Entities')
