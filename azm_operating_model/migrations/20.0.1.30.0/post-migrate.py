"""DEV17 — تمييز منحة الطالب من منحة تمويل الكيان بالاسم.

القاموس في المستند يفرّق بينهما: «منحة دراسية للطالب» و«منحة تمويلية للكيان».
وكان المتطلبان «المنح الدراسية» و«المنح الممولة» — اسمان متقاربان لموضوعين
مختلفين: الأول خصم على رسوم طالب، والثاني تمويل مقيّد يُصرف على مشروع ويُقدَّم
عنه تقرير.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["azm.fin.module"]._load_catalogue()
    _logger.info("أُعيدت تسمية متطلبي المنح")
