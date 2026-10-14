import json
import zlib

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError

from .azm_answer import AZM_SKIP_LOCK_TOKEN

from . import engine

PURCHASE_KINDS = [
    ("goods", "أصناف ومستلزمات"),
    ("assets", "أصول وأجهزة"),
    ("services", "خدمات واستشارات"),
    ("works", "أعمال ومقاولات"),
    ("subscriptions", "اشتراكات وتجديدات"),
]
SCENARIOS = [
    ("standard", "شراء عادي"),
    ("urgent", "شراء عاجل"),
    ("sole_source", "مورد وحيد"),
    ("direct", "شراء مباشر"),
    ("petty_cash", "شراء من عهدة"),
]


class AzmAssessment(models.Model):
    _name = "azm.assessment"
    _description = "إفادة AZM"
    _inherit = ["mail.thread", "mail.activity.mixin", "azm.reviewable"]
    _order = "create_date desc, id desc"

    name = fields.Char("المرجع", required=True, copy=False, readonly=True, default="جديد")
    entity_id = fields.Many2one("azm.entity", "الكيان", required=True, tracking=True)
    company_id = fields.Many2one("res.company", required=True, compute="_compute_company_id", store=True,
                                 readonly=False, precompute=True,
                                 help="شركة الكيان؛ تُستخدم في صلاحيات الشركات.")
    purchase_kind = fields.Selection(PURCHASE_KINDS, "نوع المشتريات", required=True, tracking=True)
    scenario = fields.Selection(SCENARIOS, "المسار", required=True, tracking=True)
    version = fields.Integer("الإصدار", default=1, readonly=True, copy=False)
    state = fields.Selection([
        ("draft", "مسودة"),
        ("review", "تحت المراجعة"),
        ("approved", "معتمدة"),
        ("archived", "إصدار سابق"),
    ], default="draft", required=True, tracking=True, copy=False, string="الحالة")
    user_id = fields.Many2one("res.users", "مُعد الإفادة", default=lambda self: self.env.user, tracking=True)
    reviewer_id = fields.Many2one("res.users", "المراجع", tracking=True)
    assignment_ids = fields.One2many("azm.assignment", "proc_assessment_id",
                                     string="توزيع المراحل")
    approved_by_id = fields.Many2one("res.users", "اعتمدها", readonly=True, copy=False)
    approved_date = fields.Datetime("تاريخ الاعتماد", readonly=True, copy=False)
    is_demo = fields.Boolean("مثال افتراضي", copy=False)
    answer_ids = fields.One2many("azm.answer", "assessment_id", string="الإجابات", copy=True)
    finding_ids = fields.One2many("azm.finding", "assessment_id", string="سجل المخاطر")
    version_ids = fields.One2many("azm.assessment.version", "assessment_id", string="الإصدارات المعتمدة")
    previous_id = fields.Many2one("azm.assessment", "الإصدار السابق", readonly=True, copy=False)

    progress = fields.Float("نسبة الاكتمال", compute="_compute_progress")
    visible_count = fields.Integer(compute="_compute_progress")
    answered_count = fields.Integer("أسئلة مُجابة", compute="_compute_progress")
    known_count = fields.Integer(compute="_compute_progress")
    risk_count = fields.Integer(compute="_compute_progress")
    finding_count = fields.Integer(compute="_compute_finding_count")

    output_map_html = fields.Html(compute="_compute_output_html", sanitize=False, string="خريطة الدورة")
    output_html = fields.Html(compute="_compute_output_html", sanitize=False, string="الوضع الحالي")

    _version_uniq = models.Constraint(
        "UNIQUE(entity_id, purchase_kind, scenario, version)",
        "فيه إفادة بنفس الكيان ونوع المشتريات والمسار والإصدار؛ افتحها أو اعمل إصدار جديد منها.")

    @api.depends("entity_id")
    def _compute_company_id(self):
        # an assessment belongs to the company of its entity (company access rules)
        for rec in self:
            rec.company_id = rec.entity_id.sudo().company_id or rec.company_id or self.env.company

    # ---------------------------------------------------------------- crud
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "جديد") == "جديد":
                vals["name"] = self.env["ir.sequence"].sudo().next_by_code("azm.assessment") or "جديد"
        records = super().create(vals_list)
        records._ensure_answers()
        return records

    @api.model
    def _ensure_all_answers(self):
        """Give every assessment a line for every question, after a catalogue reload.

        A question added to the catalogue has no answer line on the assessments that
        already existed, and the workspace reads a line for every *visible* question —
        so without this the whole workspace of every older assessment stops opening."""
        self.search([])._ensure_answers()

    def _ensure_answers(self):
        questions = self.env["azm.question"].search([])
        lines = []
        for rec in self:
            have = set(rec.answer_ids.question_id.ids)
            lines += [{"assessment_id": rec.id, "question_id": q.id} for q in questions if q.id not in have]
        if lines:
            self.env["azm.answer"].create(lines)
        self._refresh_visibility()

    # ---------------------------------------------------------------- engine data
    def _stages(self):
        return self.env["azm.stage"].search([])

    def _answers_by_stage(self):
        """{stage id: {question id: line}} — built once instead of rescanning every
        answer of the assessment for each stage in turn."""
        self.ensure_one()
        grouped = {}
        for line in self.answer_ids:
            grouped.setdefault(line.stage_id.id, {})[line.question_id.id] = line
        return grouped

    def _stage_payload(self, stage, catalogue=None, by_stage=None):
        """Questions, ordered answers (only those visible) for one stage.

        ``catalogue`` and ``by_stage`` let a scan over many assessments build the stage's
        question dicts and this assessment's answer index once each, instead of per
        assessment and stage — which is most of what the Home page used to cost."""
        self.ensure_one()
        sdict, qdicts = catalogue if catalogue else stage._engine_catalogue()
        by_q = (by_stage if by_stage is not None else self._answers_by_stage()).get(stage.id, {})
        answers = {}
        for qd in qdicts:
            line = by_q.get(qd["id"])
            if not line:
                continue
            # visible_questions only reads the answers — is_applied and condition both
            # do — so the defensive copy was rebuilding the whole dict once per question,
            # which is quadratic in the questions of a stage and bought nothing
            if engine.visible_questions(sdict, [qd], answers):
                value = line._engine_value()
                if value is not None:
                    answers[qd["key"]] = value
        return sdict, qdicts, answers, by_q

    def _rules(self):
        return [r._engine_dict() for r in self.env["azm.risk.rule"].search([])]

    def _refresh_visibility(self):
        for rec in self:
            for stage in rec._stages():
                sdict, qdicts, answers, by_q = rec._stage_payload(stage)
                visible = {q["id"] for q in engine.visible_questions(sdict, qdicts, answers)}
                for qid, line in by_q.items():
                    flag = qid in visible
                    if line.is_visible != flag:
                        line.with_context(azm_no_visibility=True,
                                         azm_skip_lock=AZM_SKIP_LOCK_TOKEN).is_visible = flag

    # ---------------------------------------------------------------- computes
    @api.depends("answer_ids.has_value", "answer_ids.is_known", "answer_ids.is_visible")
    def _compute_progress(self):
        # progress and risk_count are both columns of the list view, so this runs for a
        # whole page at once: the stages and their question dicts are the same for every
        # row and are read once, not once per assessment
        rules = self._rules() if self else []
        stages = self._stages() if self else self.env["azm.stage"]
        catalogues = {stage.id: stage._engine_catalogue() for stage in stages}
        for rec in self:
            vis = rec.answer_ids.filtered("is_visible")
            answered = vis.filtered("has_value")
            rec.visible_count = len(vis)
            # counted here rather than read back off the percentage: "nine questions
            # left" is what somebody answering wants, and it has to be exact
            rec.answered_count = len(answered)
            rec.known_count = len(vis.filtered("is_known"))
            rec.progress = 100.0 * len(answered) / len(vis) if vis else 0.0
            risks = 0
            if rec.id:
                by_stage = rec._answers_by_stage()
                for stage in stages:
                    sdict, qdicts, answers, _by_q = rec._stage_payload(
                        stage, catalogues[stage.id], by_stage)
                    risks += len(engine.findings(sdict, qdicts, answers, rules))
            rec.risk_count = risks

    def _compute_finding_count(self):
        for rec in self:
            rec.finding_count = len(rec.finding_ids)

    @api.depends("answer_ids.option_id", "answer_ids.option_ids", "answer_ids.value_number")
    def _compute_output_html(self):
        for rec in self:
            rec.output_html = rec._render("book") if rec.id else False
            rec.output_map_html = rec._render("workflow") if rec.id else False

    def _render(self, tab, stage=False, doc_code=None):
        """Render one output. ``doc_code`` is the code the published document carries,
        so the body of a PDF names itself the way its cover does."""
        self.ensure_one()
        rules = self._rules()
        if stage:
            sdict, qdicts, answers, _ = self._stage_payload(stage)
            if doc_code:
                sdict = {**sdict, "doc_code": doc_code}
            body = engine.render_stage(tab, sdict, qdicts, answers, rules)
        else:
            data = []
            for st in self._stages():
                sdict, qdicts, answers, _ = self._stage_payload(st)
                data.append({"stage": sdict, "questions": qdicts, "answers": answers})
            body = engine.render_cycle(tab, data, rules)
        banner = ""
        if self.is_demo:
            banner = engine.note("مثال افتراضي للتجربة فقط · يتضمن عمدًا ممارسات تحتاج معالجة.", "warn")
        elif self.state != "approved":
            banner = engine.note("مسودة غير معتمدة · صياغة من الإفادات؛ الأدلة لم تُتحقق.", "info")
        return Markup(f'<div class="o_azm_output" dir="rtl">{banner}{body}</div>')

    # ---------------------------------------------------------------- workspace RPC
    def workspace_data(self, stage_id=None, tab="book", scope="stage"):
        """Everything the OWL workspace needs in one round trip."""
        self.ensure_one()
        stages = self._stages()
        stage = stages.browse(stage_id) if stage_id else stages[:1]
        rules = self._rules()
        nav = []
        for st in stages:
            sdict, qdicts, answers, _ = self._stage_payload(st)
            stats = engine.stage_stats(sdict, qdicts, answers)
            nav.append({
                "id": st.id, "code": st.code, "name": st.name, **stats,
                "risks": len(engine.findings(sdict, qdicts, answers, rules)),
                "status": engine.stage_status(sdict, answers),
            })
        returns = self.env["azm.review.return"]._open_for(self)
        sdict, qdicts, answers, by_q = self._stage_payload(stage)
        visible = engine.visible_questions(sdict, qdicts, answers)
        questions = []
        for qd in visible:
            line = by_q.get(qd["id"])
            if not line:
                continue   # a question the catalogue gained since this assessment was made
            q = line.question_id
            covered = bool(returns) and returns._covers(line)
            questions.append({
                # a review that sent parts back leaves the rest as it was reviewed
                "locked": bool(returns) and not covered,
                # said outright rather than left to be read off "locked", which is
                # false both for a returned question and for every question when
                # nothing was returned at all
                "returned": covered,
                "id": q.id, "line_id": line.id, "code": q.code, "label": q.label, "qtype": q.qtype,
                "group": q.group, "help": q.help_text or "",
                "options": [{"id": o.id, "name": o.name, "kind": o.kind} for o in q.option_ids],
                "option_id": line.option_id.id or False,
                "option_ids": line.option_ids.ids,
                "value_number": line.value_number or False,
                "note": line.note or "",
            })
        return {
            "header": {
                "id": self.id, "name": self.name, "entity": self.entity_id.name,
                "kind": dict(PURCHASE_KINDS)[self.purchase_kind],
                "scenario": dict(SCENARIOS)[self.scenario],
                "state": self.state, "state_label": dict(self._fields["state"].selection)[self.state],
                "version": self.version, "progress": round(self.progress), "is_demo": self.is_demo,
                "outstanding": self._azm_outstanding(), "can_send": self._azm_can_send(),
                **self._azm_review_header(),
                "readonly": self.state != "draft",
            },
            # how many parts are waiting to be answered again across the whole
            # assessment: the filter is worth offering only when there are some, and
            # what came back may be under a stage the reader is not looking at
            "returns_open": len(returns),
            "stages": nav,
            "stage": {"id": stage.id, "code": stage.code, "name": stage.name,
                      "input": stage.input_desc, "output": stage.output_desc},
            "groups": [{"key": k, "title": v} for k, v in engine.GROUP_TITLES.items()],
            "questions": questions,
            "tabs": [{"key": k, "title": v} for k, v in engine.OUTPUT_TABS],
            "output": str(self._render(tab, stage if scope == "stage" else False)),
        }

    def workspace_answer(self, question_id, option_id=None, option_ids=None, value_number=None,
                         note=None, stage_id=None, tab="book", scope="stage"):
        self.ensure_one()
        if self.state != "draft":
            raise UserError("الإفادة مش في حالة مسودة.")
        line = self.answer_ids.filtered(lambda a: a.question_id.id == question_id)
        if not line:
            raise UserError("السؤال غير موجود في الإفادة.")
        vals = {}
        if option_id is not None:
            vals["option_id"] = option_id or False
        if option_ids is not None:
            vals["option_ids"] = [fields.Command.set(option_ids)]
        if value_number is not None:
            vals["value_number"] = value_number or 0.0
        if note is not None:
            vals["note"] = note
        line.write(vals)
        return self.workspace_data(stage_id=stage_id, tab=tab, scope=scope)

    def workspace_output(self, stage_id=None, tab="book", scope="stage"):
        self.ensure_one()
        stage = self.env["azm.stage"].browse(stage_id) if stage_id else False
        return str(self._render(tab, stage if scope == "stage" else False))

    # ---------------------------------------------------------------- actions
    def _azm_outstanding(self):
        self.ensure_one()
        return max(self.visible_count - self.answered_count, 0)

    def _azm_returned_outstanding(self, returns):
        self.ensure_one()
        # counted the way the whole assessment is counted: a visible question with a
        # value in it is answered
        lines = self.answer_ids.filtered(
            lambda line: line.is_visible and returns._covers(line))
        return len(lines) - len(lines.filtered("has_value"))

    def action_open_workspace(self, focus=None):
        """Open the workspace, on the stage that was asked for when one is named."""
        self.ensure_one()
        params = {"assessment_id": self.id}
        if focus and focus.get("level") == "stage":
            params["stage_id"] = focus["id"]
        elif focus and focus.get("level") == "question":
            params["stage_id"] = self.env["azm.question"].browse(focus["id"]).stage_id.id
        return {
            "type": "ir.actions.client", "tag": "azm_workspace", "name": self.name,
            "params": params,
        }

    def action_submit(self):
        """Send the cycle assessment to whoever reviews it."""
        for rec in self.filtered(lambda r: r.state == "draft"):
            rec.action_sync_findings()
            rec._submit_for_review("مراجعة إفادة دورة المشتريات")

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
            if rec.user_id == self.env.user and not self.env.is_superuser():
                raise UserError("مُعد الإفادة لا يعتمدها بنفسه (فصل المهام).")
            snapshot = "".join(str(rec._render(tab)) for tab in ("book", "policy", "procedure",
                                                                    "workflow", "authority", "risks"))
            answers = {a.question_id.code: a._engine_value() for a in rec.answer_ids if a.has_value}
            self.env["azm.assessment.version"].create({
                "assessment_id": rec.id, "version": rec.version,
                "answers_json": json.dumps(answers, ensure_ascii=False, indent=1),
                "snapshot_html": snapshot,
            })
            rec._workflow().write({"state": "approved", "approved_by_id": self.env.user.id,
                       "approved_date": fields.Datetime.now()})

    def action_new_version(self):
        self.ensure_one()
        if self.state != "approved":
            raise UserError("الإصدار الجديد يتعمل من إفادة معتمدة.")
        new = self.copy({"version": self.version + 1, "previous_id": self.id, "name": "جديد"})
        self._workflow().state = "archived"
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": new.id,
                "view_mode": "form"}

    def action_sync_findings(self):
        """Turn triggered rules into tracked findings; flag ones no longer triggered."""
        self.check_access("read")
        rules = self._rules()
        # findings are generated from the answers, not typed by the preparer:
        # create/refresh them as superuser, reviewers then work them by hand.
        Finding = self.env["azm.finding"].sudo()
        for rec in self:
            active_codes = set()
            for stage in rec._stages():
                sdict, qdicts, answers, _ = rec._stage_payload(stage)
                for item in engine.findings(sdict, qdicts, answers, rules):
                    active_codes.add(item["code"])
                    existing = rec.sudo().finding_ids.filtered(lambda f, c=item["code"]: f.code == c)
                    vals = {"fact": item["fact"], "risk": item["risk"], "control": item["control"],
                            "owner_hint": item["owner"], "stage_id": stage.id, "triggered": True}
                    if existing:
                        existing.write(vals)
                    else:
                        Finding.create({"assessment_id": rec.id, "code": item["code"], **vals})
            rec.sudo().finding_ids.filtered(lambda f: f.code not in active_codes).write({"triggered": False})
        return True

    def action_fill_demo(self):
        """Deterministic demo answers (a mix of good and weak practices)."""
        for rec in self:
            if rec.state != "draft":
                raise UserError("المثال يتعمل على مسودة فقط.")
            for _round in range(4):
                for stage in rec._stages():
                    sdict, qdicts, answers, by_q = rec._stage_payload(stage)
                    for qd in engine.visible_questions(sdict, qdicts, answers):
                        line = by_q.get(qd["id"])
                        if not line or line.has_value:
                            continue
                        normal = line.question_id.option_ids.filtered(lambda o: o.kind == "normal")
                        seed = zlib.crc32(f"{stage.code}/{qd['key']}".encode())
                        vals = {}
                        if qd["key"] == "presence":
                            # mostly applied, with a partial and a not-applicable stage for variety
                            pick = {"STK": 1, "ADV": 1}.get(stage.code, 0)
                            vals["option_id"] = normal[pick].id
                        elif qd["qtype"] == "number":
                            vals["value_number"] = 2 + seed % 5
                        elif qd["qtype"] == "multi" and normal:
                            vals["option_ids"] = [fields.Command.set(normal[: 1 + seed % min(3, len(normal))].ids)]
                        elif normal:
                            vals["option_id"] = normal[seed % len(normal)].id
                        if vals:
                            line.with_context(azm_no_visibility=True).write(vals)
                    rec._refresh_visibility()
            rec.is_demo = True
        return True

    def action_reset_answers(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError("المسح متاح للمسودة فقط.")
            rec.answer_ids.with_context(azm_no_visibility=True).write(
                {"option_id": False, "option_ids": [fields.Command.clear()], "value_number": 0.0})
            rec.is_demo = False
            rec._refresh_visibility()

    def action_view_findings(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": "سجل المخاطر", "res_model": "azm.finding",
                "view_mode": "list,form", "domain": [("assessment_id", "=", self.id)],
                "context": {"default_assessment_id": self.id}}

    def action_view_answers(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": f"إجابات {self.name}", "res_model": "azm.answer",
                "view_mode": "list", "domain": [("assessment_id", "=", self.id), ("is_visible", "=", True)],
                "context": {"search_default_by_stage": 1, "create": False}}

    def action_print_book(self):
        return self.env.ref("azm_operating_model.azm_assessment_report_book").report_action(self)

    def _report_sections(self):
        """Used by the PDF template."""
        self.ensure_one()
        return [(title, self._render(key)) for key, title in engine.OUTPUT_TABS if key != "coverage"]
