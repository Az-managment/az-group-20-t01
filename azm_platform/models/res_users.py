"""Where somebody lands when they log in.

Odoo's default is the apps screen. For somebody whose whole job is answering their
entity's questions that is a wall of applications they have no business in, with their
own work two clicks behind it. So the AZM user group carries a landing page: مساحتي.

Only when they have not chosen one themselves, and only for people who are not running
the platform — an administrator's home is their own business, and a home action
somebody set deliberately is never overwritten.
"""
from odoo import api, models


class ResUsers(models.Model):
    _inherit = "res.users"

    def _azm_landing_action(self):
        return self.env.ref("azm_platform.action_azm_my_work", raise_if_not_found=False)

    def _azm_set_landing(self):
        """Point at مساحتي the people who should start their day there."""
        action = self._azm_landing_action()
        if not action:
            return self.browse()
        answerers = self.filtered(
            lambda u: not u.share and not u.action_id
            and u.has_group("azm_operating_model.azm_group_user")
            # the page hangs under the AZM root menu: without that group they would
            # land on it with no sidebar around it
            and u.has_group("azm_platform.group_azm_user")
            # somebody who runs the platform starts where they choose, not here
            and not u.has_group("azm_platform.group_azm_manager")
            and not u.has_group("azm_operating_model.azm_group_manager"))
        if answerers:
            answerers.sudo().write({"action_id": action.id})
        return answerers

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        users._azm_set_landing()
        return users

    def write(self, vals):
        result = super().write(vals)
        # Only when the groups change. Reacting to action_id too meant somebody who
        # cleared their home action had it put straight back in the same transaction —
        # "never overwritten" has to cover removing one, not only setting one.
        if "group_ids" in vals:
            self._azm_set_landing()
        return result
