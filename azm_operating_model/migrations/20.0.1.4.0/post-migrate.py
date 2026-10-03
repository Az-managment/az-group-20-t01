from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Entities are now the companies of Odoo: link the existing entities to their company,
    create one for every company that had none, archive unused entities without a company."""
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    env["azm.entity"]._azm_sync_companies()
    env["azm.entity"]._azm_fin_default_scopes()
