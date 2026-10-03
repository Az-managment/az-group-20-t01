from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Bring in the real financial questionnaire.

    * the catalogue grows a sub-topic level, 1,136 questions with their own
      options, the follow-up conditions and the opening questions;
    * the 167 requirements move onto the spreadsheet's 19 modules. They are
      matched by code and only ever written to, never deleted and recreated, so
      no azm.fin.answer is orphaned;
    * the modules the new taxonomy leaves empty are archived by the loader, not
      deleted, because approved versions still name them;
    * assessments that already exist get their per-question answer rows, which
      _ensure_qanswers only creates on create().

    No raw SQL: azm.fin.answer.module_id / module_sequence are stored relateds
    through requirement_id and drive _order, so a SQL update of the requirement
    would leave every answer mis-sorted with no error.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["azm.fin.module"]._load_catalogue()
    env["azm.fin.assessment"].with_context(active_test=False).search([])._ensure_qanswers()
