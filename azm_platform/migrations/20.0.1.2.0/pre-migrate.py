"""azm_platform_operating_model (the bridge) is now part of azm_platform.

Move the bridge's records (actions, menus, views, fields) to azm_platform so they are
updated instead of duplicated, and retire the old module.
"""


def migrate(cr, version):
    cr.execute("SELECT 1 FROM ir_module_module WHERE name = 'azm_platform_operating_model'")
    if not cr.fetchone():
        return
    cr.execute("""
        UPDATE ir_model_data d SET module = 'azm_platform'
         WHERE d.module = 'azm_platform_operating_model'
           AND NOT EXISTS (SELECT 1 FROM ir_model_data o WHERE o.module = 'azm_platform' AND o.name = d.name)
    """)
    cr.execute("DELETE FROM ir_model_data WHERE module = 'azm_platform_operating_model'")
    cr.execute("DELETE FROM ir_module_module_dependency WHERE name = 'azm_platform_operating_model'")
    cr.execute("DELETE FROM ir_module_module_dependency d USING ir_module_module m "
               "WHERE d.module_id = m.id AND m.name = 'azm_platform_operating_model'")
    cr.execute("""UPDATE ir_module_module SET state = 'uninstalled', latest_version = NULL, auto_install = false
                   WHERE name = 'azm_platform_operating_model'""")
