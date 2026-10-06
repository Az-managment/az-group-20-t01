"""Renumber onto AZM-<DOMAIN>-<NODE>-<TYPE>-<SERIAL>, counting inside the node.

AZM-FIN-POL-000001 read as though FIN.GOV had one policy. It has three — financial
periods, activity oversight, additional cases — and each of them is its own policy, its
own document and now its own code:

    AZM-FIN-GOV-POL-000001  الفترات المالية
    AZM-FIN-GOV-POL-000002  رقابة النشاط
    AZM-FIN-GOV-POL-000003  حالات إضافية

So the deliverable is the requirement rather than the module's compiled version of all
of them, typed by the profile it is answered under, and the serial counts inside its
module. Every code in the registry changes shape, which is why this renumbers rather
than patches: the codes are derived from the catalogue, so running the derivation is
the migration.

A document prints its code into its own fingerprint, so every one of them is now
outdated and will be rebuilt the next time it is read or the queue comes round. Nothing
is rebuilt here — there are thousands.
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Artifact = env["azm.artifact"]
    before = {art.ref: art.code for art in Artifact.sudo().search([])}
    Artifact._register_all()
    env["azm.doc.publication"]._link_artifacts()
    after = {art.ref: art.code for art in Artifact.sudo().search([])}
    sample = next((f"{before[ref]} -> {after[ref]}" for ref in after if ref in before), "")
    _logger.info(
        "AZM: registry renumbered onto the node — %s deliverables (was %s); %s",
        len(after), len(before), sample)
