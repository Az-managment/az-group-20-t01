"""Give the work that already exists a date for when it reached its current state.

Nothing recorded it until now, so the best available answer is used: when it was
approved, for the approved ones, and otherwise when the row was last written. That is
not exact for a record touched since it moved, but it is honest to within a write and
far better than a column of blanks on a page whose job is to say what is overdue.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for model in ("azm.fin.assessment", "azm.assessment"):
        if model not in env:
            continue
        cr.execute(f"""
            UPDATE {env[model]._table}
               SET state_since = COALESCE(approved_date, write_date, create_date)
             WHERE state_since IS NULL
        """)
        _logger.info("%s: dated %s rows", model, cr.rowcount)
