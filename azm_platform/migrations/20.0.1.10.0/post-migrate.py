import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Render the operating model books that were filed as HTML.

    A build installed with --test-enable renders reports as HTML
    (ir_actions_report._pre_render_qweb_pdf falls back unless the context asks
    otherwise), and the install hook filed that HTML under a .pdf name with an
    application/pdf mimetype: the book looked right in the list, carried a
    plausible size, and opened as garbage. The hook now forces a real render;
    the books already filed are repaired here.
    """
    env = api.Environment(cr, SUPERUSER_ID, {"tracking_disable": True})
    if "documents.document" not in env or "azm.assessment" not in env:
        return
    report = env.ref("azm_operating_model.azm_assessment_report_book", raise_if_not_found=False)
    if not report:
        return
    books = env["documents.document"].sudo().with_context(active_test=False).search(
        [("name", "=like", "% Operating Model Book.pdf")])
    for book in books:
        if bytes(book.raw or b"")[:4] == b"%PDF":
            continue
        assessment = env["azm.assessment"].sudo().search(
            [("company_id", "=", book.company_id.id)], limit=1)
        if not assessment:
            continue
        try:
            content, content_type = report.with_context(force_report_rendering=True)._render(
                report.report_name, assessment.ids)
        except Exception:  # noqa: BLE001 - one bad book must not stop the upgrade
            _logger.warning("Could not re-render %s", book.name, exc_info=True)
            continue
        if content_type != "pdf":
            _logger.warning("%s still does not render as a PDF; left as it is.", book.name)
            continue
        book.write({"raw": content, "mimetype": "application/pdf"})
        _logger.info("Re-rendered %s", book.name)
