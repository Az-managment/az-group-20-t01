from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    azm_ai_api_key = fields.Char('Anthropic API Key', config_parameter='azm_platform.ai_api_key')
    azm_ai_model = fields.Char('AI Model', config_parameter='azm_platform.ai_model',
                               default='claude-sonnet-4-5')
