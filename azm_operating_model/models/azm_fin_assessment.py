import json
import zlib

from markupsafe import Markup

from odoo import Command, api, fields, models
from odoo.exceptions import UserError

from . import fin_engine
from .azm_fin_catalogue import (FALLBACK_KINDS, NA_REASONS, NOTE_LISTS, OTHER, PRIORITIES, PROFILES, SCOPES,
                                STATES, STATUS_OPTIONS)


def _e(text):
    return fin_engine._e(text)


class AzmFinAssessment(models.Model):
    _name = "azm.fin.assessment"
    _description = "إفادة النموذج المالي الموحد"
    _inherit = ["mail.thread", "mail.activity.mixin", "azm.reviewable"]
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
    assignment_ids = fields.One2many("azm.assignment", "fin_assessment_id",
                                     string="توزيع الموديولات")
    approved_by_id = fields.Many2one("res.users", "اعتمدها", readonly=True, copy=False)
    approved_date = fields.Datetime("تاريخ الاعتماد", readonly=True, copy=False)
    is_demo = fields.Boolean("مثال افتراضي", copy=False)
    previous_id = fields.Many2one("azm.fin.assessment", "الإصدار السابق", readonly=True, copy=False)
    # A requirement retired from the catalogue is archived, not deleted — so its answers
    # survive for the record — but it must stop being asked, counted and printed. The
    # domain keeps it out of everything that reads answer_ids; _ensure_answers goes
    # around it so a retired requirement is never re-created either.
    answer_ids = fields.One2many("azm.fin.answer", "assessment_id", string="الإجابات", copy=True,
                                 domain=[("requirement_active", "=", True)])
    version_ids = fields.One2many("azm.fin.version", "assessment_id", string="الإصدارات المعتمدة")

    applicable_count = fields.Integer("متطلبات منطبقة", compute="_compute_stats")
    done_count = fields.Integer("متطلبات مكتملة", compute="_compute_stats")
    question_count = fields.Integer("أسئلة ظاهرة", compute="_compute_stats")
    answered_count = fields.Integer("أسئلة مُجابة", compute="_compute_stats")
    progress = fields.Float("نسبة الاكتمال", compute="_compute_stats")
    full_count = fields.Integer("مطبّق بالكامل", compute="_compute_stats")
    partial_count = fields.Integer("مطبّق جزئيًا", compute="_compute_stats")
    unavailable_count = fields.Integer("غير منفذ", compute="_compute_stats")
    unknown_count = fields.Integer("لا أعرف", compute="_compute_stats")
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

    @api.depends("answer_ids.state", "answer_ids.is_done", "answer_ids.applicable",
                 "answer_ids.q_total", "answer_ids.q_answered")
    def _compute_stats(self):
        for rec in self:
            app = rec.answer_ids.filtered("applicable")
            rec.applicable_count = len(app)
            rec.done_count = len(app.filtered("is_done"))
            total, answered = app._question_totals()
            rec.question_count, rec.answered_count = total, answered
            rec.progress = 100.0 * answered / total if total else 0.0
            for key, _label in STATES:
                rec[f"{key}_count"] = len(app.filtered(lambda a, k=key: a.state == k))
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
        """A line per live requirement, for every assessment given.

        Read through the model rather than answer_ids: that field hides the lines of
        retired requirements, and they must not be created a second time."""
        requirements = self.env["azm.fin.requirement"].search([])
        Answer = self.env["azm.fin.answer"].with_context(active_test=False)
        existing = {}
        for line in Answer.search([("assessment_id", "in", self.ids)]):
            existing.setdefault(line.assessment_id.id, set()).add(line.requirement_id.id)
        lines = [{"assessment_id": rec.id, "requirement_id": r.id}
                 for rec in self for r in requirements
                 if r.id not in existing.get(rec.id, ())]
        if lines:
            Answer.create(lines)

    @api.model
    def _ensure_all_answers(self):
        """Top every assessment up after a catalogue reload — a requirement added to the
        catalogue has no line on the assessments that already existed."""
        self.search([])._ensure_answers()

    # ---------------------------------------------------------------- workspace RPC
    def _modules_nav(self):
        self.ensure_one()
        nav = []
        for module in self.env["azm.fin.module"].search([]):
            lines = self.answer_ids.filtered(lambda a, m=module: a.module_id == m)
            app = lines.filtered("applicable")
            total, answered = app._question_totals()
            nav.append({
                "code": module.code, "name": module.name,
                "total": len(lines), "applicable": len(app), "done": len(app.filtered("is_done")),
                "questions": total, "answered": answered,
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
            "questions": self.question_count, "answered": self.answered_count,
            "outstanding": self._azm_outstanding(), "can_send": self._azm_can_send(),
            # the review side: who may send a part back, and what is already back
            **self._azm_review_header(),
            "counts": {key: self[f"{key}_count"] for key, _label in STATES},
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
        lines = lines.sorted(lambda a: (a.module_sequence, a.topic_sequence, a.requirement_sequence, a.id))
        return [line._engine_dict() for line in lines]

    def _render(self, tab, module=False):
        self.ensure_one()
        if module:
            body = fin_engine.render_module(tab, {"code": module.code, "name": module.name}, self._engine_items(module))
        else:
            data = [({"code": m.code, "name": m.name}, self._engine_items(m)) for m in self.env["azm.fin.module"].search([])]
            body = fin_engine.render_model(tab, data)
        return Markup(f'<div class="o_azm_output" dir="rtl">{self._banner()}{body}</div>')

    def workspace_data(self, module_code=None, tab="book", scope="module", show_all=False):
        """Everything the financial workspace needs in one round trip."""
        self.ensure_one()
        modules = self.env["azm.fin.module"].search([])
        module = modules.filtered(lambda m: m.code == module_code)[:1] or modules[:1]
        returns = self.env["azm.review.return"]._open_for(self)
        lines = self.answer_ids.filtered(lambda a: a.module_id == module).sorted(
            lambda a: (a.topic_sequence, a.requirement_sequence, a.id))
        if not show_all:
            lines = lines.filtered("applicable")
        topics = []
        for line in lines:
            topic = line.requirement_id.topic_id
            if not topics or topics[-1]["id"] != topic.id:
                topics.append({"id": topic.id, "code": topic.code or "", "name": topic.name or "",
                               "prompts": [{"code": p.code, "axis": p.axis, "axis_name": p.axis_name,
                                            "stage": p.stage, "question": p.question, "output": p.output or ""}
                                           for p in topic.prompt_ids],
                               "requirements": []})
            row = line._workspace_dict()
            # when a review has sent parts back, everything else stands as it was
            # reviewed: the page says so rather than letting somebody type into a field
            # the server will refuse
            covered = bool(returns) and returns._covers(line)
            row["locked"] = bool(returns) and not covered
            # said outright rather than left to be read off "locked", which is false
            # both for a returned requirement and for every requirement when nothing
            # was returned at all
            row["returned"] = covered
            topics[-1]["requirements"].append(row)
        return {
            "header": self._header(),
            # how many parts are waiting to be answered again, across the whole
            # assessment: the filter is worth offering only when there are some, and
            # what came back may be under a module the reader is not looking at
            "returns_open": len(returns),
            "modules": self._modules_nav(),
            "module": {"id": module.id, "code": module.code, "name": module.name,
                       "total": len(self.answer_ids.filtered(lambda a: a.module_id == module))},
            "topics": topics,
            "states": [{"key": k, "name": n} for k, n in STATES],
            "na_reasons": NA_REASONS,
            "priorities": [{"key": k, "name": n} for k, n in PRIORITIES],
            "tabs": [{"key": k, "title": t} for k, t in fin_engine.OUTPUT_TABS],
            "output": str(self._render(tab, module if scope == "module" else False)),
        }

    def _workspace_line(self, answer_id):
        self.ensure_one()
        if self.state != "draft":
            raise UserError("الإفادة مش في حالة مسودة.")
        line = self.answer_ids.filtered(lambda a: a.id == answer_id)
        if not line:
            raise UserError("المتطلب غير موجود في الإفادة.")
        return line

    def _workspace_result(self, line, module_code, tab, scope):
        return {"requirement": line._workspace_dict(), "header": self._header(), "modules": self._modules_nav(),
                "output": self.workspace_output(module_code or line.module_id.code, tab, scope)}

    def workspace_answer(self, answer_id, question_id, vals, module_code=None, tab="book", scope="module"):
        """Save the answer of one question (option_id / option_ids / number / table / note)."""
        self.ensure_one()
        line = self._workspace_line(answer_id)
        line._set_answer(question_id, vals)
        return self._workspace_result(line, module_code, tab, scope)

    def workspace_requirement(self, answer_id, vals, module_code=None, tab="book", scope="module"):
        """Requirement level: «لا ينطبق على الكيان» and its reason."""
        self.ensure_one()
        line = self._workspace_line(answer_id)
        clean = {k: vals[k] or False for k in ("na", "reason") if k in vals}
        if clean:
            line.write(clean)
        return self._workspace_result(line, module_code, tab, scope)

    def workspace_output(self, module_code=None, tab="book", scope="module"):
        self.ensure_one()
        module = self.env["azm.fin.module"].search([("code", "=", module_code)], limit=1) if module_code else False
        return str(self._render(tab, module if scope == "module" else False))

    # ---------------------------------------------------------------- outputs
    @api.depends("answer_ids.state", "answer_ids.gap", "answer_ids.future", "answer_ids.reason",
                 "answer_ids.applicable", "answer_ids.q_answered")
    def _compute_outputs(self):
        for rec in self:
            rec.summary_html = rec._render_summary() if rec.id else False
            rec.gaps_html = rec._render_gaps() if rec.id else False
            rec.map_html = Markup(f'<div class="o_azm_output" dir="rtl">{fin_engine.module_map(rec._modules_nav())}</div>') if rec.id else False
            rec.output_html = rec._render("book") if rec.id else False

    def _banner(self):
        if self.is_demo:
            return fin_engine.note("مثال افتراضي للتجربة فقط.", "warn")
        if self.state != "approved":
            return fin_engine.note("مسودة غير معتمدة · صياغة من الإفادات؛ الأدلة لم تُتحقق.")
        return ""

    def _render_summary(self):
        self.ensure_one()
        rows = []
        for m in self._modules_nav():
            lines = self.answer_ids.filtered(lambda a, c=m["code"]: a.module_id.code == c and a.applicable)
            cnt = {k: len(lines.filtered(lambda a, k=k: a.state == k)) for k, _n in STATES}
            pct = round(100 * m["answered"] / m["questions"]) if m["questions"] else 0
            rows.append(
                f"<tr><td><b>FIN.{_e(m['code'])}</b></td><td>{_e(m['name'])}</td><td>{m['applicable']}/{m['total']}</td>"
                f"<td>{m['answered']}/{m['questions']}</td>"
                f"<td>{cnt['full']}</td><td>{cnt['partial']}</td><td>{cnt['unavailable']}</td><td>{cnt['unknown']}</td>"
                f"<td>{cnt['na']}</td>"
                f"<td><div class='o_azm_fin_bar'><span style='width:{pct}%'></span></div> {pct}%</td></tr>")
        head = ("<tr><th>الكود</th><th>الموديول</th><th>متطلبات منطبقة</th><th>أسئلة مُجابة</th><th>بالكامل</th>"
                "<th>جزئيًا</th><th>غير منفذ</th><th>لا أعرف</th><th>لا ينطبق</th><th>الاكتمال</th></tr>")
        return Markup(f'<div class="o_azm_fin_out" dir="rtl">{self._banner()}'
                      f'<table class="o_azm_fin_table"><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table></div>')

    def _render_gaps(self):
        self.ensure_one()
        app = self.answer_ids.filtered("applicable")
        sections = [
            ("partial", "الفجوات (مطبّق جزئيًا)", "gap", "التغطية والمشاكل الحالية"),
            ("unavailable", "غير منفذ · التوجه المستهدف", "future", "التوجه المستهدف"),
            ("unknown", "غير معروف · يحتاج استيضاح", "current", "ما تمت الإجابة عليه"),
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
                            f"<td>{_e(a.module_id.name)}</td><td style='white-space:pre-line'>{_e(text)}</td></tr>")
            html.append("</tbody></table>")
        html.append("</div>")
        return Markup("".join(html))

    # ---------------------------------------------------------------- actions
    def _azm_outstanding(self):
        self.ensure_one()
        return max(self.question_count - self.answered_count, 0)

    def _azm_returned_outstanding(self, returns):
        """What is still owed on the parts a review sent back.

        Counted the way the assessment counts itself, which it did not use to be: over
        the applicable lines only, and through _question_totals, where «لا ينطبق»
        is one question answered by its reason. Reading q_total directly counted both
        the requirements that do not apply to this entity and the ones marked not
        applicable — neither of which the workspace will ever let anybody answer. A
        returned module holding one of either could never be sent back for review
        again: the figure never reached zero, so the button stayed dead for good.
        """
        self.ensure_one()
        lines = self.answer_ids.filtered(
            lambda line: line.applicable and returns._covers(line))
        total, answered = lines._question_totals()
        return max(total - answered, 0)

    def action_open_workspace(self, focus=None):
        """Open the workspace, on a named part of it when one is asked for.

        Somebody sent to fix a returned module should arrive at that module, not at
        whichever one the workspace happens to open on first.
        """
        self.ensure_one()
        params = {"assessment_id": self.id}
        if focus and focus.get("level") == "module":
            params["module_code"] = self.env["azm.fin.module"].browse(focus["id"]).code
        elif focus and focus.get("level") == "topic":
            topic = self.env["azm.fin.topic"].browse(focus["id"])
            params["module_code"] = topic.module_id.code
        elif focus and focus.get("level") == "requirement":
            requirement = self.env["azm.fin.requirement"].browse(focus["id"])
            params["module_code"] = requirement.module_id.code
            params["requirement_code"] = requirement.code
        return {"type": "ir.actions.client", "tag": "azm_fin_workspace", "name": self.name,
                "params": params}

    def action_submit(self):
        """Send the financial assessment to whoever reviews it."""
        for rec in self.filtered(lambda r: r.state == "draft"):
            rec._submit_for_review("مراجعة إفادة النموذج المالي")

    def action_back_to_draft(self):
        self.filtered(lambda r: r.state == "review")._workflow().write({"state": "draft"})

    def action_approve(self):
        # The reviewer is who the work was sent to; making them unable to accept it
        # left the role with nothing to do but look. What stays is the part that
        # matters — nobody signs off their own work, which is checked below.
        if not (self.env.user.has_group("azm_operating_model.azm_group_reviewer")
                or self.env.user.has_group("azm_operating_model.azm_group_manager")):
            raise UserError("الاعتماد للمراجع أو مدير النموذج.")
        for rec in self:
            if rec.state != "review":
                raise UserError("الاعتماد يتم من حالة «تحت المراجعة» فقط.")
            rec._azm_check_not_own_work()
            answers = {a.code: a._snapshot() for a in rec.answer_ids if a.state or a.q_answered}
            self.env["azm.fin.version"].create({
                "assessment_id": rec.id, "version": rec.version,
                "answers_json": json.dumps(answers, ensure_ascii=False, indent=1),
                "summary_html": "".join(str(rec._render(tab)) for tab in ("book", "rules", "workflow", "authority",
                                                                            "reports", "integration", "gaps", "future")),
            })
            rec._workflow().write({"state": "approved", "approved_by_id": self.env.user.id,
                       "approved_date": fields.Datetime.now()})

    def action_new_version(self):
        self.ensure_one()
        if self.state != "approved":
            raise UserError("الإصدار الجديد يتعمل من إفادة معتمدة.")
        new = self.copy({"version": self.version + 1, "previous_id": self.id, "name": "جديد",
                         "scope_ids": [Command.set(self.scope_ids.ids)]})
        self._workflow().state = "archived"
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
        """Deterministic demo answers for every question: mostly applied, with gaps, not implemented,
        unknown and a few «لا ينطبق»."""
        for rec in self:
            if rec.state != "draft":
                raise UserError("المثال يتعمل على مسودة فقط.")
            rec.answer_ids.qanswer_ids.unlink()
            rec.answer_ids.write({"na": False, "reason": False})
            for line in rec.answer_ids.filtered("applicable"):
                line._fill_demo(zlib.crc32(f"{rec.entity_id.code}/{line.code}".encode()))
            rec.is_demo = True
        return True

    def action_reset_answers(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError("المسح متاح للمسودة فقط.")
            rec.answer_ids.qanswer_ids.unlink()
            rec.answer_ids.write({"na": False, "reason": False})
            rec.is_demo = False


class AzmFinAnswer(models.Model):
    """One line per requirement in an assessment; its status and texts are derived from the question answers."""
    _name = "azm.fin.answer"
    _inherit = ["azm.assignable"]
    _description = "إجابة متطلب مالي"
    _order = "module_sequence, topic_sequence, requirement_sequence, id"

    assessment_id = fields.Many2one("azm.fin.assessment", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="assessment_id.company_id", store=True)
    entity_id = fields.Many2one(related="assessment_id.entity_id", store=True, string="الكيان")
    requirement_id = fields.Many2one("azm.fin.requirement", "المتطلب", required=True, ondelete="restrict", index=True)
    module_id = fields.Many2one(related="requirement_id.module_id", store=True, string="الموديول")
    topic_id = fields.Many2one(related="requirement_id.topic_id", store=True, string="الموضوع الفرعي")
    module_sequence = fields.Integer(related="requirement_id.module_sequence", store=True, string="ترتيب الموديول")
    topic_sequence = fields.Integer(related="requirement_id.topic_sequence", store=True, string="ترتيب الموضوع")
    requirement_sequence = fields.Integer(related="requirement_id.sequence", store=True, string="ترتيب المتطلب")
    # stored so the assessment can leave a retired requirement out without joining to it
    requirement_active = fields.Boolean(related="requirement_id.active", store=True, index=True)
    code = fields.Char(related="requirement_id.code", store=True, string="الكود")
    req_id = fields.Char(related="requirement_id.req_id", string="Requirement ID")
    title = fields.Char(related="requirement_id.title", string="المتطلب ")
    profile = fields.Selection(related="requirement_id.profile", store=True, string="قالب الإجابة")
    scope_code = fields.Selection(related="requirement_id.scope_code", store=True, string="نطاق الانطباق")
    applicable = fields.Boolean("منطبق", compute="_compute_applicable", store=True)
    qanswer_ids = fields.One2many("azm.fin.qanswer", "line_id", string="إجابات الأسئلة", copy=True)
    na = fields.Boolean("لا ينطبق على الكيان", copy=True)
    reason = fields.Text("سبب عدم الانطباق", copy=True)
    attachment_ids = fields.Many2many("ir.attachment", string="الأدلة")

    # derived from the question answers
    state = fields.Selection(STATES, "حالة التطبيق", compute="_compute_from_questions", store=True)
    impl = fields.Char("وسيلة التنفيذ", compute="_compute_from_questions", store=True)
    rule_state = fields.Char("حالة القاعدة", compute="_compute_from_questions", store=True)
    target = fields.Char("التوجه المستهدف", compute="_compute_from_questions", store=True)
    current = fields.Text("الإجابات (الوضع الحالي)", compute="_compute_from_questions", store=True)
    issues = fields.Text("تغطية النظام والمشاكل الحالية", compute="_compute_from_questions", store=True)
    gap = fields.Text("الفجوة", compute="_compute_from_questions", store=True)
    target_note = fields.Text("التغييرات المطلوبة والأولوية", compute="_compute_from_questions", store=True)
    future = fields.Text("التوجه والتغييرات المطلوبة", compute="_compute_from_questions", store=True)
    q_total = fields.Integer("أسئلة ظاهرة", compute="_compute_from_questions", store=True)
    q_answered = fields.Integer("أسئلة مُجابة", compute="_compute_from_questions", store=True)
    is_done = fields.Boolean("مكتمل", compute="_compute_from_questions", store=True)

    _assessment_requirement_uniq = models.Constraint(
        "UNIQUE(assessment_id, requirement_id)", "المتطلب متكرر في نفس الإفادة.")

    @api.depends("requirement_id.scope_code", "assessment_id.scope_ids")
    def _compute_applicable(self):
        for a in self:
            code = a.requirement_id.scope_code
            a.applicable = code == "ALL" or code in a.assessment_id.scope_ids.mapped("code")

    # ---------------------------------------------------------------- derivation
    def _answers_by_question(self):
        self.ensure_one()
        return {qa.question_id.id: qa for qa in self.qanswer_ids}

    def _visible(self, qas=None):
        """Visible questions of the requirement, following the «يظهر لو» conditions."""
        self.ensure_one()
        qas = self._answers_by_question() if qas is None else qas
        questions = self.requirement_id.question_ids
        values = {q.key: qas[q.id]._names() if q.id in qas else set() for q in questions}
        keys = fin_engine.visible_keys([{"key": q.key, "condition": q._condition()} for q in questions], values)
        return questions.filtered(lambda q: q.key in keys)

    @api.depends("na", "reason", "requirement_id.question_ids", "qanswer_ids.option_id", "qanswer_ids.option_ids",
                 "qanswer_ids.has_number", "qanswer_ids.value_number", "qanswer_ids.table_json", "qanswer_ids.note",
                 "qanswer_ids.note_tags", "qanswer_ids.priority")
    def _compute_from_questions(self):
        for line in self:
            qas = line._answers_by_question()
            visible = line._visible(qas)
            answered = visible.filtered(lambda q: q.id in qas and qas[q.id].is_answered)

            def pick(role):
                q = visible.filtered(lambda x: x.role == role)[:1]
                return qas.get(q.id) if q else None

            status, impl, rule, target = pick("status"), pick("impl"), pick("rule"), pick("target")
            state = STATUS_OPTIONS.get(status.option_id.name) if status and status.option_id else False
            line.state = "na" if line.na else state
            line.impl = "، ".join(impl.option_ids.mapped("name")) if impl else False
            line.rule_state = rule.option_id.name if rule and rule.option_id else False
            line.target = target.option_id.name if target and target.option_id else False
            line.issues = (status._note_text() if status else "") or False
            facts = [f"{q.label}: {qas[q.id]._display()}" for q in answered if q.role in ("main", "follow")]
            line.current = "\n".join(facts) or False
            line.gap = line.issues if line.state in ("partial", "unavailable") else False
            line.target_note = (target._note_text() if target else "") or False
            future = " — ".join(x for x in (line.target, line.target_note) if x)
            line.future = future or False
            line.q_total = len(visible)
            line.q_answered = len(answered)
            line.is_done = bool((line.reason or "").strip()) if line.na else bool(visible) and len(answered) == len(visible)

    def _question_totals(self):
        """(visible questions, answered) — a «لا ينطبق» requirement counts as one question answered by its reason."""
        total = answered = 0
        for line in self:
            if line.na:
                total += 1
                answered += int(bool((line.reason or "").strip()))
            else:
                total += line.q_total
                answered += line.q_answered
        return total, answered

    # ---------------------------------------------------------------- answering
    def _set_answer(self, question_id, vals):
        self.ensure_one()
        question = self.requirement_id.question_ids.filtered(lambda q: q.id == question_id)
        if not question:
            raise UserError("السؤال غير موجود في هذا المتطلب.")
        option_ids = set(question.option_ids.ids)
        clean = {}
        if "option_id" in vals:
            if vals["option_id"] and vals["option_id"] not in option_ids:
                raise UserError("اختيار غير معروف لهذا السؤال.")
            clean["option_id"] = vals["option_id"] or False
            if question.qtype == "table" and vals["option_id"]:
                clean["table_json"] = False
        if "option_ids" in vals:
            ids = [i for i in vals["option_ids"] or [] if i in option_ids]
            clean["option_ids"] = [Command.set(ids)]
        if "number" in vals:
            number = vals["number"]
            clean.update({"value_number": float(number or 0), "has_number": number not in (None, False, "")})
        if "table" in vals:
            rows = [[str(c or "") for c in row] for row in (vals["table"] or []) if isinstance(row, list)]
            rows = [row for row in rows if any(c.strip() for c in row)]
            clean["table_json"] = json.dumps(rows, ensure_ascii=False) if rows else False
            if rows:
                clean["option_id"] = False
        if "note" in vals:
            clean["note"] = vals["note"] or False
        if "note_tags" in vals:
            allowed = NOTE_LISTS.get(question.note_label or "", [])
            tags = [t for t in vals["note_tags"] or [] if t in allowed]
            clean["note_tags"] = json.dumps(tags, ensure_ascii=False) if tags else False
            if OTHER not in tags and "note" not in vals:
                clean["note"] = False
        if "priority" in vals:
            clean["priority"] = vals["priority"] if vals["priority"] in dict(PRIORITIES) else False
        qa = self.qanswer_ids.filtered(lambda a: a.question_id == question)
        if qa:
            qa.write(clean)
        else:
            qa = self.env["azm.fin.qanswer"].create({"line_id": self.id, "question_id": question.id, **clean})
        return qa

    def _fill_demo(self, seed):
        self.ensure_one()
        pick = seed % 20
        state = ("full" if pick < 9 else "partial" if pick < 14 else "unavailable" if pick < 17
                 else "unknown" if pick < 18 else "na")
        if state == "na":
            self.write({"na": True, "reason": NA_REASONS[0]})
            return
        title = self.requirement_id.title
        status_name = {v: k for k, v in STATUS_OPTIONS.items()}[state]
        rule_name = {"full": "معتمدة وموثقة", "partial": "مطبقة دون توثيق", "unavailable": "غير موجودة",
                     "unknown": "لا أعرف"}[state]
        target_name = {"full": "استمرار", "partial": "تحسين", "unavailable": "أحتاج مقترحًا",
                       "unknown": "لا أعرف"}[state]
        notes = {
            "status": {"full": f"«{title}» مغطى في النظام الحالي دون مشاكل جوهرية.",
                       "partial": f"يُطبق «{title}» على جزء من الحالات فقط ويُستكمل يدويًا؛ يلزم توحيده وتوثيقه.",
                       "unavailable": f"لا توجد ممارسة قائمة لـ«{title}» حاليًا.",
                       "unknown": ""}[state],
            "target": {"full": "", "partial": f"توحيد «{title}» في النظام وتوثيق القاعدة — أولوية متوسطة.",
                       "unavailable": f"تصميم قاعدة موحّدة لـ«{title}» ضمن النموذج المستهدف — أولوية مرتفعة.",
                       "unknown": ""}[state],
        }
        values, creates = {}, []
        for i, q in enumerate(self.requirement_id.question_ids):
            cond = q._condition()
            if cond and not (values.get(cond["q"], set()) & set(cond["in"])):
                continue
            opts = q.option_ids
            main = opts.filtered(lambda o: o.kind not in FALLBACK_KINDS) or opts
            s = seed >> (i % 16)
            vals = {"line_id": self.id, "question_id": q.id}
            if q.role in ("status", "rule", "target"):
                name = {"status": status_name, "rule": rule_name, "target": target_name}[q.role]
                opt = opts.filtered(lambda o, n=name: o.name == n)[:1] or main[:1]
                vals["option_id"] = opt.id
                tags = [t for t in NOTE_LISTS.get(q.note_label or "", []) if t != OTHER]
                if tags and notes[q.role]:
                    first = 0 if state == "full" else 1 + s % (len(tags) - 1)
                    vals["note_tags"] = json.dumps(sorted({tags[first], tags[(first + 3) % len(tags)]} if state != "full"
                                                          else {tags[0]}, key=tags.index), ensure_ascii=False)
                    if q.role == "target":
                        vals["priority"] = "high" if state == "unavailable" else "medium"
                values[q.key] = {opt.name}
            elif q.qtype == "select":
                opt = main[s % len(main)] if main else main
                vals["option_id"] = opt.id
                values[q.key] = {opt.name}
            elif q.qtype == "multi":
                chosen = (main[s % len(main)] | main[(s // 7) % len(main)]) if main else main
                vals["option_ids"] = [Command.set(chosen.ids)]
                values[q.key] = set(chosen.mapped("name"))
            elif q.qtype == "number":
                unit = q.unit or ""
                base = 5 + s % 26 if unit in ("%", "يوم", "يوم عمل") else 2 + s % 10
                if unit == "جنيه":
                    base = (5 + s % 45) * 1000
                vals.update({"value_number": base, "has_number": True})
            elif q.qtype == "table":
                rows = []
                for r in range(2):
                    row = []
                    for c, col in enumerate(q._columns()):
                        options = [o for o in col.get("options") or [] if o != "لا يوجد"]
                        kind = col.get("type")
                        row.append(options[(s + r + c) % len(options)] if options
                                   else str((5 + (s + r + c) % 20) * (1000 if "مبلغ" in col["label"] or col["label"] in ("القيمة", "حد القيمة", "البدل اليومي", "حد الصرف للمرة") else 1)) if kind == "number"
                                   else f"2026-{1 + (s + r) % 12:02d}-28" if kind == "date"
                                   else f"{col['label']} — مثال {r + 1}")
                    rows.append(row)
                vals["table_json"] = json.dumps(rows, ensure_ascii=False)
            creates.append(vals)
        self.env["azm.fin.qanswer"].create(creates)

    # ---------------------------------------------------------------- payloads
    def _workspace_dict(self):
        self.ensure_one()
        req = self.requirement_id
        qas = self._answers_by_question()
        visible = set(self._visible(qas).ids)
        questions = []
        for q in req.question_ids:
            data = q._schema()
            qa = qas.get(q.id)
            data.update({"visible": q.id in visible, "answered": bool(qa and qa.is_answered),
                         "value": qa._value() if qa else self.env["azm.fin.qanswer"]._empty_value()})
            questions.append(data)
        prof = PROFILES[req.profile]
        return {
            "answer_id": self.id, "requirement_id": req.id,
            "code": req.code, "req_id": req.req_id or "", "title": req.title,
            "tree_ref": req.tree_ref or "",
            "question": req.question, "profile": req.profile, "profile_name": prof[0],
            "scope_code": req.scope_code, "scope_name": SCOPES.get(req.scope_code, ""), "source": req.source,
            "pack": req.pack or "", "owner": req.owner or "", "response_type": req.response_type or "",
            "applicable": self.applicable, "done": self.is_done, "state": self.state or False,
            "na": self.na, "reason": self.reason or "", "q_total": self.q_total, "q_answered": self.q_answered,
            "attachments": len(self.attachment_ids), "questions": questions,
        }

    def _engine_dict(self):
        self.ensure_one()
        req = self.requirement_id
        qas = self._answers_by_question()
        qa_list, missing = [], []
        for q in self._visible(qas).filtered(lambda x: x.role in ("main", "follow")):
            qa = qas.get(q.id)
            if not (qa and qa.is_answered):
                missing.append(q.label)
                continue
            qa_list.append({
                "code": q.code, "key": q.key, "label": q.label, "qtype": q.qtype, "unit": q.unit or "",
                "display": qa._display(), "columns": q._columns(), "rows": qa._rows(),
                "names": sorted(qa._names()), "fallback": qa._is_fallback(),
            })
        return {
            "code": req.code, "req_id": req.req_id or "", "title": req.title, "question": req.question,
            "profile": req.profile, "profile_name": PROFILES[req.profile][0],
            "scope_name": SCOPES.get(req.scope_code, ""), "topic": req.topic_id.name or "",
            "topic_code": req.topic_id.code or "", "pack": req.pack or "", "owner": req.owner or "",
            "state": self.state or False, "impl": [x for x in (self.impl or "").split("، ") if x],
            "rule": self.rule_state or "", "target": self.target or "", "issues": self.issues or "",
            "target_note": self.target_note or "",
            "reason": self.reason or "", "done": self.is_done, "qa": qa_list, "missing": missing,
            "q_total": self.q_total, "q_answered": self.q_answered,
        }

    def _snapshot(self):
        self.ensure_one()
        qas = self._answers_by_question()
        return {
            "state": self.state or False, "na": self.na, "reason": self.reason or "",
            "answers": {q.code: {"value": qas[q.id]._display(), "note": qas[q.id]._note_text()}
                        for q in self._visible(qas) if q.id in qas and qas[q.id].is_answered},
        }

    def write(self, vals):
        if {"na", "reason"} & set(vals) and not self.env["azm.answer"]._azm_lock_lifted():
            if any(a.assessment_id.state != "draft" for a in self):
                raise UserError("الإفادة مش في حالة مسودة؛ لا يمكن تعديل الإجابات.")
            self._azm_check_assignee()
            self._azm_check_returns()
        return super().write(vals)

    # ---------------------------------------------------------------- whose part
    def _azm_part_key(self):
        self.ensure_one()
        return (self.assessment_id.id, self.module_id.id)

    def _azm_part_name(self):
        self.ensure_one()
        return f"FIN.{self.module_id.code}"

    @api.model
    def _azm_assignments(self, lines):
        found = self.env["azm.assignment"].sudo().search(
            [("fin_assessment_id", "in", lines.assessment_id.ids)])
        return {(a.fin_assessment_id.id, a.module_id.id): a.user_ids.ids for a in found}


class AzmFinQAnswer(models.Model):
    """The answer to one question of a requirement (created when the question is first answered)."""
    _name = "azm.fin.qanswer"
    _description = "إجابة سؤال مالي"
    _order = "line_id, question_sequence, id"

    line_id = fields.Many2one("azm.fin.answer", "المتطلب", required=True, ondelete="cascade", index=True)
    assessment_id = fields.Many2one(related="line_id.assessment_id", store=True, index=True)
    company_id = fields.Many2one(related="line_id.company_id", store=True)
    question_id = fields.Many2one("azm.fin.question", "السؤال", required=True, ondelete="restrict", index=True)
    question_sequence = fields.Integer(related="question_id.sequence", store=True)
    code = fields.Char(related="question_id.code", string="الكود")
    label = fields.Char(related="question_id.label", string="السؤال ")
    role = fields.Selection(related="question_id.role", string="الدور")
    qtype = fields.Selection(related="question_id.qtype", string="شكل الإجابة")
    option_id = fields.Many2one("azm.fin.option", "الاختيار", ondelete="restrict")
    option_ids = fields.Many2many("azm.fin.option", "azm_fin_qanswer_option_rel", "qanswer_id", "option_id",
                                  string="الاختيارات")
    value_number = fields.Float("الرقم")
    has_number = fields.Boolean("فيه رقم")
    table_json = fields.Text("الجدول (JSON)")
    note = fields.Text("تفاصيل إضافية")
    note_tags = fields.Text("اختيارات خانة النص (JSON)")
    priority = fields.Selection(PRIORITIES, "الأولوية")
    value_display = fields.Char("الإجابة", compute="_compute_value_display")
    is_answered = fields.Boolean("مُجاب", compute="_compute_is_answered", store=True)

    _line_question_uniq = models.Constraint("UNIQUE(line_id, question_id)", "السؤال متكرر في نفس المتطلب.")

    @api.depends("question_id.qtype", "option_id", "option_ids", "has_number", "table_json")
    def _compute_is_answered(self):
        for qa in self:
            qtype = qa.question_id.qtype
            qa.is_answered = bool(
                qa.option_ids if qtype == "multi" else qa.has_number if qtype == "number"
                else (qa.option_id or qa._rows()) if qtype == "table" else qa.option_id)

    def _compute_value_display(self):
        for qa in self:
            qa.value_display = qa._display()

    def _rows(self):
        return json.loads(self.table_json) if self.table_json else []

    def _tags(self):
        return json.loads(self.note_tags) if self.note_tags else []

    def _note_text(self):
        """The text box answer: the chosen items, the free detail and the priority."""
        self.ensure_one()
        parts = [t for t in self._tags() if t != OTHER]
        if self.note:
            parts.append(self.note)
        text = "، ".join(parts)
        if self.priority:
            text = f"{text} — الأولوية: {dict(PRIORITIES)[self.priority]}" if text else f"الأولوية: {dict(PRIORITIES)[self.priority]}"
        return text

    def _names(self):
        return set(self.option_ids.mapped("name")) | ({self.option_id.name} if self.option_id else set())

    def _is_fallback(self):
        chosen = self.option_ids | self.option_id
        return bool(chosen) and all(o.kind in FALLBACK_KINDS for o in chosen)

    def _display(self):
        self.ensure_one()
        qtype = self.question_id.qtype
        if qtype == "multi":
            return "، ".join(self.option_ids.mapped("name"))
        if qtype == "number":
            return f"{self.value_number:g} {self.question_id.unit or ''}".strip() if self.has_number else ""
        if qtype == "table":
            rows = self._rows()
            return f"{len(rows)} صف" if rows else (self.option_id.name or "")
        return self.option_id.name or ""

    @api.model
    def _empty_value(self):
        return {"option_id": False, "option_ids": [], "number": None, "table": [], "note": "", "note_tags": [],
                "priority": False}

    def _value(self):
        self.ensure_one()
        return {"option_id": self.option_id.id or False, "option_ids": self.option_ids.ids,
                "number": self.value_number if self.has_number else None, "table": self._rows(),
                "note": self.note or "", "note_tags": self._tags(), "priority": self.priority or False}

    def _check_draft(self):
        if not self.env["azm.answer"]._azm_lock_lifted() and any(qa.line_id.assessment_id.state != "draft" for qa in self):
            raise UserError("الإفادة مش في حالة مسودة؛ لا يمكن تعديل الإجابات.")

    def _check_writable(self):
        """Every reason this answer may not be written, asked in one place.

        The return lock was missing here. A reviewer who sends one module back leaves
        the rest of the assessment as they reviewed it, and the procurement twin
        enforces that on every answer — but on this side only «لا ينطبق» and its reason
        went through it, while every actual answer is written as one of these lines. So
        a preparer could keep editing modules the reviewer had already accepted, which
        is the one thing returning named parts exists to prevent.
        """
        self._check_draft()
        self.line_id._azm_check_assignee()
        self.line_id._azm_check_returns()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # a question is first answered by creating this line, so the checks belong here
        # as much as on write
        records._check_writable()
        return records

    def write(self, vals):
        self._check_writable()
        return super().write(vals)

    def unlink(self):
        self._check_writable()
        return super().unlink()


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
