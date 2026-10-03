from . import models
from . import controllers


def _azm_post_init(env):
    """Link Operating Model entities to Odoo companies when the names match."""
    env['azm.entity']._azm_autolink_companies()
