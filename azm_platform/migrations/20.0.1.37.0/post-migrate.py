"""Rebuild the documents whose filename stopped matching the code they print.

A published document is named for the code it carries, and it is rebuilt when its
fingerprint moves. Procurement documents fingerprinted the *master* code while printing
the entity's *copy* of it, so the two could disagree without the document ageing. That
is fixed in _current_stamp, but it cannot heal a document whose stored fingerprint never
contained the entity code in the first place: renaming AZ Management from AMD to AZM
left two procurement documents named AMD-PUR-… with a fingerprint that had only ever
recorded AZM-PUR-….

So the stale ones are found by what they are actually called, and their fingerprint is
cleared. Nothing is rendered here — the queue rebuilds them when they are next read,
which keeps a migration from turning into a publishing run.

Safe to run twice: a document whose name already agrees with its code is left alone.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api
    env = api.Environment(cr, SUPERUSER_ID, {})
    Pub = env["azm.doc.publication"].sudo()

    stale = Pub.browse()
    for pub in Pub.search([("document_id", "!=", False), ("stamp", "!=", False)]):
        code = pub._scoped_code()
        if not code:
            continue        # a binding carries no code of its own
        name = pub.document_id.name or ""
        head = name.split(" · ", 1)[0].strip()
        # only a name that leads with some other code counts: one that leads with the
        # document's own title never claimed a code to begin with
        if head and head != code and head.count("-") >= 3:
            stale |= pub

    if stale:
        stale.write({"stamp": False})
        _logger.info("cleared the fingerprint of %s document(s) named for an older code; "
                     "they rebuild when next read", len(stale))
    else:
        _logger.info("every published document is named for the code it prints")
