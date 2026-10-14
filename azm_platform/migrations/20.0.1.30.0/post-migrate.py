"""Renumber the registry: only what the group produces, and no holes.

A code used to be allocated for every deliverable the catalogue *could* define. Every
entity marked investments, real estate and inter-company not applicable, so fourteen
codes stood for documents that exist nowhere — and each of them pushed every real
deliverable after it up a place. AZM-FIN-PRO-000003 was one of them, which is why the
third procedure looked like the first.

The registry is derived now: numbered in the catalogue's order, skipping what nothing
is produced for, closing up so each type reads 000001..N. Documents print their code
into their own fingerprint, so the ones whose number moved age by themselves and are
rebuilt the next time they are read — nothing has to be rebuilt here.
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
    retired = sorted(code for ref, code in before.items() if ref not in after)
    moved = [ref for ref in after if ref in before and before[ref] != after[ref]]
    _logger.info(
        "AZM: registry renumbered — %s deliverables, %s retired with nothing behind them "
        "(%s), %s renumbered into place",
        len(after), len(retired), ", ".join(retired[:6]) or "none", len(moved))
