"""Call AZ Management & Development by the code the rest of the group calls it.

A company carries an entity code of its own, and it is the one everything else is
numbered from — it prefixes the company's journals and so the sequences of everything
they file. The entity beside it was coded from the initials of its name instead, and
the two drifted: the company is AZM on its journals, the entity was AMD here, and every
document this entity published printed AMD-FIN-POL-000001 for an entity nothing else in
the system calls AMD.

The copy code is derived at render time rather than stored, so this renames one row and
the documents follow. The master register is untouched: an artifact is numbered once, as
AZM-FIN-POL-000001, and AZ Management holds the register — so its copy of an artifact is
that artifact, and the two codes coinciding is the point rather than a collision.

Safe to run twice: it renames only when AMD is still there and AZM is still free.
"""
import logging

_logger = logging.getLogger(__name__)

OLD, NEW = "AMD", "AZM"


def migrate(cr, version):
    cr.execute("SELECT id FROM azm_entity WHERE code = %s", (NEW,))
    if cr.fetchone():
        _logger.info("azm.entity %s already exists; nothing to rename", NEW)
        return
    cr.execute("SELECT id FROM azm_entity WHERE code = %s", (OLD,))
    row = cr.fetchone()
    if not row:
        _logger.info("no azm.entity coded %s; nothing to rename", OLD)
        return
    cr.execute("UPDATE azm_entity SET code = %s WHERE id = %s", (NEW, row[0]))
    _logger.info("azm.entity %s renamed %s -> %s", row[0], OLD, NEW)
