"""Accepting the answers publishes what they produce.

An assessment's documents — its policies, procedures, authority matrices, the whole
book — are built from the answers and rebuilt whenever those change, which the cron
notices within the hour. That is right while the work is being done and wrong at the
moment it is signed off: the reviewer accepts, and what they accepted should be on the
shelf and in the entity's Documents folders, not an hour later.

Approval already changes every document's fingerprint — the state and the approval date
are part of what a document says — so there is nothing to force here. What this adds is
telling the queue to go now rather than when it next happens to look.
"""
import logging

from odoo import _, models

_logger = logging.getLogger(__name__)


class AzmPublishOnApproval(models.AbstractModel):
    """Shared by the two assessments, which approve in the same way."""
    _name = "azm.publish.on.approval"
    _description = "AZM publish on approval"

    def _azm_publish_accepted(self):
        """Queue the entity's documents and set the queue going.

        Queued rather than built here: an entity holds some two hundred and fifty
        documents and each is a PDF render, which is not something to do inside the
        click that accepted the answers. The cron is triggered rather than waited for,
        so they appear in Documents in the moment after rather than within the hour.
        """
        Pub = self.env.get("azm.doc.publication")
        if Pub is None:
            return self.env["azm.doc.publication"]
        companies = self.company_id
        if not companies:
            return Pub
        queued = Pub.sudo()._enqueue(companies)
        _logger.info("AZM: %s documents queued after approval of %s",
                     len(queued), ", ".join(self.mapped("name")))
        for record in self:
            record.sudo().message_post(body=_(
                "The answers were accepted. %s documents are being published to "
                "Documents.", len(queued)))
        return queued


class AzmAssessment(models.Model):
    _name = "azm.assessment"
    _inherit = ["azm.assessment", "azm.publish.on.approval"]

    def action_approve(self):
        result = super().action_approve()
        self._azm_publish_accepted()
        return result


class AzmFinAssessment(models.Model):
    _name = "azm.fin.assessment"
    _inherit = ["azm.fin.assessment", "azm.publish.on.approval"]

    def action_approve(self):
        result = super().action_approve()
        self._azm_publish_accepted()
        return result
