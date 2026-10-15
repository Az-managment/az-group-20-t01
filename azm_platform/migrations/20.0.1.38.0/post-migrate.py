"""يُعاد ترقيم المخرجات بعد كل تغيير في الكتالوج.

azm.artifact يعيش في azm_platform، وهجرات azm_operating_model تسبقه في الترقية —
فالحارس `if "azm.artifact" in env` فيها يسقط صامتًا ولا يُرقَّم شيء. والنتيجة أن
سجل الترميز يتخلّف عن الكتالوج: أسماء العقد فيه تبقى بصياغة قديمة، وأول تسجيل
لاحق يُصدر تغييرًا حيث لا يُتوقع.

فالترقيم يُطلب من هنا، حيث النموذج موجود بالتأكيد.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api
    env = api.Environment(cr, SUPERUSER_ID, {})
    count = env["azm.artifact"]._register_all()
    _logger.info("أُعيد ترقيم %s مخرجًا بعد تغيّر الكتالوج", count)
