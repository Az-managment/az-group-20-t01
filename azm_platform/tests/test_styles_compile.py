"""هل تُترجم أنماطنا أصلًا؟

ساس يُترجم حزمة الواجهة كلها دفعةً واحدة، فخطأ في ملف واحد من ملفاتنا لا يُسقط
ذلك الملف وحده: يُسقط الحزمة، فتعود ورقة أنماط فيها رسالة الخطأ بدل مليون ونصف
من الأحرف، ويفتح المستخدم أودو كلها بلا تنسيق.

وهذا ما وقع: ‎width: min(760px, 100%)‎ — وهي CSS صحيحة — يحسبها ساس بنفسه ويرفض
خلط الوحدتين. الحزمة سقطت، ولم يسقط اختبار واحد، لأن أحدًا لم يكن يسأل عمّا
إذا كانت تُترجم.

الاختبار يبني الحزمة ويبحث فيها عن صنف من كل ملف من ملفاتنا: إن سقطت الترجمة
لم يكن فيها شيء منها.
"""
from odoo.tests import TransactionCase, tagged

# صنف من كل ورقة أنماط لنا، شاهدٌ على أنها بلغت الحزمة
SENTINELS = [
    "o_azm_sidebar",         # azm_platform/scss/azm_backend
    "o_azm_mywork_hero",     # azm_platform/my_work
    "o_azm_qr_hero",         # azm_operating_model/question_review
    "o_azm_qs_card_head",    # azm_operating_model/question_stats
    "o_azm_q_review",        # azm_operating_model/fin_workspace
]


@tagged("post_install", "-at_install")
class TestOurStylesReachTheBundle(TransactionCase):

    def test_the_backend_stylesheet_is_whole(self):
        attachments = self.env["ir.attachment"].sudo()
        bundle = self.env["ir.qweb"]._get_asset_bundle(
            "web.assets_backend", assets_params={})
        bundle.css()
        sheet = attachments.search(
            [("name", "like", "%assets_backend%"), ("name", "like", "%.css")],
            limit=1, order="id desc")
        self.assertTrue(sheet, "لم تُبنَ ورقة أنماط أصلًا")
        css = sheet.raw.decode()
        missing = [s for s in SENTINELS if s not in css]
        self.assertFalse(missing, (
            "سقطت ترجمة الحزمة أو سقطت منها أنماطنا: %s — "
            "طول الورقة %s حرفًا" % (", ".join(missing), len(css))))
