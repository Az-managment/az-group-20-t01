"""DEV03 — الدور الذي كان في خانة الضابط التعويضي يُنقل إلى خانته، ولا يُفترض ضابطًا.

وتُعيد هذه الهجرة تحميل الكتالوج، فهو لا يُحمَّل مع تحديث الموديول: تغييرات
DEV04 (العملة والنطاق والسريان والأساس والبديل) وDEV03 (قائمة الضوابط) تبقى في
ملف JSON ولا تصل إلى قاعدة البيانات بدون هذا.

كان عمود «الضابط البديل» في FIN-005/Q003 يعرض أدوارًا وظيفية، فسُجّل فيه أشخاص
حيث يُنتظر إجراء: «الضابط البديل: المدير المالي». والمدير المالي ليس ضابطًا، وإنما
قد يكون مالكه.

فالدور يُنقل إلى «مالك الضابط»، ويُترك «الضابط التعويضي» فارغًا ليكتبه من يعرفه.
المستند صريح في هذا: «لا يُحوّل دور وظيفي قديم في حقل الضابط التعويضي إلى إجراء
رقابي مفترض». واختراع إجراء لم يقله أحد أسوأ من ترك الخانة فارغة.

والإجابات المنقولة تُعلَّم بانتظار إعادة التأكيد (آلية DEV05 نفسها)، فتطلب الصفحة
من صاحبها مراجعتها بدل أن تمر بصمت.

آمن للتكرار: الصف الذي لا يحمل دورًا في تلك الخانة لا يُمس.
"""
import json
import logging

_logger = logging.getLogger(__name__)

CONTROL = 2        # موضع عمود الضابط التعويضي
OWNER = "مالك الضابط"


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api
    env = api.Environment(cr, SUPERUSER_ID, {})
    # الكتالوج لا يُعاد تحميله مع تحديث الموديول — يُستدعى عند التثبيت وفي هجرة
    # تطلبه فقط. فكل تغيير في fin_catalogue.json يحتاج هذا السطر ليصل، وبدونه
    # تبقى الأعمدة الجديدة (ضوابط DEV03 وعملات DEV04 وسريانها) في الملف وحده.
    env["azm.fin.module"]._load_catalogue()

    question = env["azm.fin.question"].sudo().search(
        [("requirement_id.code", "=", "FIN-005"), ("key", "=", "Q003")], limit=1)
    if not question:
        _logger.info("FIN-005/Q003 غير موجود؛ لا شيء يُنقل")
        return
    columns = question._columns()
    labels = [c.get("label") for c in columns]
    if OWNER not in labels or labels[CONTROL] != "الضابط التعويضي":
        _logger.info("الجدول ليس بالشكل المتوقع؛ لا شيء يُنقل")
        return
    owner_at = labels.index(OWNER)
    controls = set(columns[CONTROL].get("options") or [])

    moved = 0
    answers = env["azm.fin.qanswer"].sudo().search(
        [("question_id", "=", question.id), ("table_json", "!=", False)])
    for answer in answers:
        rows = json.loads(answer.table_json or "[]")
        touched = False
        for row in rows:
            while len(row) < len(columns):
                row.append("")
            said = (row[CONTROL] or "").strip()
            # قيمة ليست من قائمة الضوابط هي الدور القديم
            if said and said not in controls:
                if not (row[owner_at] or "").strip():
                    row[owner_at] = said
                row[CONTROL] = ""
                touched = True
                moved += 1
        if touched:
            answer.write({"table_json": json.dumps(rows, ensure_ascii=False),
                          "stale": True})
    _logger.info("DEV03: نُقل %s دورًا إلى «مالك الضابط»، والضابط متروك للمراجعة", moved)
