from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def color_scheme(self):
        """AZM pages are designed for the light theme: serve the light assets even when a user
        switched Odoo to dark mode (Enterprise), unless an administrator allows dark mode
        (Settings › AZM › Allow dark mode, parameter ``azm.allow_dark_theme``)."""
        if not self.env["ir.config_parameter"].sudo().get_bool("azm.allow_dark_theme"):
            return "light"
        return super().color_scheme()
