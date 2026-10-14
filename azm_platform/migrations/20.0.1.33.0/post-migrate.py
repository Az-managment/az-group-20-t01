"""Give every output of a requirement its own document.

FUE-FIN-GOV-GAP-000001 was one code over five gaps, exactly as AZM-FIN-POL-000001 had
been one code over three policies. The rule is the same for all of them now and it is
the only rule: every module-level document is a binding of what sits under it, and every
requirement-level document is a deliverable with a code of its own.

So a requirement produces the thing it is — a policy, a procedure, an authority, a
report, a system requirement — and also the gap against it and the direction for it,
each in its own document. A requirement document was keyed `req:<id>`; it is now
`req:<id>:<output>`, and the two further documents are created alongside.
"""
import logging

from odoo import api, SUPERUSER_ID

from odoo.addons.azm_platform.models.azm_coding import REQUIREMENT_ASPECTS

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Pub = env["azm.doc.publication"].sudo()

    # re-key the documents that are already filed, so the work already done is kept
    old = Pub.search([("kind", "=", "requirement"), ("tab", "=", False)])
    for pub in old:
        tab = Pub._requirement_tab(pub.requirement_id)
        pub.write({"tab": tab, "key": f"req:{pub.requirement_id.id}:{tab}"})
    _logger.info("AZM: %s requirement documents re-keyed to their own output", len(old))

    # and the new ones — the gap and the direction of each requirement
    for company in env["res.company"].sudo().search([]):
        Pub._ensure_company(company)
    # the aspects exist for every requirement and most entities have neither a gap nor
    # a direction on a given one, so they wait to be asked for rather than filling a
    # queue of thousands with documents that will be filed as empty
    aspects = Pub.search([("kind", "=", "requirement"),
                          ("tab", "in", list(REQUIREMENT_ASPECTS)),
                          ("build", "!=", "on_open")])
    aspects.write({"build": "on_open"})
    _logger.info("AZM: %s gap and direction documents set to build when read",
                 len(aspects))

    # a requirement's gap and the requirement itself were two files called the same
    # thing, because the name is stored and changing how it is written does not recompute
    # what is already there
    named = Pub.search([("kind", "=", "requirement")])
    env.add_to_compute(Pub._fields["name"], named)
    named.flush_recordset(["name"])

    env["azm.artifact"]._register_all()
    linked = Pub._link_artifacts()
    _logger.info("AZM: %s documents now; %s linked to the deliverable they are",
                 Pub.search_count([]), linked)
