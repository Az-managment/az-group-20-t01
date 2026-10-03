import json

from odoo import api, fields, models
from odoo.exceptions import ValidationError

# The six roles a question plays inside a requirement, in the order they appear.
# The first two are specific to the requirement; the last four are the standard
# scales every requirement repeats, and they are the ones the per-requirement
# roll-up (azm.fin.answer) is derived from.
ROLES = [
    ("main", "رئيسي"),
    ("followup", "سؤال تابع"),
    ("state", "الوضع الحالي"),
    ("impl", "وسيلة التنفيذ"),
    ("rule", "حالة القاعدة"),
    ("target", "التوجه المستهدف"),
]
STANDARD_ROLES = ("state", "impl", "rule", "target")

QTYPES = [
    ("select", "اختيار واحد"),
    ("multi", "اختيار متعدد"),
    ("number", "رقم"),
    ("table", "جدول"),
]

# Options that are not a real answer, same meaning as azm.option.kind on the
# procurement side: "لا أعرف" and "غير مدرج" leave the question unknown, so the
# follow-ups that depend on it stay hidden.
OPTION_KINDS = [
    ("normal", "إجابة"),
    ("unknown", "لا أعرف"),
    ("not_listed", "غير مدرج"),
    ("none", "لا يوجد"),
    ("na", "لا ينطبق"),
]


class AzmFinTopic(models.Model):
    _name = "azm.fin.topic"
    _description = "موضوع فرعي مالي"
    _order = "module_sequence, sequence, id"
    _rec_names_search = ("name", "code")

    code = fields.Char("الكود", required=True, index=True)
    name = fields.Char("الموضوع الفرعي", required=True, translate=True)
    module_id = fields.Many2one("azm.fin.module", "الموديول", required=True,
                                ondelete="cascade", index=True)
    module_sequence = fields.Integer(related="module_id.sequence", store=True,
                                     string="ترتيب الموديول")
    sequence = fields.Integer(default=10)
    requirement_ids = fields.One2many("azm.fin.requirement", "topic_id", string="المتطلبات")
    requirement_count = fields.Integer("عدد المتطلبات", compute="_compute_counts")
    opening_question_ids = fields.One2many("azm.fin.opening.question", "topic_id",
                                           string="الأسئلة الافتتاحية")
    opening_question_count = fields.Integer("عدد الأسئلة الافتتاحية", compute="_compute_counts")
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint("UNIQUE(code)", "كود الموضوع لازم يكون فريد.")

    @api.depends("requirement_ids", "opening_question_ids")
    def _compute_counts(self):
        for topic in self:
            topic.requirement_count = len(topic.requirement_ids)
            topic.opening_question_count = len(topic.opening_question_ids)

    @api.depends("code", "name")
    def _compute_display_name(self):
        for topic in self:
            topic.display_name = f"[{topic.code}] {topic.name}" if topic.code else topic.name


class AzmFinRequirement(models.Model):
    _inherit = "azm.fin.requirement"

    topic_id = fields.Many2one("azm.fin.topic", "الموضوع الفرعي", ondelete="set null", index=True)
    question_ids = fields.One2many("azm.fin.question", "requirement_id", string="الأسئلة")
    question_count = fields.Integer("عدد الأسئلة", compute="_compute_question_count")

    @api.depends("question_ids")
    def _compute_question_count(self):
        for req in self:
            req.question_count = len(req.question_ids)


class AzmFinQuestion(models.Model):
    _name = "azm.fin.question"
    _description = "سؤال النموذج المالي"
    # The engine only counts the answer of a question that was visible given the
    # answers of EARLIER questions, so a trigger has to sort before whatever
    # depends on it. `sequence` carries the Qnnn number from the catalogue, which
    # already guarantees that.
    _order = "module_sequence, requirement_sequence, sequence, id"
    _rec_names_search = ("label", "code")

    requirement_id = fields.Many2one("azm.fin.requirement", "المتطلب", required=True,
                                     ondelete="cascade", index=True)
    module_id = fields.Many2one(related="requirement_id.module_id", store=True, string="الموديول")
    module_sequence = fields.Integer(related="requirement_id.module_sequence", store=True,
                                     string="ترتيب الموديول")
    requirement_sequence = fields.Integer(related="requirement_id.sequence", store=True,
                                          string="ترتيب المتطلب")
    topic_id = fields.Many2one(related="requirement_id.topic_id", store=True,
                               string="الموضوع الفرعي")
    key = fields.Char("المفتاح", required=True,
                      help="المعرّف المحلي داخل المتطلب (Q001)، المستخدم في شروط الظهور.")
    code = fields.Char("الكود", compute="_compute_code", store=True, index=True)
    label = fields.Text("السؤال", required=True, translate=True)
    role = fields.Selection(ROLES, "الدور", required=True, default="main")
    qtype = fields.Selection(QTYPES, "شكل الإجابة", required=True, default="select")
    sequence = fields.Integer(default=10)
    condition = fields.Text("شرط الظهور (JSON)",
                            help='مثال: {"field": "Q003", "in": ["مطبق بالكامل", "مطبق جزئيًا"]}')
    unit = fields.Char("الوحدة")
    columns_json = fields.Text("أعمدة الجدول (JSON)")
    help_text = fields.Text("المطلوب في الإجابة", translate=True)
    text_label = fields.Char("خانة نص", translate=True,
                             help="عنوان خانة النص الحر المصاحبة للسؤال، إن وجدت.")
    response_type = fields.Char("نوع الرد")
    option_ids = fields.One2many("azm.fin.option", "question_id", string="الاختيارات")
    option_count = fields.Integer("عدد الاختيارات", compute="_compute_option_count")
    active = fields.Boolean(default=True)

    _requirement_key_uniq = models.Constraint(
        "UNIQUE(requirement_id, key)", "المفتاح مكرر في نفس المتطلب.")

    @api.depends("requirement_id.code", "key")
    def _compute_code(self):
        for question in self:
            req_code = question.requirement_id.code
            question.code = f"{req_code}/{question.key}" if req_code and question.key else False

    @api.depends("option_ids")
    def _compute_option_count(self):
        for question in self:
            question.option_count = len(question.option_ids)

    @api.depends("code", "label")
    def _compute_display_name(self):
        for question in self:
            question.display_name = f"[{question.code}] {question.label or ''}"[:120]

    @api.constrains("condition", "key", "sequence")
    def _check_condition(self):
        """The condition must be valid JSON and must point backwards.

        The engine only sees the answers of questions that sort BEFORE the one it
        is evaluating, so a condition naming a later question would never fire —
        silently, with the follow-up simply never appearing. The catalogue is
        machine-generated, so this is checked here rather than trusted.
        """
        for question in self.filtered("condition"):
            try:
                condition = json.loads(question.condition)
            except ValueError as error:
                raise ValidationError(
                    self.env._("شرط الظهور في %(code)s مش JSON صحيح: %(error)s",
                               code=question.code, error=error)) from error
            field = (condition or {}).get("field")
            if not field:
                continue
            trigger = question.requirement_id.question_ids.filtered(lambda q: q.key == field)
            if not trigger:
                raise ValidationError(self.env._(
                    "شرط الظهور في %(code)s بيشير لسؤال غير موجود: %(field)s",
                    code=question.code, field=field))
            if trigger.sequence >= question.sequence:
                raise ValidationError(self.env._(
                    "شرط الظهور في %(code)s بيشير لسؤال لاحق (%(field)s)؛ المحرك "
                    "بيشوف إجابات الأسئلة السابقة بس، فالسؤال مش هيظهر أبدًا.",
                    code=question.code, field=field))

    def _columns(self):
        self.ensure_one()
        return json.loads(self.columns_json or "[]")

    def _engine_dict(self):
        """The plain dict the visibility engine works on."""
        self.ensure_one()
        return {
            "id": self.id,
            "key": self.key,
            "qtype": self.qtype,
            "role": self.role,
            "sequence": self.sequence,
            "condition": json.loads(self.condition) if self.condition else None,
        }


class AzmFinOption(models.Model):
    _name = "azm.fin.option"
    _description = "اختيار إجابة مالي"
    _order = "sequence, id"

    name = fields.Char("الاختيار", required=True, translate=True)
    question_id = fields.Many2one("azm.fin.question", "السؤال", required=True,
                                  ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    kind = fields.Selection(OPTION_KINDS, "النوع", default="normal", required=True)
    active = fields.Boolean(default=True)


class AzmFinOpeningQuestion(models.Model):
    _name = "azm.fin.opening.question"
    _description = "سؤال افتتاحي مالي"
    _order = "topic_id, sequence, id"
    _rec_names_search = ("question", "node")

    node = fields.Char("المعرّف", required=True, index=True)
    topic_id = fields.Many2one("azm.fin.topic", "الموضوع الفرعي", required=True,
                               ondelete="cascade", index=True)
    module_id = fields.Many2one(related="topic_id.module_id", store=True, string="الموديول")
    axis_code = fields.Char("كود المحور", index=True)
    axis = fields.Char("المحور", translate=True)
    stage = fields.Char("المرحلة", translate=True)
    question = fields.Text("السؤال الافتتاحي", required=True, translate=True)
    output = fields.Char("المخرج", translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _node_uniq = models.Constraint("UNIQUE(node)", "معرّف السؤال الافتتاحي لازم يكون فريد.")

    @api.depends("node", "question")
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"[{record.node}] {record.question or ''}"[:120]
