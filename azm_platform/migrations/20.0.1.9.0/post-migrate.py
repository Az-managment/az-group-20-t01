from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Give every company its document folders and queue its operating-model documents.

    The PDFs are rendered by the «AZM: publish operating-model documents» job, a batch at a time,
    so the upgrade itself stays fast.
    """
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    env["azm.doc.folder"]._ensure_all()
    env["azm.doc.publication"]._enqueue()
