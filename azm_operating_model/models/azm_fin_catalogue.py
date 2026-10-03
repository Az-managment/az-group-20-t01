import json

from odoo import Command, api, fields, models
from odoo.tools import file_open

# Answer profiles (قوالب الإجابة) — same codes, names and meaning as the ACEAZ prototype
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

STATES = [
    ("full", "مطبّق بالكامل"),
    ("partial", "مطبّق جزئيًا"),
    ("unavailable", "غير متاح حاليًا"),
    ("na", "لا ينطبق"),
]
# The وسيلة التنفيذ scale, taken from the spreadsheet. _workspace_write drops
# any value not in this list silently, so it has to match the questionnaire.
IMPLEMENTATIONS = ["النظام الحالي", "SAP", "Excel", "يدوي أو ورقي", "لا يوجد نظام"]


class AzmFinModule(models.Model):
    _name = "azm.fin.module"
    _description = "موديول النموذج المالي الموحد"
    _order = "sequence, id"

    name = fields.Char("الموديول", required=True, translate=True)
    code = fields.Char("الكود", required=True, index=True)
    sequence = fields.Integer(default=10)
    requirement_ids = fields.One2many("azm.fin.requirement", "module_id", string="المتطلبات")
    requirement_count = fields.Integer("عدد المتطلبات", compute="_compute_requirement_count")
    detail_json = fields.Text("أسئلة تفصيلية موثّقة (JSON)",
                              help="أسئلة إضافية موثّقة من المستند لهذا الموديول (مثل العهد).")
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint("UNIQUE(code)", "كود الموديول لازم يكون فريد.")

    def _compute_requirement_count(self):
        counts = dict(self.env["azm.fin.requirement"]._read_group(
            [("module_id", "in", self.ids)], ["module_id"], ["__count"]))
        for module in self:
            module.requirement_count = counts.get(module, 0)

    def _details(self):
        self.ensure_one()
        return json.loads(self.detail_json) if self.detail_json else []

    @api.model
    def _load_catalogue(self):
        """Create / update the whole financial catalogue from data/fin_catalogue.json.

        Idempotent: every record is matched by its code, nothing answered is ever
        deleted, and options that disappear from the catalogue are archived rather
        than unlinked, because answers point at them.
        """
        with file_open("azm_operating_model/data/fin_catalogue.json", "rb") as f:
            cat = json.load(f)
        self._load_scopes()
        modules = self._load_modules(cat)
        topics = self._load_topics(cat, modules)
        self._load_requirements(cat, modules, topics)
        self._load_questions(cat)
        self._load_opening_questions(cat, topics)
        self._retire_empty_modules()
        return True

    @api.model
    def _load_scopes(self):
        Scope = self.env["azm.fin.scope"].with_context(active_test=False)
        for seq, (code, name) in enumerate(SCOPES.items(), 1):
            if code == "ALL":
                continue
            scope = Scope.search([("code", "=", code)])
            vals = {"name": name, "sequence": seq}
            scope.write(vals) if scope else Scope.create({"code": code, **vals})

    @api.model
    def _load_modules(self, cat):
        Module = self.with_context(active_test=False)
        modules = {}
        for seq, m in enumerate(cat["modules"], 1):
            module = Module.search([("code", "=", m["code"])])
            vals = {"name": m["name"], "sequence": seq * 10, "active": True}
            if module:
                module.write(vals)
            else:
                module = Module.create({"code": m["code"], **vals})
            modules[m["code"]] = module
        adv = cat.get("adv_module") or "ADV"
        if cat.get("adv_questions") and adv in modules:
            modules[adv].detail_json = json.dumps(cat["adv_questions"], ensure_ascii=False)
        return modules

    @api.model
    def _load_topics(self, cat, modules):
        Topic = self.env["azm.fin.topic"].with_context(active_test=False)
        topics = {}
        per_module = {}
        for t in cat.get("topics", []):
            per_module[t["module"]] = per_module.get(t["module"], 0) + 1
            vals = {
                "name": t["name"],
                "module_id": modules[t["module"]].id,
                "sequence": per_module[t["module"]],
                "active": True,
            }
            topic = Topic.search([("code", "=", t["code"])])
            if topic:
                topic.write(vals)
            else:
                topic = Topic.create({"code": t["code"], **vals})
            topics[t["code"]] = topic
        return topics

    @api.model
    def _load_requirements(self, cat, modules, topics):
        Req = self.env["azm.fin.requirement"].with_context(active_test=False)
        per_module = {}
        for r in cat["requirements"]:
            per_module[r["module"]] = per_module.get(r["module"], 0) + 1
            vals = {
                "module_id": modules[r["module"]].id,
                "sequence": per_module[r["module"]],
                "title": r["title"],
                "question": r["question"],
                "profile": r["profile"],
                "scope_code": r["scope"],
                "shape": r["shape"],
                "columns_json": json.dumps(r["columns"], ensure_ascii=False),
                "branches_json": json.dumps(r["branches"], ensure_ascii=False),
                "has_details": r["adv"],
            }
            if r.get("topic") in topics:
                vals["topic_id"] = topics[r["topic"]].id
            req = Req.search([("code", "=", r["code"])])
            req.write(vals) if req else Req.create({"code": r["code"], **vals})

    @api.model
    def _load_questions(self, cat):
        """Upsert the questions and their options.

        Options are matched by name inside their own question, so an option never
        leaks between questions, and stale ones are archived because
        azm.fin.qanswer.option_id is ondelete="restrict".
        """
        Question = self.env["azm.fin.question"].with_context(active_test=False)
        Option = self.env["azm.fin.option"].with_context(active_test=False)
        requirements = {
            r.code: r for r in
            self.env["azm.fin.requirement"].with_context(active_test=False).search([])
        }
        for q in cat.get("questions", []):
            requirement = requirements.get(q["requirement"])
            if not requirement:
                continue
            vals = {
                "label": q["label"],
                "role": q["role"],
                "qtype": q["qtype"],
                "sequence": q["sequence"],
                "condition": json.dumps(q["condition"], ensure_ascii=False) if q.get("condition") else False,
                "unit": q.get("unit") or False,
                "columns_json": json.dumps(q.get("columns") or [], ensure_ascii=False),
                "help_text": q.get("help") or False,
                "text_label": q.get("text_label") or False,
                "response_type": q.get("response_type") or False,
                "active": True,
            }
            question = Question.search([
                ("requirement_id", "=", requirement.id), ("key", "=", q["key"])])
            if question:
                question.write(vals)
            else:
                question = Question.create({
                    "requirement_id": requirement.id, "key": q["key"], **vals})

            wanted = {o["name"]: o for o in q.get("options", [])}
            existing = {o.name: o for o in question.option_ids}
            for name, option in wanted.items():
                ovals = {"sequence": option["sequence"], "kind": option["kind"], "active": True}
                if name in existing:
                    existing[name].write(ovals)
                else:
                    Option.create({"question_id": question.id, "name": name, **ovals})
            stale = [o for name, o in existing.items() if name not in wanted]
            if stale:
                Option.browse([o.id for o in stale]).write({"active": False})

    @api.model
    def _load_opening_questions(self, cat, topics):
        Opening = self.env["azm.fin.opening.question"].with_context(active_test=False)
        per_topic = {}
        for item in cat.get("opening_questions", []):
            topic = topics.get(item["topic"])
            if not topic:
                continue
            per_topic[item["topic"]] = per_topic.get(item["topic"], 0) + 1
            vals = {
                "topic_id": topic.id,
                "axis_code": item.get("axis_code") or False,
                "axis": item.get("axis") or False,
                "stage": item.get("stage") or False,
                "question": item["question"],
                "output": item.get("output") or False,
                "sequence": per_topic[item["topic"]],
                "active": True,
            }
            record = Opening.search([("node", "=", item["node"])])
            record.write(vals) if record else Opening.create({"node": item["node"], **vals})

    @api.model
    def _retire_empty_modules(self):
        """Archive the modules the new taxonomy left without requirements.

        They are archived, not deleted: approved azm.fin.version snapshots name
        them, and every nav/search call uses search([]), which already skips
        archived records.
        """
        Module = self.with_context(active_test=False)
        empty = Module.search([("active", "=", True), ("requirement_ids", "=", False)])
        if empty:
            empty.write({"active": False})

    def action_reload_catalogue(self):
        self._load_catalogue()
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"type": "success", "message": "تم تحديث كتالوج النموذج المالي."}}


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
    _order = "module_sequence, sequence, id"
    _rec_names_search = ("title", "code", "question")

    code = fields.Char("الكود", required=True, index=True)
    module_id = fields.Many2one("azm.fin.module", "الموديول", required=True, ondelete="cascade", index=True)
    module_sequence = fields.Integer(related="module_id.sequence", store=True, string="ترتيب الموديول")
    sequence = fields.Integer(default=10)
    title = fields.Char("المتطلب", required=True, translate=True)
    question = fields.Text("السؤال", required=True, translate=True)
    profile = fields.Selection(PROFILE_SELECTION, "قالب الإجابة", required=True)
    scope_code = fields.Selection(SCOPE_SELECTION, "نطاق الانطباق", required=True, default="ALL")
    source = fields.Selection([("FIN", "مالية"), ("HRF", "مالية الموارد البشرية")], "المصدر",
                              compute="_compute_source", store=True)
    shape = fields.Selection([("table", "جدول"), ("fields", "حقول")], "شكل الإجابة", default="table", required=True)
    columns_json = fields.Text("أعمدة/حقول الإجابة (JSON)")
    branches_json = fields.Text("التفرعات (JSON)")
    has_details = fields.Boolean("أسئلة تفصيلية موثّقة")
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint("UNIQUE(code)", "كود المتطلب لازم يكون فريد.")

    @api.depends("code")
    def _compute_source(self):
        for req in self:
            req.source = "HRF" if (req.code or "").startswith("HRF") else "FIN"

    @api.depends("code", "title")
    def _compute_display_name(self):
        for req in self:
            req.display_name = f"[{req.code}] {req.title}" if req.code else req.title

    def _schema(self):
        self.ensure_one()
        return {
            "shape": self.shape,
            "columns": json.loads(self.columns_json or "[]"),
            "branches": json.loads(self.branches_json or "[]"),
        }


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
