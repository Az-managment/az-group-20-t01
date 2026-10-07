"""What is waiting for somebody on the AZM home page.

The page used to open with a block of figures and a list of the reader's own tasks.
Neither says what to do next: a count of entities is context, and a task list is only
one of the four things that can be waiting. This gathers the rest — work sent back to
this reader, work waiting for their review, what is overdue, and what is open against
the entities they can see — so the page can lead with the things that need a decision.

Everything here is counted through the reader's own rights. A figure nobody may open
is not shown, rather than shown and then refused.
"""
from odoo import api, fields, models

# How many rows of each kind the page shows before it says "and n more".
ATTENTION_ROWS = 4


class AzmDashboard(models.AbstractModel):
    _inherit = "azm.dashboard"

    @api.model
    def _attention_overdue(self, company_ids):
        """This reader's own tasks whose deadline has passed."""
        Task = self.env.get("project.task")
        if Task is None or not Task.has_access("read"):
            return {"count": 0, "rows": []}
        domain = [("user_ids", "in", self.env.uid), ("is_closed", "=", False),
                  ("project_id", "!=", False),
                  ("date_deadline", "<", fields.Datetime.now())]
        found = Task.search(domain, order="date_deadline asc", limit=ATTENTION_ROWS)
        return {
            "count": Task.search_count(domain),
            "rows": [{
                "id": task.id,
                "res_model": "project.task",
                "title": task.name,
                "where": task.project_id.display_name or "",
                "when": fields.Date.to_string(task.date_deadline.date()) if task.date_deadline else "",
                "who": ", ".join(task.user_ids.mapped("name")),
                "priority": "high" if task.priority in ("2", "3") else "normal",
            } for task in found],
        }

    @api.model
    def _attention_reviews(self):
        """Assessments sent for review that this reader is the one to look at."""
        rows = self._my_work_reviews()
        return {
            "count": len(rows),
            "rows": [{
                "id": row["id"],
                "res_model": row["res_model"],
                "title": row.get("model_label") or row.get("name") or "",
                "where": row.get("entity") or "",
                "when": row.get("since") or "",
                "who": row.get("preparer") or "",
                "priority": "normal",
            } for row in rows[:ATTENTION_ROWS]],
        }

    @api.model
    def _attention_returned(self):
        """Parts a review sent back to this reader, which block the rest of their work."""
        rows = self._my_work_returned()
        return {
            "count": len(rows),
            "rows": [{
                "id": row.get("res_id"),
                "res_model": row.get("res_model"),
                "title": row.get("part") or row.get("note") or "",
                "where": row.get("entity") or "",
                "when": row.get("since") or "",
                "who": row.get("reviewer") or "",
                "priority": "high",
            } for row in rows[:ATTENTION_ROWS]],
        }

    @api.model
    def _attention_open_issues(self, company_ids):
        """What stands open against the entities in scope: procurement findings that a
        review has turned into tracked work, and financial requirements not yet met.

        Counted apart, because they are not the same thing and the page says so: a
        finding is tracked work with an owner, a gap is a requirement still unmet.
        """
        out = {"findings": None, "gaps": None}
        Finding = self.env.get("azm.finding")
        if Finding is not None and Finding.has_access("read"):
            out["findings"] = Finding.search_count([
                ("company_id", "in", company_ids),
                ("state", "not in", ("closed", "accepted")),
            ])
        Answer = self.env.get("azm.fin.answer")
        if Answer is not None and Answer.has_access("read"):
            out["gaps"] = Answer.search_count([
                ("company_id", "in", company_ids),
                ("applicable", "=", True),
                ("state", "in", ("partial", "unavailable")),
            ])
        return out

    @api.model
    def home_attention(self):
        """The four things that can be waiting, each with what the reader needs to act.

        Returned as separate lists rather than one merged feed: they are acted on in
        different places, and a single list would have to invent a ranking between a
        late task and an assessment waiting on a reviewer.
        """
        company_ids = self._companies().ids
        returned = self._attention_returned()
        reviews = self._attention_reviews()
        overdue = self._attention_overdue(company_ids)
        issues = self._attention_open_issues(company_ids)
        return {
            "returned": returned,
            "reviews": reviews,
            "overdue": overdue,
            "issues": issues,
            # what the page leads with is whatever actually has something in it
            "total": returned["count"] + reviews["count"] + overdue["count"],
            "scope": {
                "entities": len(company_ids),
                "label": self.env.companies[:1].name if len(company_ids) == 1 else "",
            },
        }
