"""أسئلة أُضيفت إلى دورة المشتريات — يُعاد تحميل كتالوجها ليصل التغيير.

الكتالوج لا يُحمَّل مع تحديث الموديول: يُستدعى عند التثبيت وفي هجرة تطلبه. وبدون
هذا السطر تبقى الحقول الجديدة في ملف JSON ولا تصل إلى قاعدة البيانات.

الأسئلة المضافة (REQ: نوع الشراء ومساره وبيانات الطلب، VEN: منع تكرار المورد)
صياغتها مسودة تنتظر اعتماد صاحب العملية؛ موضعها ومفاتيحها هي ما ثُبّت هنا.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["azm.stage"]._load_catalogue()
    # السؤال الجديد مخرَج يُرقَّم: بدون هذا يبقى السجل متخلّفًا عن الكتالوج،
    # ويظل أول تسجيل لاحق يُصدر أكوادًا جديدة حيث لا يُتوقع أن يُصدر شيئًا.
    if "azm.artifact" in env:
        env["azm.artifact"]._register_all()

    added = env["azm.question"].sudo().search_count(
        [("key", "in", ("purchase_type", "purchase_route", "request_fields"))])
    _logger.info("كتالوج المشتريات أُعيد تحميله؛ أسئلة طلب الاحتياج الجديدة: %s", added)
