from . import models
from . import controllers


def _azm_post_init(env):
    """Link Operating Model entities to Odoo companies when the names match.

    The platform is the last module of the stack to install, so this is also
    where the development staff of az_group_base are put on their entities:
    az_group_base and azm_operating_model are both only dependencies of this
    module, nothing orders them against each other, and when az_group_base
    installs first there is no azm.entity to assign yet.
    """
    env['azm.entity']._azm_sync_companies()
    from odoo.addons.az_group_base.hooks import finish_dev_staff
    finish_dev_staff(env)
    from .hooks import describe_entities, load_dev_entity_data
    describe_entities(env)
    load_dev_entity_data(env)
