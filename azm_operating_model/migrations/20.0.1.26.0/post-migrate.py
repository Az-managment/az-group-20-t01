"""إضافات DEV11 وDEV13 وDEV18 — يُعاد تحميل الكتالوجان وتُرقَّم المخرجات.

  FIN-008  أبعاد التعليم: العام الدراسي والمرحلة والفصل الدراسي والموقع.
  FIN-019  فكّ حجز بقدر الفاتورة الجزئية، وسؤال الخصم المزدوج: هل يُخصم المبلغ
           نفسه أكثر من مرة وهو ينتقل من الطلب إلى الأمر إلى الفاتورة.
  FIN-081  جدول يعرّف كل مؤشر: تعريفه وصيغته ووحدته ومصدره ومالكه ومستهدفه ومن يراه.
  FIN-084  أعمدة التكامل: الاتجاه ومعرّف منع التكرار والتسوية ومعالجة الأخطاء والمسؤول.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["azm.stage"]._load_catalogue()
    env["azm.fin.module"]._load_catalogue()
    if "azm.artifact" in env:
        env["azm.artifact"]._register_all()
    _logger.info("الكتالوجان أُعيد تحميلهما وأُعيد ترقيم المخرجات")
