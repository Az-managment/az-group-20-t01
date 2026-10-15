"""إضافات DEV15 — الخزينة والأصول والضرائب.

  FIN-042  سجل الحسابات البنكية والمفوضين: الحساب والبنك والعملة والغرض والمفوَّض
           وحدّ تفويضه ومن يعتمد الفتح أو الإغلاق وتاريخهما. المطابقة والبنود
           المعلقة كانتا مغطّاتين؛ الحسابات نفسها لم تكن.
  FIN-051  أحداث الأصل: كان فيها «استبعاد» وأُضيف «بيع» و«شطب» و«انخفاض في القيمة».
  FIN-056  معاملة ضريبة المدخلات وتوزيعها بين نشاط خاضع وآخر معفى.

ولم يُضف شيء للأصول تحت التنفيذ: FIN-050 يغطّيها.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["azm.fin.module"]._load_catalogue()
    if "azm.artifact" in env:
        env["azm.artifact"]._register_all()
    _logger.info("كتالوج المالي أُعيد تحميله لإضافات DEV15")
