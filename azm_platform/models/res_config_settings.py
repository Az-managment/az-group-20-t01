from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    azm_ai_api_key = fields.Char('Anthropic API Key', config_parameter='azm_platform.ai_api_key')
    azm_ai_model = fields.Char('AI Model', config_parameter='azm_platform.ai_model',
                               default='claude-sonnet-4-5')
    azm_allow_dark_theme = fields.Boolean(
        'Allow dark mode', config_parameter='azm.allow_dark_theme',
        help='AZM pages always open in the light theme. Tick to let users who switched Odoo to dark mode keep it.')
