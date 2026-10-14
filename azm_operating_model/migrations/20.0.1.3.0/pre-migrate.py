"""Financial model answers move from one form per requirement (state + texts + table) to real questions.

Keep the old answers aside before the new computed fields take over their columns; post-migrate
turns them into answers of the «مدى التطبيق الحالي» / «وسيلة التنفيذ» / «التوجه المستهدف» questions."""


def migrate(cr, version):
    cr.execute("SELECT 1 FROM information_schema.columns WHERE table_name = 'azm_fin_answer' AND column_name = 'gap'")
    if not cr.fetchone():
        return
    cr.execute("DROP TABLE IF EXISTS azm_fin_answer_legacy")
    cr.execute("""
        CREATE TABLE azm_fin_answer_legacy AS
        SELECT id, state, impl, current, gap, future, reason
          FROM azm_fin_answer
         WHERE state IS NOT NULL
    """)
