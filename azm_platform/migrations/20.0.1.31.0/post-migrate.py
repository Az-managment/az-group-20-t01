"""Point the people who answer questions at their own page.

The landing page is set when somebody is given the AZM user group, which does nothing
for the people who already have it. Odoo's default is the apps screen: for somebody
whose whole job is answering their entity's questions that is a wall of applications
they have no business in, with their own work two clicks behind it.

Only where no home action was ever chosen, and never for the people running the
platform — an administrator's home is their own business.
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    group = env.ref("azm_operating_model.azm_group_user", raise_if_not_found=False)
    if not group:
        return
    users = env["res.users"].with_context(active_test=False).search(
        [("id", "in", group.sudo().all_user_ids.ids)])
    moved = users._azm_set_landing()
    _logger.info("AZM: %s of %s users now start on their own page",
                 len(moved), len(users))
