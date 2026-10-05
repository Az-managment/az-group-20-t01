"""Pages a role is not offered, where a group cannot say so.

مساحتي is one person's own work. Somebody running the platform tracks everybody's from
التقدّم instead, and was being offered both — one of which is almost always empty for
them, since they are not the one answering.

A group cannot express this. The AZM hierarchy flows upward — a manager implies a
reviewer implies a user — so any group that shows the page to an answerer shows it to a
manager too. It is said here instead, in the one place every menu listing passes
through, so the page is left out of the sidebar, the app menu and the command palette
alike rather than only the first of those.
"""
from odoo import api, models

# {menu xml id: the group whose holders are not offered it}
NOT_OFFERED_TO = {
    "azm_platform.menu_my_work": "azm_operating_model.azm_group_manager",
}


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    @api.model
    def _azm_withheld_menu_ids(self):
        """Menus this user is not offered despite having the group that carries them."""
        withheld = set()
        for xmlid, group in NOT_OFFERED_TO.items():
            if not self.env.user.has_group(group):
                continue
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                withheld.add(menu.id)
        return withheld

    @api.model
    def _visible_menu_ids(self, debug=False):
        # super() is the cached one and stays so; this is a set difference over a
        # frozenset of ids, and has_group is itself cached per user
        visible = super()._visible_menu_ids(debug=debug)
        withheld = self._azm_withheld_menu_ids()
        return visible - withheld if withheld else visible
