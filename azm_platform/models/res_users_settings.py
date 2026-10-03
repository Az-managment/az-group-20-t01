from odoo import api, fields, models


class ResUsersSettings(models.Model):
    _inherit = "res.users.settings"

    # web_enterprise ships "system", which follows whatever the operating system
    # or browser asks for, so a user on a dark desktop gets a dark Odoo. The AZM
    # interfaces are designed light, and the Arabic documents are read on a light
    # ground, so light is the default here.
    color_scheme = fields.Selection(default="light")

    @api.model
    def _azm_force_light_theme(self):
        """Put every internal user on the light theme.

        ir_http.color_scheme() only honours an explicit "light" or "dark" on the
        user; with "system", or with no settings row at all, it falls back to the
        browser's color_scheme cookie. So the row has to exist and has to say
        light, otherwise the desktop still decides.
        """
        users = self.env["res.users"].with_context(active_test=False).search([
            ("share", "=", False),
        ])
        for user in users:
            settings = self.sudo()._find_or_create_for_user(user)
            if settings.color_scheme != "light":
                settings.color_scheme = "light"
        return len(users)
