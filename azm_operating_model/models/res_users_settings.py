from odoo import api, fields, models

ALLOW_DARK_PARAM = 'azm.allow_dark_theme'


class ResUsersSettings(models.Model):
    _inherit = 'res.users.settings'

    # AZM pages are designed for the light theme, so a user starts on it unless
    # an administrator allows dark mode (parameter ``azm.allow_dark_theme``).
    #
    # This is a preference, deliberately, and not a theme forced on the served
    # response. web_enterprise decides the theme on both sides: the server puts
    # it in the color_scheme cookie, and ColorSchemePlugin recomputes it in the
    # browser from this preference, falling back to the operating system when
    # it reads "system". Overriding ir.http.color_scheme made the two disagree
    # whenever the system asked for dark: the browser wrote "dark" into the
    # cookie and reloaded, the next response wrote "light" back, and the page
    # reloaded for as long as it was left open.
    color_scheme = fields.Selection(default=lambda self: self._azm_default_color_scheme())

    @api.model
    def _azm_default_color_scheme(self):
        if self.env['ir.config_parameter'].sudo().get_bool(ALLOW_DARK_PARAM):
            return 'system'
        return 'light'

    @api.model
    def _azm_apply_light_theme(self):
        """Put the existing internal users on the light theme.

        The default above only covers settings created from now on, and a user
        who was already there keeps whatever they had, which is "system" for
        anybody who never chose.
        """
        if self.env['ir.config_parameter'].sudo().get_bool(ALLOW_DARK_PARAM):
            return
        users = self.env['res.users'].with_context(active_test=False).search([
            ('share', '=', False),
        ])
        for user in users:
            settings = self.sudo()._find_or_create_for_user(user)
            if settings.color_scheme == 'system':
                settings.color_scheme = 'light'
