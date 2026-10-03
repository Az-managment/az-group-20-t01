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
IMPLEMENTATIONS = ["نظام", "يدوي", "Excel", "مختلط"]


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
        """Create / update modules, scopes and requirements from data/fin_catalogue.json.
        Idempotent: records are matched by code, nothing answered is deleted."""
        with file_open("azm_operating_model/data/fin_catalogue.json", "rb") as f:
            cat = json.load(f)
        Scope = self.env["azm.fin.scope"].with_context(active_test=False)
        for seq, (code, name) in enumerate(SCOPES.items(), 1):
            if code == "ALL":
                continue
            scope = Scope.search([("code", "=", code)])
            vals = {"name": name, "sequence": seq}
            scope.write(vals) if scope else Scope.create({"code": code, **vals})

        Module = self.with_context(active_test=False)
        modules = {}
        for seq, m in enumerate(cat["modules"], 1):
            module = Module.search([("code", "=", m["code"])])
            vals = {"name": m["name"], "sequence": seq * 10}
            if module:
                module.write(vals)
            else:
                module = Module.create({"code": m["code"], **vals})
            modules[m["code"]] = module
        if cat.get("adv_questions") and "ADV" in modules:
            modules["ADV"].detail_json = json.dumps(cat["adv_questions"], ensure_ascii=False)

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
            req = Req.search([("code", "=", r["code"])])
            req.write(vals) if req else Req.create({"code": r["code"], **vals})
        return True

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
