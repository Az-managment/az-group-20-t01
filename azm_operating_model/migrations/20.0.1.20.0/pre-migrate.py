"""Carry each assignment's single owner into the list of people on it.

A part used to be one person's. It can now be shared, so the column became a table —
and the person already named has to end up in it, or every assignment in the database
would come back held by nobody.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'azm_assignment' AND column_name = 'user_id'
    """)
    if not cr.fetchone():
        return
    cr.execute("""
        CREATE TABLE IF NOT EXISTS azm_assignment_res_users_rel (
            azm_assignment_id integer NOT NULL REFERENCES azm_assignment(id) ON DELETE CASCADE,
            res_users_id integer NOT NULL REFERENCES res_users(id) ON DELETE CASCADE,
            PRIMARY KEY (azm_assignment_id, res_users_id)
        )
    """)
    cr.execute("""
        INSERT INTO azm_assignment_res_users_rel (azm_assignment_id, res_users_id)
             SELECT id, user_id FROM azm_assignment WHERE user_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)
    _logger.info("azm.assignment: carried %s owners into the shared list", cr.rowcount)
