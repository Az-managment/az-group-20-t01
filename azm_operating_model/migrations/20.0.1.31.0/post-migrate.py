"""DEV13 — القيد العكسي والحسابات الرقابية.

«افحص تغطية الحسابات الرقابية والعملات وإلغاء القيود والقيد العكسي وإعادة فتح
الفترة». إعادة فتح الفترة مغطّاة في FIN-078. والاثنان الآخران لم يكونا مذكورين
في بنك الأسئلة كله: صفر سؤال عن القيد العكسي، وصفر عن الحسابات الرقابية.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["azm.fin.module"]._load_catalogue()
    _logger.info("أُضيف القيد العكسي والحسابات الرقابية")
