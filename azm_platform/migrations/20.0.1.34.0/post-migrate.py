"""Back onto the registry's own numbering: AZM-<DOMAIN>-<TYPE>-<SERIAL>.

The registry is explicit, and for a reason that only shows up later:

    Canonical ID    AZM-<DOMAIN>-<TYPE>-<SERIAL>; entity/system/version/stage separate.
    Artifact ↔ Tree  One artifact may map to many nodes without copies.

A code naming one node forbids an artifact from belonging to two, and a code naming one
entity makes every entity's copy a different thing — which is the opposite of "store
once, map many". So the module and the entity travel beside the code, on the document
and on the tree, where they can change without the deliverable changing its name.

What stays is the thing the registry actually asked for and the old reading missed:
**0..N of every output type per process**. FIN.GOV's three policies are three artifacts
and three documents, not one of each; so are the gaps against its requirements and the
directions for them.
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
    sample = next((f"{before[ref]} -> {after[ref]}"
                   for ref in after if ref in before and before[ref] != after[ref]), "")
    _logger.info("AZM: %s deliverables renumbered the registry's way; %s",
                 len(after), sample or "nothing moved")
