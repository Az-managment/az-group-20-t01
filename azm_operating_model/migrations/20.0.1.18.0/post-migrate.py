"""Re-code the entities whose code came out of the old initials.

"Future University in Egypt" was FUIE, because the "in" counted. Everyone there writes
FUE, and the code is now printed on every document the entity issues — so it is worth
getting right rather than leaving as something only a machine would have written.

Only codes that were generated are touched: an entity whose code still matches what the
old rule would have produced for its name has never been edited, so correcting it takes
nothing away from anybody. One somebody chose is left exactly as it is, whatever it
looks like, and so is one whose corrected form is already taken.

Renaming an entity re-codes its documents and ages them, so they reissue under the new
prefix — that is the point, and it is why nothing is rebuilt here.
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def _old_initials(text):
    """What the rule used to produce: the first letter of every word, joining words and
    all."""
    return "".join(w[0] for w in (text or "").split() if w[0].isalnum()).upper()


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Entity = env["azm.entity"].sudo().with_context(active_test=False)
    entities = Entity.search([])
    taken = set(entities.mapped("code"))
    from odoo.addons.azm_operating_model.models.azm_entity import _initials

    changed = []
    for entity in entities:
        was = entity.code or ""
        generated = _old_initials(entity.name)[:6]
        if was != generated:
            continue                      # somebody chose this one; leave it
        now = _initials(entity.name)[:6]
        if not now or now == was or now in taken:
            continue
        taken.discard(was)
        taken.add(now)
        entity.code = now
        changed.append(f"{was} -> {now} ({entity.name})")
    _logger.info("AZM: %s entity codes corrected%s", len(changed),
                 (": " + "; ".join(changed[:5])) if changed else "")
