def migrate(cr, version):
    """The unified financial model was a separate module (azm_financial_model);
    it is now part of azm_operating_model. Keep its data: hand its records over."""
    cr.execute("SELECT state FROM ir_module_module WHERE name = 'azm_financial_model'")
    row = cr.fetchone()
    if not row:
        return
    cr.execute("""
        UPDATE ir_model_data d SET module = 'azm_operating_model'
         WHERE d.module = 'azm_financial_model'
           AND NOT EXISTS (SELECT 1 FROM ir_model_data o
                            WHERE o.module = 'azm_operating_model' AND o.name = d.name)
    """)
    cr.execute("DELETE FROM ir_model_data WHERE module = 'azm_financial_model'")
    cr.execute("DELETE FROM ir_module_module_dependency WHERE name = 'azm_financial_model'")
    cr.execute("UPDATE ir_module_module SET state = 'uninstalled', latest_version = NULL "
               "WHERE name = 'azm_financial_model'")
