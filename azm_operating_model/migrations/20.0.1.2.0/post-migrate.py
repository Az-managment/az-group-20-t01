from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Databases that never had the financial model get its catalogue now."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    if not env["azm.fin.module"].search_count([]):
        env["azm.fin.module"]._load_catalogue()
        env["azm.entity"]._azm_fin_default_scopes()
