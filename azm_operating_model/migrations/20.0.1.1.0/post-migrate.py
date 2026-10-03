from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Per-user visibility: keep existing people working after the upgrade.

    * every entity gets, as allowed users, the people who already prepared,
      reviewed or created its assessments;
    * assessments move to the company of their entity.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["azm.entity"]._azm_grant_existing_users()
    assessments = env["azm.assessment"].with_context(active_test=False).search([("entity_id.company_id", "!=", False)])
    for rec in assessments:
        if rec.company_id != rec.entity_id.company_id:
            rec.company_id = rec.entity_id.company_id
    # the reference sequence is shared by every company (assessments now take their entity's company)
    sequence = env.ref("azm_operating_model.azm_assessment_sequence", raise_if_not_found=False)
    if sequence:
        sequence.company_id = False
