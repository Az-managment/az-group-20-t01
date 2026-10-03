from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Put the existing users on the light theme.

    web_enterprise defaults color_scheme to "system", which hands the decision
    to the desktop, so a user on a dark machine saw a dark Odoo. New users get
    light from the field default; the ones already in the database are moved
    here.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["res.users.settings"]._azm_force_light_theme()
