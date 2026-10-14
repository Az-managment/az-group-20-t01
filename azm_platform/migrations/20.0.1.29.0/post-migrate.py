"""Point every published document at the deliverable it is a copy of.

The outputs library reads one deliverable across every entity, and counts how many of
them hold a ready copy. That count is a group over azm_doc_publication.artifact_id, a
link that did not exist before this version — so without this the library opens showing
nothing held anywhere until something happens to queue the documents again.
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["azm.artifact"]._register_all()
    linked = env["azm.doc.publication"]._link_artifacts()
    _logger.info("AZM: linked %s documents to the deliverable they are a copy of", linked)
