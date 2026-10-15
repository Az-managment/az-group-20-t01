import json

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import file_open

# Answer profiles (قوالب الإجابة) — used to route requirements to the output documents
PROFILES = {
    "L": ("حصر مرجعي", "Reference list", "جدول عناصر وأكواد وجهات مستفيدة"),
    "C": ("قاعدة حساب", "Calculation rule", "مكوّن ومعادلة وشرائح ومثال"),
    "W": ("دورة عمل", "Workflow", "خطوات ومنفّذ ومراجع ومخرج"),
    "A": ("صلاحيات ورقابة", "Authority & control", "منشئ ومراجع ومعتمد وفصل مهام"),
    "R": ("تقرير أو مؤشر", "Report / KPI", "حقول وأبعاد ومصدر ودورية"),
    "I": ("تكامل أو ترحيل", "Integration", "مصدر ووجهة وحقول ومطابقة"),
    "P": ("سياسة وتوقيت", "Policy & timing", "نطاق وقاعدة وتاريخ ومعتمد"),
}
PROFILE_SELECTION = [(k, f"{k} · {v[0]}") for k, v in PROFILES.items()]

# Applicability (نطاق الانطباق): ALL = every entity, the others need the entity to have that activity
SCOPES = {
    "ALL": "كل الكيانات",
    "EDU": "الكيانات التعليمية",
    "ACA": "ذات النشاط الأكاديمي",
    "WORK": "ذات العاملين والرواتب",
    "STOCK": "ذات المخزون",
    "PRJ": "ذات المشروعات",
    "REAL": "ذات العقارات",
    "LEASE": "ذات الإيجارات",
    "GRANT": "ذات المنح",
    "GROUP": "على مستوى المجموعة",
}
SCOPE_SELECTION = list(SCOPES.items())

# Requirement status, derived from the «مدى التطبيق الحالي» question (or «لا ينطبق» on the line)
STATES = [
    ("full", "مطبّق بالكامل"),
    ("partial", "مطبّق جزئيًا"),
    ("unavailable", "غير منفذ"),
    ("unknown", "لا أعرف"),
    ("na", "لا ينطبق"),
]
STATUS_OPTIONS = {"مطبق بالكامل": "full", "مطبق جزئيًا": "partial", "غير منفذ": "unavailable", "لا أعرف": "unknown"}

# DEV02 — أربع حقائق، أربعة حقول.
#
# الحقل الواحد `state` كان يحمل ثلاثًا منها: الانطباق («لا ينطبق») والتنفيذ
# («مطبّق بالكامل») وحالة المعرفة («لا أعرف»)، وسطر واحد كان يمحو إحداها بالأخرى:
#     line.state = "na" if line.na else state
# فمن يُعلن متطلبًا غير منطبق يفقد ما كان قد سجّله عن تنفيذه. وهي حقائق مستقلة:
# متطلب قد لا ينطبق وقد كان يُنفَّذ، وآخر ينطبق ولا يُعرف تنفيذه.
APPLICABILITY = [
    ("yes", "منطبق"),
    ("no", "لا ينطبق"),
    ("undetermined", "قيد التحديد"),
]
EXECUTION = [
    ("full", "مطبّق بالكامل"),
    ("partial", "مطبّق جزئيًا"),
    ("none", "لا يُنفَّذ"),
    ("unknown", "غير معلوم"),
]
AUTOMATION = [
    ("system", "نظام"),
    ("manual", "يدوي"),
    ("mixed", "مختلط"),
    ("unknown", "غير معلوم"),
]
EVIDENCE = [
    ("not_required", "غير مطلوب"),
    ("missing", "غير مرفق"),
    ("unverified", "مرفق غير متحقق"),
    ("verified", "متحقق"),
]
# أي خيارات «وسيلة التنفيذ» تُقرأ نظامًا وأيها يدويًا. Excel أداة لا نظامًا —
# قرار محتوى لا هندسة، ومرفوع لصاحب العملية؛ تغييره هنا يغيّر التصنيف كله.
AUTOMATION_SYSTEM = {"النظام الحالي", "SAP"}
AUTOMATION_MANUAL = {"يدوي أو ورقي", "Excel", "لا يوجد نظام"}

# Question roles: the requirement-specific questions, then the 4 unified V3 status questions
ROLES = [
    ("main", "رئيسي"),
    ("follow", "سؤال تابع"),
    ("status", "الوضع الحالي"),
    ("impl", "وسيلة التنفيذ"),
    ("rule", "حالة القاعدة"),
    ("target", "التوجه المستهدف"),
]
QTYPES = [("select", "اختيار واحد"), ("multi", "اختيار متعدد"), ("table", "جدول"), ("number", "رقم")]
# «أخرى» لا «غير مدرج»: المستند يطلب أن يقرأها المجيب دعوةً إلى التوضيح لا
# إعلانًا بأن إجابته خارج القائمة. والنوع not_listed باقٍ كما هو، فهو ما
# يقرؤه المحرك ليعرف أن الإجابة ليست من المعروض.
OPTION_KINDS = [("unknown", "لا أعرف"), ("not_listed", "أخرى"), ("none", "لا يوجد")]
FALLBACK_KINDS = ("unknown", "not_listed", "none")

CATALOGUE = "azm_operating_model/data/fin_catalogue.json"

# The text boxes of the unified questions are answered from lists ("أخرى" opens a free-text detail)
OTHER = "أخرى"
NOTE_LISTS = {
    "تغطية النظام والمشاكل الحالية": [
        "مغطى بالكامل في النظام", "جزء من العمل خارج النظام (Excel أو ورقي)", "إدخال يدوي متكرر",
        "تأخير في التنفيذ أو الاعتماد", "أخطاء متكررة تحتاج تصحيح", "غياب التوثيق أو السياسة المكتوبة",
        "عدم وضوح المسؤوليات", "لا يوجد فصل بين المهام", "صعوبة استخراج التقارير", "عدم تكامل بين الأنظمة",
        "اختلاف التطبيق بين الكيانات", OTHER],
    "التغييرات المطلوبة والأولوية": [
        "أتمتة العملية في النظام", "توحيد القاعدة على مستوى المجموعة", "توثيق واعتماد السياسة",
        "تعديل مستويات الاعتماد", "تحقيق الفصل بين المهام", "تكامل مع نظام آخر", "تقارير ومؤشرات متابعة",
        "تدريب المستخدمين", "إعادة تصميم الإجراء بالكامل", OTHER],
}
PRIORITY_NOTES = {"التغييرات المطلوبة والأولوية"}
PRIORITIES = [("high", "مرتفعة"), ("medium", "متوسطة"), ("low", "منخفضة")]
NA_REASONS = ["النشاط غير موجود بالكيان", "يُدار على مستوى المجموعة", "يُدار من جهة خارجية",
              "لا ينطبق على نوع الكيان", "مؤجل لمرحلة لاحقة", "سبب آخر"]


class AzmFinModule(models.Model):
    _name = "azm.fin.module"
    _description = "موديول النموذج المالي الموحد"
    _order = "sequence, id"

    name = fields.Char("الموديول", required=True, translate=True)
    code = fields.Char("الكود", required=True, index=True)
    full_code = fields.Char("الكود الكامل", compute="_compute_full_code")
    sequence = fields.Integer(default=10)
    topic_ids = fields.One2many("azm.fin.topic", "module_id", string="الموضوعات")
    requirement_ids = fields.One2many("azm.fin.requirement", "module_id", string="المتطلبات")
    requirement_count = fields.Integer("عدد المتطلبات", compute="_compute_counts")
    question_count = fields.Integer("عدد الأسئلة", compute="_compute_counts")
    topic_count = fields.Integer("عدد الموضوعات", compute="_compute_counts")
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint("UNIQUE(code)", "كود الموديول لازم يكون فريد.")

    def _compute_full_code(self):
        for module in self:
            module.full_code = f"FIN.{module.code}"

    def _compute_counts(self):
        def counts(model):
            return dict(self.env[model]._read_group([("module_id", "in", self.ids)], ["module_id"], ["__count"]))
        reqs, questions, topics = (counts(m) for m in ("azm.fin.requirement", "azm.fin.question", "azm.fin.topic"))
        for module in self:
            module.requirement_count = reqs.get(module, 0)
            module.question_count = questions.get(module, 0)
            module.topic_count = topics.get(module, 0)

    @api.depends("code", "name")
    def _compute_display_name(self):
        for module in self:
            module.display_name = f"FIN.{module.code} · {module.name}" if module.code else module.name

    # ---------------------------------------------------------------- catalogue
    @api.model
    def _load_catalogue(self):
        """Create / update the model tree, requirements, questions and options from data/fin_catalogue.json.

        Idempotent: everything is matched by code (options by question + name), nothing answered is deleted;
        what disappeared from the catalogue is archived."""
        with file_open(CATALOGUE, "rb") as f:
            cat = json.load(f)
        ctx = {"active_test": False, "tracking_disable": True}

        Scope = self.env["azm.fin.scope"].with_context(**ctx)
        for seq, (code, name) in enumerate(SCOPES.items(), 1):
            if code == "ALL":
                continue
            scope = Scope.search([("code", "=", code)])
            vals = {"name": name, "sequence": seq}
            scope.write(vals) if scope else Scope.create({"code": code, **vals})

        # modules
        Module = self.with_context(**ctx)
        existing = {m.code: m for m in Module.search([])}
        modules = {}
        for seq, m in enumerate(cat["modules"], 1):
            vals = {"name": m["name"], "sequence": seq * 10, "active": True}
            module = existing.get(m["code"])
            if module:
                module.write(vals)
            else:
                module = Module.create({"code": m["code"], **vals})
            modules[m["code"]] = module

        # topics + opening questions
        Topic = self.env["azm.fin.topic"].with_context(**ctx)
        existing = {t.code: t for t in Topic.search([])}
        topics = {}
        for seq, t in enumerate(cat["topics"], 1):
            vals = {"name": t["name"], "module_id": modules[t["module"]].id, "sequence": seq, "active": True}
            topic = existing.get(t["code"])
            if topic:
                topic.write(vals)
            else:
                topic = Topic.create({"code": t["code"], **vals})
            topics[t["code"]] = topic
        Topic.search([("code", "not in", list(topics))]).write({"active": False})

        Prompt = self.env["azm.fin.prompt"].with_context(**ctx)
        existing = {p.code: p for p in Prompt.search([])}
        new_prompts = []
        for t in cat["topics"]:
            for seq, p in enumerate(t["prompts"], 1):
                vals = {"topic_id": topics[t["code"]].id, "sequence": seq, "axis": p["axis"],
                        "axis_name": p["axis_name"], "stage": p["stage"], "question": p["question"],
                        "output": p["output"]}
                prompt = existing.get(p["code"])
                if prompt:
                    changed = {k: v for k, v in vals.items() if (prompt[k].id if k == "topic_id" else prompt[k]) != v}
                    if changed:
                        prompt.write(changed)
                else:
                    new_prompts.append({"code": p["code"], **vals})
        Prompt.create(new_prompts)

        # requirements
        Req = self.env["azm.fin.requirement"].with_context(**ctx)
        existing = {r.code: r for r in Req.search([])}
        reqs = {}
        per_module = {}
        for r in cat["requirements"]:
            per_module[r["module"]] = per_module.get(r["module"], 0) + 1
            vals = {
                "module_id": modules[r["module"]].id, "topic_id": topics[r["topic"]].id,
                "sequence": per_module[r["module"]], "req_id": r["req_id"], "title": r["title"],
                "question": r["question"], "profile": r["profile"], "scope_code": r["scope"],
                "pack": r["pack"], "owner": r["owner"], "response_type": r["response_type"], "active": True,
            }
            req = existing.get(r["code"])
            if req:
                req.write(vals)
            else:
                req = Req.create({"code": r["code"], **vals})
            reqs[r["code"]] = req
        Req.search([("code", "not in", list(reqs))]).write({"active": False})

        # questions + options
        Question = self.env["azm.fin.question"].with_context(**ctx)
        Option = self.env["azm.fin.option"].with_context(**ctx)
        existing = {q.code: q for q in Question.search([])}
        options = {}
        for o in Option.search([]):
            options.setdefault(o.question_id.id, {})[o.name] = o
        seen, new_options = set(), []
        for r in cat["requirements"]:
            for seq, q in enumerate(r["questions"], 1):
                vals = {
                    "requirement_id": reqs[r["code"]].id, "key": q["key"], "sequence": seq, "role": q["role"],
                    "label": q["label"], "hint": q["hint"] or False, "qtype": q["qtype"], "unit": q["unit"] or False,
                    "columns_json": json.dumps(q["columns"], ensure_ascii=False) if q["columns"] else False,
                    "condition_json": json.dumps(q["condition"], ensure_ascii=False) if q["condition"] else False,
                    "note_label": q["note_label"] or False, "active": True,
                }
                question = existing.get(q["code"])
                if question:
                    changed = {k: v for k, v in vals.items()
                               if (question[k].id if k == "requirement_id" else question[k]) != v}
                    if changed:
                        question.write(changed)
                else:
                    question = Question.create({"code": q["code"], **vals})
                seen.add(q["code"])
                have = options.get(question.id, {})
                names = []
                for oseq, o in enumerate(q["options"], 1):
                    names.append(o["name"])
                    ovals = {"sequence": oseq, "kind": o["kind"] or False, "active": True}
                    opt = have.get(o["name"])
                    if opt:
                        if opt.sequence != oseq or (opt.kind or False) != ovals["kind"] or not opt.active:
                            opt.write(ovals)
                    else:
                        new_options.append({"question_id": question.id, "name": o["name"], **ovals})
                stale = [opt.id for name, opt in have.items() if name not in names and opt.active]
                if stale:
                    Option.browse(stale).write({"active": False})
        Option.create(new_options)
        Question.search([("code", "not in", list(seen))]).write({"active": False})

        # modules that are no longer part of the tree
        Module.search([("code", "not in", list(modules))]).write({"active": False})
        return True

    def action_reload_catalogue(self):
        self.env["azm.fin.module"].check_access("write")
        self._load_catalogue()
        # a requirement added here has no answer line on the assessments that already
        # exist, and one retired here must stop being counted
        self.env["azm.fin.assessment"]._ensure_all_answers()
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"type": "success", "message": "تم تحديث كتالوج النموذج المالي."}}


class AzmFinTopic(models.Model):
    _name = "azm.fin.topic"
    _description = "موضوع فرعي في النموذج المالي"
    _order = "sequence, id"
    _rec_names_search = ("name", "code")

    code = fields.Char("الكود", required=True, index=True)
    name = fields.Char("الموضوع الفرعي", required=True, translate=True)
    module_id = fields.Many2one("azm.fin.module", "الموديول", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    requirement_ids = fields.One2many("azm.fin.requirement", "topic_id", string="المتطلبات")
    prompt_ids = fields.One2many("azm.fin.prompt", "topic_id", string="الأسئلة الافتتاحية")
    requirement_count = fields.Integer("عدد المتطلبات", compute="_compute_counts")
    prompt_count = fields.Integer("عدد الأسئلة الافتتاحية", compute="_compute_counts")
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint("UNIQUE(code)", "كود الموضوع لازم يكون فريد.")

    def _compute_counts(self):
        reqs = dict(self.env["azm.fin.requirement"]._read_group([("topic_id", "in", self.ids)], ["topic_id"], ["__count"]))
        prompts = dict(self.env["azm.fin.prompt"]._read_group([("topic_id", "in", self.ids)], ["topic_id"], ["__count"]))
        for topic in self:
            topic.requirement_count = reqs.get(topic, 0)
            topic.prompt_count = prompts.get(topic, 0)

    @api.depends("code", "name")
    def _compute_display_name(self):
        for topic in self:
            topic.display_name = f"{topic.code} · {topic.name}" if topic.code else topic.name


class AzmFinPrompt(models.Model):
    _name = "azm.fin.prompt"
    _description = "سؤال افتتاحي مقترح (مسودة)"
    _order = "topic_id, sequence, id"

    code = fields.Char("الكود", required=True, index=True)
    topic_id = fields.Many2one("azm.fin.topic", "الموضوع", required=True, ondelete="cascade", index=True)
    module_id = fields.Many2one(related="topic_id.module_id", store=True, string="الموديول")
    sequence = fields.Integer(default=10)
    axis = fields.Char("كود المحور")
    axis_name = fields.Char("المحور")
    stage = fields.Selection([("current", "حصر الوضع الحالي"), ("design", "تصميم لاحق بعد المراجعة")], "المرحلة")
    question = fields.Text("السؤال الافتتاحي", required=True)
    output = fields.Char("المخرج")

    _code_uniq = models.Constraint("UNIQUE(code)", "كود السؤال الافتتاحي لازم يكون فريد.")


class AzmFinScope(models.Model):
    _name = "azm.fin.scope"
    _description = "نطاق انطباق مالي"
    _order = "sequence, id"

    name = fields.Char("النطاق", required=True, translate=True)
    code = fields.Char("الكود", required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint("UNIQUE(code)", "كود النطاق لازم يكون فريد.")


class AzmFinRequirement(models.Model):
    _name = "azm.fin.requirement"
    _description = "متطلب النموذج المالي الموحد"
    _order = "module_sequence, topic_sequence, sequence, id"
    _rec_names_search = ("title", "code", "req_id", "tree_ref", "question")

    code = fields.Char("الكود", required=True, index=True, help="الكود السابق (V3) مثل FIN-004 أو HRF-050.")
    req_id = fields.Char("Requirement ID", index=True)
    tree_ref = fields.Char(
        "مرجع الشجرة", compute="_compute_tree_ref", store=True, index=True,
        help="مكان المتطلب في الشجرة: الموضوع ثم ترتيب المتطلب فيه، مثل FIN.PUR.03.01. "
             "مرجع للتصفح يتغير مع إصدار النموذج؛ الهوية الثابتة هي Requirement ID.")
    module_id = fields.Many2one("azm.fin.module", "الموديول", required=True, ondelete="cascade", index=True)
    module_sequence = fields.Integer(related="module_id.sequence", store=True, string="ترتيب الموديول")
    topic_id = fields.Many2one("azm.fin.topic", "الموضوع الفرعي", ondelete="set null", index=True)
    topic_sequence = fields.Integer(related="topic_id.sequence", store=True, string="ترتيب الموضوع")
    sequence = fields.Integer(default=10)
    title = fields.Char("المتطلب", required=True, translate=True)
    question = fields.Text("السؤال الرئيسي", required=True, translate=True)
    profile = fields.Selection(PROFILE_SELECTION, "قالب الإجابة", required=True, default="P")
    scope_code = fields.Selection(SCOPE_SELECTION, "نطاق الانطباق", required=True, default="ALL")
    source = fields.Selection([("FIN", "مالية"), ("HRF", "مالية الموارد البشرية")], "المصدر",
                              compute="_compute_source", store=True)
    pack = fields.Char("حزمة الانطباق")
    owner = fields.Char("المالك المقترح")
    response_type = fields.Char("نوع الرد (V3)")
    question_ids = fields.One2many("azm.fin.question", "requirement_id", string="الأسئلة")
    question_count = fields.Integer("عدد الأسئلة", compute="_compute_question_count")
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint("UNIQUE(code)", "كود المتطلب لازم يكون فريد.")
    # tree_ref is what the tree, the breadcrumb, the PDF cover and the filed document
    # all name a requirement by, and it is computed from sibling rank — so inserting or
    # reordering a requirement could quietly give two of them the same name. It cannot
    # now: the database refuses it instead of filing two documents under one name.
    # Deferred to commit: reordering requirements inside a topic renumbers all of them,
    # and any permutation passes through a moment where two rows share a reference.
    # Postgres checks a plain UNIQUE row by row and would refuse the legal reorder; what
    # must never be true is the *end state* having duplicates.
    _tree_ref_uniq = models.Constraint(
        "UNIQUE(tree_ref) DEFERRABLE INITIALLY DEFERRED",
        "مرجع الشجرة مكرر؛ لا يمكن أن يحمل متطلبان نفس المرجع.")

    @api.depends("topic_id.code", "topic_id.requirement_ids.sequence", "module_id.code", "sequence")
    def _compute_tree_ref(self):
        """Model › module › topic › requirement: FIN.PUR.03.02 is the 2nd requirement of topic FIN.PUR.03.

        Numbered inside the topic (archived ones included, so a retired requirement never
        shifts the others).

        The rank depends on the siblings, so the whole topic has to recompute when any one
        of them moves — depending only on this record's own ``sequence`` left the others
        holding their old rank, which is a duplicate reference, and the reference names the
        tree leaf, the breadcrumb, the PDF cover and the filed document."""
        siblings = self.with_context(active_test=False).search(
            [("topic_id", "in", self.topic_id.ids)], order="sequence, id") if self.topic_id else self.browse()
        rank = {}
        for req in siblings:
            rank.setdefault(req.topic_id.id, []).append(req.id)
        for req in self:
            if req.topic_id.code and req.id in rank.get(req.topic_id.id, []):
                req.tree_ref = f"{req.topic_id.code}.{rank[req.topic_id.id].index(req.id) + 1:02d}"
            elif req.module_id.code:
                req.tree_ref = f"FIN.{req.module_id.code}.R{req.sequence:02d}"
            else:
                req.tree_ref = False

    @api.depends("code")
    def _compute_source(self):
        for req in self:
            req.source = "HRF" if (req.code or "").startswith("HRF") else "FIN"

    def _compute_question_count(self):
        counts = dict(self.env["azm.fin.question"]._read_group(
            [("requirement_id", "in", self.ids)], ["requirement_id"], ["__count"]))
        for req in self:
            req.question_count = counts.get(req, 0)

    @api.depends("tree_ref", "code", "title")
    def _compute_display_name(self):
        for req in self:
            ref = req.tree_ref or req.code
            req.display_name = f"{ref} · {req.title}" if ref else req.title


class AzmFinQuestion(models.Model):
    _name = "azm.fin.question"
    _inherit = ["azm.reviewable.question"]
    _description = "سؤال النموذج المالي الموحد"
    _azm_comment_field = "fin_question_id"
    _order = "module_sequence, requirement_id, sequence, id"
    _rec_names_search = ("label", "code", "tree_ref")

    code = fields.Char("كود السؤال", required=True, index=True)
    key = fields.Char("المفتاح", required=True, help="Q001، Q002 … داخل المتطلب؛ يستخدم في شروط الظهور.")
    requirement_id = fields.Many2one("azm.fin.requirement", "المتطلب", required=True, ondelete="cascade", index=True)
    tree_ref = fields.Char(related="requirement_id.tree_ref", store=True, index=True, string="مرجع الشجرة",
                           help="كود المتطلب/المستند الذي ينتمي إليه السؤال، مثل FIN.PUR.01.01.")
    module_id = fields.Many2one(related="requirement_id.module_id", store=True, string="الموديول")
    module_sequence = fields.Integer(related="requirement_id.module_sequence", store=True)
    topic_id = fields.Many2one(related="requirement_id.topic_id", store=True, string="الموضوع الفرعي")
    sequence = fields.Integer(default=10)
    role = fields.Selection(ROLES, "الدور", required=True, default="follow")
    label = fields.Char("السؤال", required=True, translate=True)
    hint = fields.Char("المطلوب في الإجابة", translate=True)
    qtype = fields.Selection(QTYPES, "شكل الإجابة", required=True, default="select")
    unit = fields.Char("الوحدة")
    columns_json = fields.Text("أعمدة الجدول (JSON)", help='[{"label": "الخطوة", "options": ["…"]}, {"label": "المنفذ"}]')
    condition_json = fields.Text("شرط الظهور (JSON)", help='{"q": "Q003", "in": ["مطبق بالكامل"]}')
    condition_text = fields.Char("شرط الظهور", compute="_compute_condition_text")
    note_label = fields.Char("خانة نص", help="عنوان خانة النص الإضافية تحت السؤال (إن وجدت).")
    option_ids = fields.One2many("azm.fin.option", "question_id", string="الاختيارات")
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint("UNIQUE(code)", "كود السؤال لازم يكون فريد.")

    @api.depends("condition_json")
    def _compute_condition_text(self):
        for q in self:
            cond = q._condition()
            q.condition_text = f"يظهر لو {cond['q']} = {' أو '.join(cond['in'])}" if cond else False

    @api.depends("code", "label")
    def _compute_display_name(self):
        for q in self:
            q.display_name = f"[{q.code}] {q.label}" if q.code else q.label

    def _condition(self):
        self.ensure_one()
        return json.loads(self.condition_json) if self.condition_json else None

    def _columns(self):
        self.ensure_one()
        return json.loads(self.columns_json) if self.columns_json else []

    # ------------------------------------------------------------------ DEV04
    def _check_rows(self, rows):
        """يرفض قيمة لا يمكن أن تكون صحيحة قبل أن تُحفظ.

        لم يكن هناك تحقق من شيء: خانة نوعها «رقم» كانت تقبل نصًّا، وخصمٌ بنسبة
        9999 يُحفظ كما هو، ومبلغ يُسجَّل بلا عملة فلا يُعرف أهو جنيه أم دولار.
        وهذه قيم تُبنى عليها مصفوفة صلاحيات.

        ما يُقرأ من تعريف العمود:
          type: number        → لا بد أن يكون رقمًا
          unit: "%"           → بين min و max، وافتراضهما 0 و100
          unit: "amount"      → يلزمه عمود عملة مملوء
          unit_column: "..."  → الوحدة مكتوبة في عمود آخر من الصف نفسه،
                                فيُقرأ منه أهذه نسبة أم مبلغ
        """
        self.ensure_one()
        columns = self._columns()
        if not columns:
            return
        index = {col.get("label"): i for i, col in enumerate(columns)}

        def cell(row, label):
            i = index.get(label)
            return (row[i] if i is not None and i < len(row) else "") or ""

        for number, row in enumerate(rows, start=1):
            for i, col in enumerate(columns):
                raw = (row[i] if i < len(row) else "") or ""
                text = str(raw).strip()
                if not text:
                    continue
                label = col.get("label") or ""
                if col.get("type") == "number":
                    try:
                        value = float(text.replace(",", ""))
                    except ValueError:
                        raise UserError(_(
                            "الصف %(row)s، «%(col)s»: القيمة «%(bad)s» ليست رقمًا.",
                            row=number, col=label, bad=text))
                    unit = col.get("unit")
                    if col.get("unit_column"):
                        said = cell(row, col["unit_column"]).strip()
                        if said == col.get("percent_value"):
                            unit = "%"
                        elif said == col.get("amount_value"):
                            unit = "amount"
                    if unit == "%":
                        low = col.get("min", 0)
                        high = col.get("max", 100)
                        if not low <= value <= high:
                            raise UserError(_(
                                "الصف %(row)s، «%(col)s»: النسبة %(bad)s خارج المدى "
                                "المسموح (%(low)s–%(high)s).",
                                row=number, col=label, bad=text, low=low, high=high))
                    elif unit == "amount":
                        holder = col.get("currency_column")
                        if holder and not cell(row, holder).strip():
                            raise UserError(_(
                                "الصف %(row)s، «%(col)s»: مبلغ بلا عملة. "
                                "املأ «%(cur)s» ليُعرف ما هذا المبلغ.",
                                row=number, col=label, cur=holder))
                elif col.get("type") == "date":
                    try:
                        fields.Date.from_string(text)
                    except (ValueError, TypeError):
                        raise UserError(_(
                            "الصف %(row)s، «%(col)s»: «%(bad)s» ليس تاريخًا.",
                            row=number, col=label, bad=text))
        self._check_ranges(rows, columns, index)

    def _check_ranges(self, rows, columns, index):
        """حدّان متداخلان للنطاق نفسه يعنيان موافقتين لمعاملة واحدة.

        «من 0 إلى 50 ألفًا يعتمدها المدير المالي» و«من 30 ألفًا إلى 100 يعتمدها
        الرئيس التنفيذي» تتركان مَن يصرف 40 ألفًا بين اعتمادين، ولا يقول الجدول
        أيهما. يُرفض التداخل ما لم يُعلن استثناءً صريحًا بأولوية.
        """
        spec = next((c for c in columns if c.get("range_from")), None)
        if not spec:
            return
        low_i, high_i = index.get(spec["range_from"]), index.get(spec.get("label"))
        if low_i is None or high_i is None:
            return
        scope_cols = [index[c] for c in (spec.get("range_scope") or []) if c in index]
        seen = {}
        for number, row in enumerate(rows, start=1):
            def at(i):
                return (row[i] if i < len(row) else "") or ""
            try:
                low = float(str(at(low_i)).replace(",", "") or 0)
                high = float(str(at(high_i)).replace(",", "") or 0)
            except ValueError:
                continue
            if high and high < low:
                raise UserError(_(
                    "الصف %(row)s: «إلى» أصغر من «من».", row=number))
            key = tuple(str(at(i)).strip() for i in scope_cols)
            for other_row, other_low, other_high in seen.get(key, []):
                if low < (other_high or low + 1) and other_low < (high or other_low + 1):
                    raise UserError(_(
                        "الصفّان %(a)s و%(b)s يتداخلان في النطاق نفسه، فلا يُعرف "
                        "أي اعتماد يسري على مبلغ يقع بينهما.",
                        a=other_row, b=number))
            seen.setdefault(key, []).append((number, low, high))

    def _schema(self):
        """Static description of the question for the workspace / engine."""
        self.ensure_one()
        return {
            "id": self.id, "code": self.code, "key": self.key, "role": self.role, "label": self.label,
            "hint": self.hint or "", "qtype": self.qtype, "unit": self.unit or "",
            "columns": self._columns(), "condition": self._condition(), "condition_text": self.condition_text or "",
            "note_label": self.note_label or "",
            "note_options": NOTE_LISTS.get(self.note_label or "", []),
            "has_priority": (self.note_label or "") in PRIORITY_NOTES,
            "options": [{"id": o.id, "name": o.name, "kind": o.kind or ""} for o in self.option_ids],
        }


class AzmFinOption(models.Model):
    _name = "azm.fin.option"
    _description = "اختيار لسؤال مالي"
    _order = "sequence, id"

    question_id = fields.Many2one("azm.fin.question", "السؤال", required=True, ondelete="cascade", index=True)
    name = fields.Char("الاختيار", required=True, translate=True)
    kind = fields.Selection(OPTION_KINDS, "نوع خاص",
                            help="لا أعرف / غير مدرج / لا يوجد: تظهر منفصلة، ولا تُجمع مع غيرها في الاختيار المتعدد.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)


class AzmEntity(models.Model):
    _inherit = "azm.entity"

    fin_scope_ids = fields.Many2many(
        "azm.fin.scope", "azm_entity_fin_scope_rel", "entity_id", "scope_id", string="أنشطة الكيان (النموذج المالي)",
        help="تحدد المتطلبات المالية التي تنطبق على الكيان، مثل: تعليمي، رواتب، مشروعات، عقارات.")
    fin_assessment_ids = fields.One2many("azm.fin.assessment", "entity_id", string="الإفادات المالية")

    @api.model
    def _azm_fin_default_scopes(self):
        """Group entities are educational: give them the education, academic and payroll scopes by default."""
        scopes = self.env["azm.fin.scope"].search([("code", "in", ("EDU", "ACA", "WORK"))])
        for entity in self.sudo().with_context(active_test=False).search([("fin_scope_ids", "=", False)]):
            entity.fin_scope_ids = [Command.set(scopes.ids)]
