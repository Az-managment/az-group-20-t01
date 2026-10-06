"""The seeded operating-model books were named .pdf whatever came out of the renderer.

Without wkhtmltopdf the report falls back to HTML, and a file of HTML called .pdf opens
as garbage — which reads as a corrupt file rather than as a missing renderer. The books
are re-rendered now that one is available; whatever comes back decides the name and the
type, so the file says what it holds.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    if "documents.document" not in env:
        return
    report = env.ref("azm_operating_model.azm_assessment_report_book", raise_if_not_found=False)
    if not report:
        return
    books = env["documents.document"].sudo().search(
        [("name", "=like", "% Operating Model Book.pdf")])
    for book in books:
        if bytes(book.raw or b"").startswith(b"%PDF"):
            continue
        assessment = env["azm.assessment"].sudo().search(
            [("company_id", "=", book.company_id.id)], limit=1)
        content, content_type = (None, None)
        if assessment:
            try:
                content, content_type = report._render(report.report_name, assessment.ids)
            except Exception:  # noqa: BLE001 - a book that will not render must not stop the upgrade
                _logger.warning("Could not re-render %s", book.name, exc_info=True)
        if content and content_type == "pdf":
            book.write({"raw": content, "mimetype": "application/pdf"})
            continue
        # still no pdf: the file keeps its bytes and stops claiming to be one
        vals = {"name": book.name[: -len(".pdf")] + ".html", "mimetype": "text/html"}
        if content:
            vals["raw"] = content
        book.write(vals)
        _logger.info("%s holds HTML, not a PDF: filed under its real type", book.name)
