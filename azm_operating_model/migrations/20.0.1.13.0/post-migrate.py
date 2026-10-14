"""Rename the risk rules to codes that name the answer they watch.

A rule used to be coded by its position among the rules of the same question, in the
order the catalogue happened to list them: `R-VEN-bank` and `R-VEN-bank-2`. Reordering
those two lines gave each the other's code, and since the loader matched a rule by its
code it then wrote one rule's text onto the other — carrying with it every finding a
reviewer had scored, treated and closed.

The code now names the trigger (`R-VEN-bank-03`), which is the same on every database
and does not move. This renames what is already stored rather than waiting for somebody
to reload the catalogue, and carries the findings with their rules.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    # The new code is derived from the records themselves — stage code, question key and
    # the position of the option that fires the rule — so the catalogue file is not read
    # and a hand-edited rule is renamed just as correctly as a loaded one.
    cr.execute("""
        SELECT r.id, r.code,
               'R-' || s.code || '-' || q.key || '-' || lpad(o.sequence::text, 2, '0')
          FROM azm_risk_rule r
          JOIN azm_stage s ON s.id = r.stage_id
          JOIN azm_question q ON q.id = r.question_id
          JOIN azm_option o ON o.id = r.trigger_option_id
    """)
    renames = [(new, old, rule_id) for rule_id, old, new in cr.fetchall() if old != new]
    if not renames:
        return
    # the findings first: they are matched to a rule by code, so they have to travel
    # with it, and azm_finding is unique on (assessment_id, code)
    for new, old, _rule_id in renames:
        cr.execute("UPDATE azm_finding SET code = %s WHERE code = %s", (new, old))
    for new, _old, rule_id in renames:
        cr.execute("UPDATE azm_risk_rule SET code = %s WHERE id = %s", (new, rule_id))
    _logger.info("AZM: renamed %s risk rules to trigger-based codes", len(renames))
