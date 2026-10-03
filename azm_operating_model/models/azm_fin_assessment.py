import json
import zlib
from html import escape

from markupsafe import Markup

from odoo import Command, api, fields, models
from odoo.exceptions import UserError

from . import fin_engine
from .azm_fin_catalogue import IMPLEMENTATIONS, PROFILES, SCOPES, STATES

STATE_LABELS = dict(STATES)
STATE_HINTS = {
    "full": "قاعدة قائمة ومطبّقة",
    "partial": "يوجد نقص أو فجوة",
    "unavailable": "لا توجد ممارسة بعد",
    "na": "يتطلب سببًا ومراجعة",
}
TEXT_KEYS = ("current", "gap", "future", "reason")


def _e(text):
    return escape(str(text or ""), quote=True)


class AzmFinAssessment(models.Model):
    _name = "azm.fin.assessment"
    _description = "إفادة النموذج المالي الموحد"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"

    name = fields.Char("المرجع", required=True, copy=False, readonly=True, default="جديد")
    entity_id = fields.Many2one("azm.entity", "الكيان", required=True, tracking=True)
    company_id = fields.Many2one("res.company", "الشركة", required=True, compute="_compute_company_id",
                                 store=True, readonly=False, precompute=True)
    scope_ids = fields.Many2many("azm.fin.scope", "azm_fin_assessment_scope_rel", "assessment_id", "scope_id",
                                 string="أنشطة الكيان", compute="_compute_scope_ids", store=True, readonly=False,
                                 precompute=True,
                                 help="المتطلبات ذات النطاق «كل الكيانات» تظهر دائمًا، والباقي حسب هذه الأنشطة.")
    version = fields.Integer("الإصدار", default=1, readonly=True, copy=False)
    state = fields.Selection([
        ("draft", "مسودة"),
        ("review", "تحت المراجعة"),
        ("approved", "معتمدة"),
        ("archived", "إصدار سابق"),
    ], default="draft", required=True, tracking=True, copy=False, string="الحالة")
    user_id = fields.Many2one("res.users", "مُعد الإفادة", default=lambda self: self.env.user, tracking=True)
    reviewer_id = fields.Many2one("res.users", "المراجع", tracking=True)
    approved_by_id = fields.Many2one("res.users", "اعتمدها", readonly=True, copy=False)
    approved_date = fields.Datetime("تاريخ الاعتماد", readonly=True, copy=False)
    is_demo = fields.Boolean("مثال افتراضي", copy=False)
    previous_id = fields.Many2one("azm.fin.assessment", "الإصدار السابق", readonly=True, copy=False)
    answer_ids = fields.One2many("azm.fin.answer", "assessment_id", string="الإجابات", copy=True)
    version_ids = fields.One2many("azm.fin.version", "assessment_id", string="الإصدارات المعتمدة")

    applicable_count = fields.Integer("متطلبات منطبقة", compute="_compute_stats")
    done_count = fields.Integer("متطلبات مُجابة", compute="_compute_stats")
    progress = fields.Float("نسبة الاكتمال", compute="_compute_stats")
    full_count = fields.Integer("مطبّق بالكامل", compute="_compute_stats")
    partial_count = fields.Integer("مطبّق جزئيًا", compute="_compute_stats")
    unavailable_count = fields.Integer("غير متاح", compute="_compute_stats")
    na_count = fields.Integer("لا ينطبق", compute="_compute_stats")
    gap_count = fields.Integer("الفجوات", compute="_compute_stats")

    map_html = fields.Html("خريطة النموذج", compute="_compute_outputs", sanitize=False)
    output_html = fields.Html("الوضع الحالي", compute="_compute_outputs", sanitize=False)
    summary_html = fields.Html("ملخص الموديولات", compute="_compute_outputs", sanitize=False)
    gaps_html = fields.Html("الفجوات والتصورات", compute="_compute_outputs", sanitize=False)

    _entity_version_uniq = models.Constraint(
        "UNIQUE(entity_id, version)",
        "فيه إفادة مالية لنفس الكيان بنفس الإصدار؛ افتحها أو اعمل إصدار جديد منها.")

    # ---------------------------------------------------------------- computes
    @api.depends("entity_id")
    def _compute_company_id(self):
        for rec in self:
            rec.company_id = rec.entity_id.sudo().company_id or rec.company_id or self.env.company

    @api.depends("entity_id")
    def _compute_scope_ids(self):
        for rec in self:
            rec.scope_ids = rec.entity_id.sudo().fin_scope_ids if rec.entity_id else False

    @api.depends("answer_ids.state", "answer_ids.is_done", "answer_ids.applicable")
    def _compute_stats(self):
        for rec in self:
            app = rec.answer_ids.filtered("applicable")
            rec.applicable_count = len(app)
            rec.done_count = len(app.filtered("is_done"))
            rec.progress = 100.0 * rec.done_count / rec.applicable_count if rec.applicable_count else 0.0
            rec.full_count = len(app.filtered(lambda a: a.state == "full"))
            rec.partial_count = len(app.filtered(lambda a: a.state == "partial"))
            rec.unavailable_count = len(app.filtered(lambda a: a.state == "unavailable"))
            rec.na_count = len(app.filtered(lambda a: a.state == "na"))
            rec.gap_count = rec.partial_count + rec.unavailable_count

    # ---------------------------------------------------------------- crud
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "جديد") == "جديد":
                vals["name"] = self.env["ir.sequence"].sudo().next_by_code("azm.fin.assessment") or "جديد"
        records = super().create(vals_list)
        records._ensure_answers()
        return records

    def _ensure_answers(self):
        requirements = self.env["azm.fin.requirement"].search([])
        lines = []
        for rec in self:
            have = set(rec.answer_ids.requirement_id.ids)
            lines += [{"assessment_id": rec.id, "requirement_id": r.id} for r in requirements if r.id not in have]
        if lines:
            self.env["azm.fin.answer"].create(lines)

    # ---------------------------------------------------------------- workspace RPC
    def _modules_nav(self):
        self.ensure_one()
        nav = []
        for module in self.env["azm.fin.module"].search([]):
            lines = self.answer_ids.filtered(lambda a, m=module: a.module_id == m)
            app = lines.filtered("applicable")
            nav.append({
                "code": module.code, "name": module.name,
                "total": len(lines), "applicable": len(app), "done": len(app.filtered("is_done")),
                "gaps": len(app.filtered(lambda a: a.state in ("partial", "unavailable"))),
            })
        return nav

    def _header(self):
        self.ensure_one()
        return {
            "id": self.id, "name": self.name, "entity": self.entity_id.name,
            "state": self.state, "state_label": dict(self._fields["state"].selection)[self.state],
            "version": self.version, "is_demo": self.is_demo, "readonly": self.state != "draft",
            "applicable": self.applicable_count, "done": self.done_count, "progress": round(self.progress),
            "counts": {"full": self.full_count, "partial": self.partial_count,
                       "unavailable": self.unavailable_count, "na": self.na_count},
            "scopes": [{"code": "ALL", "name": SCOPES["ALL"]}] + [
                {"code": s.code, "name": s.name} for s in self.scope_ids],
        }

    def _engine_items(self, module=None, show_all=False):
        """Plain dicts for the rendering engine (applicable requirements only, unless show_all)."""
        self.ensure_one()
        lines = self.answer_ids
        if module:
            lines = lines.filtered(lambda a: a.module_id == module)
        if not show_all:
            lines = lines.filtered("applicable")
        lines = lines.sorted(lambda a: (a.module_sequence, a.requirement_sequence, a.id))
        return [line._engine_dict() for line in lines]

    def _render(self, tab, module=False):
        self.ensure_one()
        if module:
            body = fin_engine.render_module(tab, {"code": module.code, "name": module.name}, self._engine_items(module))
        else:
            data = [({"code": m.code, "name": m.name}, self._engine_items(m)) for m in self.env["azm.fin.module"].search([])]
            body = fin_engine.render_model(tab, data)
        banner = ""
        if self.is_demo:
            banner = fin_engine.note("مثال افتراضي للتجربة فقط.", "warn")
        elif self.state != "approved":
            banner = fin_engine.note("مسودة غير معتمدة · صياغة من الإفادات؛ الأدلة لم تُتحقق.")
        return Markup(f'<div class="o_azm_output" dir="rtl">{banner}{body}</div>')

    def workspace_data(self, module_code=None, tab="book", scope="module", show_all=False):
        """Everything the financial workspace needs in one round trip."""
        self.ensure_one()
        modules = self.env["azm.fin.module"].search([])
        module = modules.filtered(lambda m: m.code == module_code)[:1] or modules[:1]
        lines = self.answer_ids.filtered(lambda a: a.module_id == module).sorted(
            lambda a: (a.requirement_id.sequence, a.id))
        if not show_all:
            lines = lines.filtered("applicable")
        return {
            "header": self._header(),
            "modules": self._modules_nav(),
            "module": {"code": module.code, "name": module.name,
                       "total": len(self.answer_ids.filtered(lambda a: a.module_id == module))},
            "requirements": [line._workspace_dict() for line in lines],
            "details": module._details(),
            "profiles": [{"key": k, "name": v[0], "en": v[1], "desc": v[2]} for k, v in PROFILES.items()],
            "states": [{"key": k, "name": n, "hint": STATE_HINTS[k]} for k, n in STATES],
            "implementations": IMPLEMENTATIONS,
            "tabs": [{"key": k, "title": t} for k, t in fin_engine.OUTPUT_TABS],
            "output": str(self._render(tab, module if scope == "module" else False)),
        }

    def workspace_save(self, answer_id, vals, module_code=None, tab="book", scope="module"):
        self.ensure_one()
        if self.state != "draft":
            raise UserError("الإفادة مش في حالة مسودة.")
        line = self.answer_ids.filtered(lambda a: a.id == answer_id)
        if not line:
            raise UserError("المتطلب غير موجود في الإفادة.")
        line._workspace_write(vals)
        return {"answer": line._workspace_dict(), "header": self._header(), "modules": self._modules_nav(),
                "output": self.workspace_output(module_code or line.module_id.code, tab, scope)}

    def workspace_output(self, module_code=None, tab="book", scope="module"):
        self.ensure_one()
        module = self.env["azm.fin.module"].search([("code", "=", module_code)], limit=1) if module_code else False
        return str(self._render(tab, module if scope == "module" else False))

    # ---------------------------------------------------------------- outputs
    @api.depends("answer_ids.state", "answer_ids.gap", "answer_ids.future", "answer_ids.reason",
                 "answer_ids.applicable")
    def _compute_outputs(self):
        for rec in self:
            rec.summary_html = rec._render_summary() if rec.id else False
            rec.gaps_html = rec._render_gaps() if rec.id else False
            rec.map_html = Markup(f'<div class="o_azm_output" dir="rtl">{fin_engine.module_map(rec._modules_nav())}</div>') if rec.id else False
            rec.output_html = rec._render("book") if rec.id else False

    def _banner(self):
        if self.is_demo:
            return '<div class="o_azm_fin_note o_warn">مثال افتراضي للتجربة فقط.</div>'
        if self.state != "approved":
            return '<div class="o_azm_fin_note">مسودة غير معتمدة · مبنية على الإفادات؛ الأدلة لم تُتحقق.</div>'
        return ""

    def _render_summary(self):
        self.ensure_one()
        rows = []
        for m in self._modules_nav():
            lines = self.answer_ids.filtered(lambda a, c=m["code"]: a.module_id.code == c and a.applicable)
            cnt = {k: len(lines.filtered(lambda a, k=k: a.state == k)) for k, _n in STATES}
            pct = round(100 * m["done"] / m["applicable"]) if m["applicable"] else 0
            rows.append(
                f"<tr><td><b>{_e(m['code'])}</b></td><td>{_e(m['name'])}</td><td>{m['applicable']}/{m['total']}</td>"
                f"<td>{cnt['full']}</td><td>{cnt['partial']}</td><td>{cnt['unavailable']}</td><td>{cnt['na']}</td>"
                f"<td><div class='o_azm_fin_bar'><span style='width:{pct}%'></span></div> {pct}%</td></tr>")
        head = ("<tr><th>الكود</th><th>الموديول</th><th>منطبق/الكل</th><th>بالكامل</th><th>جزئيًا</th>"
                "<th>غير متاح</th><th>لا ينطبق</th><th>الاكتمال</th></tr>")
        return Markup(f'<div class="o_azm_fin_out" dir="rtl">{self._banner()}'
                      f'<table class="o_azm_fin_table"><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table></div>')

    def _render_gaps(self):
        self.ensure_one()
        app = self.answer_ids.filtered("applicable")
        sections = [
            ("partial", "الفجوات (مطبّق جزئيًا)", "gap", "الفجوة وأثرها"),
            ("unavailable", "غير متاح حاليًا · التصوّر المستقبلي", "future", "التصوّر المستقبلي"),
            ("na", "لا ينطبق · للمراجعة", "reason", "السبب"),
        ]
        html = [f'<div class="o_azm_fin_out" dir="rtl">{self._banner()}']
        for state, title, field, label in sections:
            lines = app.filtered(lambda a, s=state: a.state == s)
            html.append(f"<h3>{_e(title)} <small>({len(lines)})</small></h3>")
            if not lines:
                html.append('<p class="text-muted">لا يوجد.</p>')
                continue
            html.append("<table class='o_azm_fin_table'><thead><tr><th>الكود</th><th>المتطلب</th>"
                        f"<th>الموديول</th><th>{_e(label)}</th></tr></thead><tbody>")
            for a in lines:
                text = a[field] or "[لم يُحدد]"
                html.append(f"<tr><td><b>{_e(a.code)}</b></td><td>{_e(a.requirement_id.title)}</td>"
                            f"<td>{_e(a.module_id.name)}</td><td>{_e(text)}</td></tr>")
            html.append("</tbody></table>")
        html.append("</div>")
        return Markup("".join(html))

    # ---------------------------------------------------------------- actions
    def action_open_workspace(self):
        self.ensure_one()
        return {"type": "ir.actions.client", "tag": "azm_fin_workspace", "name": self.name,
                "params": {"assessment_id": self.id}}

    def action_submit(self):
        for rec in self.filtered(lambda r: r.state == "draft"):
            rec.state = "review"
            if rec.reviewer_id:
                # the preparer loses write access once the assessment leaves draft: notify as superuser
                rec.sudo().activity_schedule("mail.mail_activity_data_todo", user_id=rec.reviewer_id.id,
                                      summary="مراجعة إفادة النموذج المالي")

    def action_back_to_draft(self):
        self.filtered(lambda r: r.state == "review").write({"state": "draft"})

    def action_approve(self):
        if not self.env.user.has_group("azm_operating_model.azm_group_manager"):
            raise UserError("الاعتماد لمدير النموذج فقط.")
        for rec in self:
            if rec.state != "review":
                raise UserError("الاعتماد يتم من حالة «تحت المراجعة» فقط.")
            if rec.user_id == self.env.user and not self.env.is_superuser():
                raise UserError("مُعد الإفادة لا يعتمدها بنفسه (فصل المهام).")
            answers = {a.code: a._workspace_dict(light=True) for a in rec.answer_ids if a.state}
            self.env["azm.fin.version"].create({
                "assessment_id": rec.id, "version": rec.version,
                "answers_json": json.dumps(answers, ensure_ascii=False, indent=1),
                # every output except the coverage matrix, taken from the tab
                # list rather than a literal, so a new output is never missed
                "summary_html": "".join(str(rec._render(tab)) for tab, _title in fin_engine.OUTPUT_TABS
                                        if tab not in ("coverage", "na")),
            })
            rec.write({"state": "approved", "approved_by_id": self.env.user.id,
                       "approved_date": fields.Datetime.now()})

    def action_new_version(self):
        self.ensure_one()
        if self.state != "approved":
            raise UserError("الإصدار الجديد يتعمل من إفادة معتمدة.")
        new = self.copy({"version": self.version + 1, "previous_id": self.id, "name": "جديد",
                         "scope_ids": [Command.set(self.scope_ids.ids)]})
        self.state = "archived"
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": new.id, "view_mode": "form"}

    def action_view_gaps(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": "سجل الفجوات", "res_model": "azm.fin.answer",
                "view_mode": "list,form",
                "domain": [("assessment_id", "=", self.id), ("applicable", "=", True),
                           ("state", "in", ("partial", "unavailable"))],
                "context": {"create": False, "search_default_by_module": 1}}

    def action_view_answers(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": f"إجابات {self.name}", "res_model": "azm.fin.answer",
                "view_mode": "list,form", "domain": [("assessment_id", "=", self.id), ("applicable", "=", True)],
                "context": {"create": False, "search_default_by_module": 1}}

    def action_fill_demo(self):
        """Deterministic demo answers: mostly applied, with partial gaps, unavailable items and a few N/A."""
        for rec in self:
            if rec.state != "draft":
                raise UserError("المثال يتعمل على مسودة فقط.")
            for line in rec.answer_ids.filtered("applicable"):
                seed = zlib.crc32(f"{rec.entity_id.code}/{line.code}".encode())
                pick = seed % 20
                state = "full" if pick < 9 else "partial" if pick < 14 else "unavailable" if pick < 18 else "na"
                schema = line.requirement_id._schema()
                row = []
                for i, col in enumerate(schema["columns"]):
                    opts = col.get("options")
                    row.append(opts[(seed >> i) % len(opts)] if opts else f"{col['label']} — مثال")
                vals = {
                    "state": state,
                    "impl": [IMPLEMENTATIONS[seed % len(IMPLEMENTATIONS)]] if state in ("full", "partial") else [],
                    "current": f"المطبّق حاليًا في «{line.requirement_id.title}» وفق الممارسة المعتادة بالكيان."
                    if state in ("full", "partial") else "",
                    "gap": f"تُطبّق القاعدة على جزء من الحالات فقط؛ يلزم توحيد «{line.requirement_id.title}» وتوثيقه."
                    if state == "partial" else "",
                    "future": f"تصميم قاعدة موحّدة لـ «{line.requirement_id.title}» ضمن النموذج المستهدف."
                    if state == "unavailable" else "",
                    "reason": "النشاط غير موجود حاليًا بالكيان." if state == "na" else "",
                    "table": [row] if state in ("full", "partial") else [],
                    "branches": [b["options"][0] for b in schema["branches"]] if state != "na" else [],
                }
                line._workspace_write(vals)
            rec.is_demo = True
        return True

    def action_reset_answers(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError("المسح متاح للمسودة فقط.")
            rec.answer_ids.write({"state": False, "impl": False, "current": False, "gap": False, "future": False,
                                  "reason": False, "table_json": False, "branch_json": False})
            rec.is_demo = False


class AzmFinAnswer(models.Model):
    _name = "azm.fin.answer"
    _description = "إجابة متطلب مالي"
    _order = "module_sequence, requirement_sequence, id"

    assessment_id = fields.Many2one("azm.fin.assessment", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="assessment_id.company_id", store=True)
    entity_id = fields.Many2one(related="assessment_id.entity_id", store=True, string="الكيان")
    requirement_id = fields.Many2one("azm.fin.requirement", "المتطلب", required=True, ondelete="restrict", index=True)
    module_id = fields.Many2one(related="requirement_id.module_id", store=True, string="الموديول")
    module_sequence = fields.Integer(related="requirement_id.module_sequence", store=True, string="ترتيب الموديول")
    requirement_sequence = fields.Integer(related="requirement_id.sequence", store=True, string="ترتيب المتطلب")
    code = fields.Char(related="requirement_id.code", store=True, string="الكود")
    title = fields.Char(related="requirement_id.title", string="المتطلب ")
    profile = fields.Selection(related="requirement_id.profile", store=True, string="قالب الإجابة")
    scope_code = fields.Selection(related="requirement_id.scope_code", store=True, string="نطاق الانطباق")
    applicable = fields.Boolean("منطبق", compute="_compute_applicable", store=True)
    state = fields.Selection(STATES, "حالة التطبيق", copy=True)
    impl = fields.Char("طريقة التنفيذ", help="نظام، يدوي، Excel، مختلط (مفصولة بفاصلة).")
    current = fields.Text("القاعدة الحالية")
    gap = fields.Text("الفجوة وأثرها")
    future = fields.Text("التصوّر المستقبلي")
    reason = fields.Text("سبب عدم الانطباق")
    table_json = fields.Text("جدول الإجابة (JSON)")
    branch_json = fields.Text("التفرعات (JSON)")
    attachment_ids = fields.Many2many("ir.attachment", string="الأدلة")
    is_done = fields.Boolean("مُجاب", compute="_compute_is_done", store=True)

    _assessment_requirement_uniq = models.Constraint(
        "UNIQUE(assessment_id, requirement_id)", "المتطلب متكرر في نفس الإفادة.")

    @api.depends("requirement_id.scope_code", "assessment_id.scope_ids")
    def _compute_applicable(self):
        for a in self:
            code = a.requirement_id.scope_code
            a.applicable = code == "ALL" or code in a.assessment_id.scope_ids.mapped("code")

    @api.depends("state", "current", "gap", "future", "reason")
    def _compute_is_done(self):
        # same rule as the ACEAZ portal: the text the chosen state requires must be filled in
        need = {"full": "current", "partial": "gap", "unavailable": "future", "na": "reason"}
        for a in self:
            a.is_done = bool(a.state and (a[need[a.state]] or "").strip())

    def _workspace_dict(self, light=False):
        self.ensure_one()
        req = self.requirement_id
        data = {
            "answer_id": self.id, "code": req.code, "state": self.state or False,
            "impl": [x for x in (self.impl or "").split(",") if x],
            "current": self.current or "", "gap": self.gap or "", "future": self.future or "",
            "reason": self.reason or "",
            "table": json.loads(self.table_json) if self.table_json else [],
            "branches": json.loads(self.branch_json) if self.branch_json else [],
        }
        if light:
            return data
        prof = PROFILES[req.profile]
        data.update({
            "title": req.title, "question": req.question, "profile": req.profile,
            "profile_name": prof[0], "profile_en": prof[1], "profile_hint": prof[2],
            "scope_code": req.scope_code, "scope_name": SCOPES.get(req.scope_code, ""),
            "source": req.source, "applicable": self.applicable, "done": self.is_done,
            "schema": req._schema(), "has_details": req.has_details,
            "attachments": len(self.attachment_ids),
        })
        return data

    def _engine_dict(self):
        self.ensure_one()
        req = self.requirement_id
        schema = req._schema()
        return {
            "code": req.code, "title": req.title, "question": req.question, "profile": req.profile,
            "profile_name": PROFILES[req.profile][0], "scope_name": SCOPES.get(req.scope_code, ""),
            "state": self.state or False, "impl": [x for x in (self.impl or "").split(",") if x],
            "current": self.current or "", "gap": self.gap or "", "future": self.future or "",
            "reason": self.reason or "", "done": self.is_done,
            "table": json.loads(self.table_json) if self.table_json else [],
            "branches": json.loads(self.branch_json) if self.branch_json else [],
            "columns": schema["columns"], "branch_defs": schema["branches"],
        }

    def _workspace_write(self, vals):
        clean = {}
        if "state" in vals:
            if vals["state"] not in (False, *(k for k, _n in STATES)):
                raise UserError("حالة غير معروفة.")
            clean["state"] = vals["state"]
        if "impl" in vals:
            clean["impl"] = ",".join(x for x in vals["impl"] or [] if x in IMPLEMENTATIONS) or False
        for key in TEXT_KEYS:
            if key in vals:
                clean[key] = vals[key] or False
        if "table" in vals:
            rows = [[str(c or "") for c in row] for row in (vals["table"] or []) if isinstance(row, list)]
            clean["table_json"] = json.dumps(rows, ensure_ascii=False) if rows else False
        if "branches" in vals:
            clean["branch_json"] = json.dumps([str(b or "") for b in vals["branches"] or []], ensure_ascii=False)
        if clean:
            self.write(clean)

    def write(self, vals):
        locked = {"state", "impl", "current", "gap", "future", "reason", "table_json", "branch_json"}
        if locked & set(vals) and not self.env.context.get("azm_skip_lock"):
            if any(a.assessment_id.state != "draft" for a in self):
                raise UserError("الإفادة مش في حالة مسودة؛ لا يمكن تعديل الإجابات.")
        return super().write(vals)


class AzmFinVersion(models.Model):
    _name = "azm.fin.version"
    _description = "نسخة معتمدة من إفادة مالية"
    _order = "approved_date desc, id desc"

    assessment_id = fields.Many2one("azm.fin.assessment", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="assessment_id.company_id", store=True)
    version = fields.Integer(required=True)
    approved_date = fields.Datetime(required=True, default=fields.Datetime.now)
    approved_by_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user)
    answers_json = fields.Text("الإجابات (JSON)", readonly=True)
    summary_html = fields.Html("نسخة الملخص المعتمدة", sanitize=False, readonly=True)
