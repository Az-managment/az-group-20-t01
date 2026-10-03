from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Table columns now carry their input type (list / number / date): reload the financial catalogue."""
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    env["azm.fin.module"]._load_catalogue()
