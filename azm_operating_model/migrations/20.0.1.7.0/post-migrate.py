from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Put the existing internal users on the light theme.

    20.0.1.6.0 only did it from the install hook, so a database that was
    upgraded rather than installed kept everybody on "system".
    """
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    env["res.users.settings"]._azm_apply_light_theme()
