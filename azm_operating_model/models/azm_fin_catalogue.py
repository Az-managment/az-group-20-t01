import json

from odoo import Command, api, fields, models
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
OPTION_KINDS = [("unknown", "لا أعرف"), ("not_listed", "غير مدرج"), ("none", "لا يوجد")]
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
        self._load_catalogue()
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

    @api.depends("topic_id.code", "module_id.code", "sequence")
    def _compute_tree_ref(self):
        """Model › module › topic › requirement: FIN.PUR.03.02 is the 2nd requirement of topic FIN.PUR.03.

        Numbered inside the topic (archived ones included, so a retired requirement never shifts the others)."""
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
    _description = "سؤال النموذج المالي الموحد"
    _order = "module_sequence, requirement_id, sequence, id"
    _rec_names_search = ("label", "code")

    code = fields.Char("كود السؤال", required=True, index=True)
    key = fields.Char("المفتاح", required=True, help="Q001، Q002 … داخل المتطلب؛ يستخدم في شروط الظهور.")
    requirement_id = fields.Many2one("azm.fin.requirement", "المتطلب", required=True, ondelete="cascade", index=True)
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
