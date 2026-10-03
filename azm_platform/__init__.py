from . import models
from . import controllers


def _azm_post_init(env):
    """Link Operating Model entities to Odoo companies when the names match."""
    env['azm.entity']._azm_autolink_companies()
    # The AZM interfaces are designed light; web_enterprise would otherwise let
    # each desktop's dark mode decide.
    env['res.users.settings']._azm_force_light_theme()
