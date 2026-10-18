"""تنزيل بنك الأسئلة ملفَّ إكسل.

الملف يُبنى في النموذج ويُختبر هناك؛ وهذا يسلّمه وحسب. والحراسة في الموضعين:
المسار لا يُفتح بالرابط لغير مدير النموذج، ولو عرفه.

وترويسات التسليم تُبنى في دالّة مستقلة لأن ما سقط فيها سقط عند الطلب لا عند
التحميل: استُدعي content_disposition من حيث ليس، فمرّ الاستيراد وعاش الكود حتى
ضغط أحدهم الزر. الاختبار يستدعيها كما يستدعيها المسار.
"""
from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.http.stream import content_disposition

FILENAME = "azm_question_bank.xlsx"
CONTENT_TYPE = ("application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet")


def delivery_headers(content):
    """ترويسات الملف: نوعه، وطوله، واسمه حين يُحفظ."""
    return [
        ("Content-Type", CONTENT_TYPE),
        ("Content-Length", len(content)),
        ("Content-Disposition", content_disposition(FILENAME)),
    ]


class AzmQuestionExport(http.Controller):

    @http.route("/azm/question_bank.xlsx", type="http", auth="user")
    def question_bank_xlsx(self, **kw):
        try:
            content = request.env["azm.question.bank.export"].question_bank_xlsx()
        except UserError as err:
            # لمن ليس له: لا ملف ولا رسالة تفصح عمّا خلفه
            raise Forbidden() from err
        return request.make_response(content, headers=delivery_headers(content))
