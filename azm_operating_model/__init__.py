from . import controllers
from . import models


def _azm_post_init(env):
    env["azm.entity"]._azm_sync_companies()   # one entity per existing company
    env["azm.stage"]._load_catalogue()
    # unified financial model (النموذج المالي الموحد)
    env["azm.fin.module"]._load_catalogue()
    env["azm.entity"]._azm_fin_default_scopes()
    env["res.users.settings"]._azm_apply_light_theme()
