"""رأي في السؤال نفسه، لا إجابة عنه.

المراجع القائم يراجع ما أُجيب. وهذا دور آخر: من يقرأ بنك الأسئلة ويقول رأيه في
السؤال — أواضح هو، أمكرر، أينقصه خيار، أيحتاج إعادة صياغة. فالفرق بين الاثنين
هو الفرق بين «هذه الإجابة ناقصة» و«هذا السؤال لا يُسأل هكذا».

وملاحظة لا تصل أحدًا لا تُراجَع، فلها حالتان: مسودة عند صاحبها، ومُرسَلة إلى
مدير النموذج. وما أُرسل لا يُعدَّل — وإلا تغيّر تحت عين من يقرؤه.

السؤال يعيش في نموذجين لا واحد، فالملاحظة تشير إلى أحدهما لا إليهما، على نهج
azm.assignment نفسه.

والدور يقرأ بنك الأسئلة ولا يُجيب: صلاحياته قراءة على الكتالوج وحده. فلا يرى
إفادة كيان ولا إجاباته — ورأيه في صياغة سؤال لا يحتاج أن يرى ما أجاب به أحد.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

VERDICTS = [
    ("clear", "واضح ومناسب"),
    ("wording", "يحتاج إعادة صياغة"),
    ("duplicate", "مكرر أو يتداخل مع غيره"),
    ("options", "ينقصه خيار أو خياراته غير دقيقة"),
    ("scope", "غير منطبق على نشاطنا"),
    ("other", "أخرى"),
]
# الآراء التي تعني أن على أحد أن ينظر، تمييزًا لها عن «واضح ومناسب»
NEEDS_WORK = ("wording", "duplicate", "options", "scope", "other")

# نصّ الضغطة الواحدة: ما يصل المدير حين يقول المراجع إن السؤال لا شيء عليه
APPROVED = "سليم كما هو — لا يحتاج تغييرًا."


class AzmQuestionComment(models.Model):
    _name = "azm.question.comment"
    _description = "ملاحظة على سؤال"
    _order = "create_date desc, id desc"
    _rec_name = "question_code"

    # أحد النموذجين لا كلاهما — انظر _check_one_question
    fin_question_id = fields.Many2one("azm.fin.question", "سؤال مالي",
                                      ondelete="cascade", index=True)
    proc_question_id = fields.Many2one("azm.question", "سؤال مشتريات",
                                       ondelete="cascade", index=True)

    question_code = fields.Char("كود السؤال", compute="_compute_question", store=True, index=True)
    question_label = fields.Char("نص السؤال", compute="_compute_question", store=True)
    node = fields.Char("الموضع", compute="_compute_question", store=True,
                       help="الموديول أو المرحلة التي ينتمي إليها السؤال.")
    model_key = fields.Selection([("financial", "النموذج المالي الموحد"),
                                  ("procurement", "دورة المشتريات")],
                                 "النموذج", compute="_compute_question", store=True, index=True)

    verdict = fields.Selection(VERDICTS, "الرأي", required=True, default="wording")
    comment = fields.Text("الملاحظة", required=True)
    needs_work = fields.Boolean("يحتاج نظرًا", compute="_compute_needs_work", store=True)

    state = fields.Selection([("draft", "مسودة"), ("sent", "مُرسَلة")],
                             "الحالة", default="draft", required=True, readonly=True)
    sent_on = fields.Datetime("تاريخ الإرسال", readonly=True)
    user_id = fields.Many2one("res.users", "صاحب الملاحظة", required=True, readonly=True,
                              default=lambda self: self.env.user, index=True)

    _one_question = models.Constraint(
        "CHECK((fin_question_id IS NULL) <> (proc_question_id IS NULL))",
        "الملاحظة تخص سؤالًا واحدًا: ماليًا أو من المشتريات.")
    # رأي واحد لكل مراجع في كل سؤال؛ وتعديله أولى من تكديس آراء متناقضة له
    _one_per_reviewer = models.Constraint(
        "UNIQUE(fin_question_id, proc_question_id, user_id)",
        "لك ملاحظة على هذا السؤال بالفعل؛ عدّلها بدل إضافة أخرى.")

    @api.depends("fin_question_id", "proc_question_id")
    def _compute_question(self):
        for note in self:
            fin, proc = note.fin_question_id, note.proc_question_id
            if fin:
                note.question_code = fin.code or fin.key or ""
                note.question_label = fin.label or ""
                note.node = f"FIN.{fin.module_id.code}" if fin.module_id else "FIN"
                note.model_key = "financial"
            elif proc:
                note.question_code = proc.code or proc.key or ""
                note.question_label = proc.label or ""
                note.node = f"PUR-{proc.stage_id.code}" if proc.stage_id else "PUR"
                note.model_key = "procurement"
            else:
                note.question_code = note.question_label = note.node = False
                note.model_key = False

    @api.depends("verdict")
    def _compute_needs_work(self):
        for note in self:
            note.needs_work = note.verdict in NEEDS_WORK

    # ------------------------------------------------------------------ الكتابة
    def write(self, vals):
        """ما أُرسل لا يُعدَّل — إلا أن يُعيده مدير النموذج إلى صاحبه."""
        moving_back = vals.get("state") == "draft"
        if not moving_back and not self.env.su:
            frozen = self.filtered(lambda n: n.state == "sent")
            if frozen and set(vals) - {"state", "sent_on"}:
                raise UserError(_(
                    "الملاحظة أُرسلت، فلا تُعدَّل. اطلب من مدير النموذج إعادتها إن لزم."))
        return super().write(vals)

    def action_send(self):
        """إرسال الملاحظة إلى مدير النموذج."""
        drafts = self.filtered(lambda n: n.state == "draft")
        if not drafts:
            raise UserError(_("لا توجد ملاحظات مسودة لإرسالها."))
        drafts.write({"state": "sent", "sent_on": fields.Datetime.now()})
        return True

    def action_back_to_draft(self):
        if not self.env.user.has_group("azm_operating_model.azm_group_manager"):
            raise UserError(_("إعادة الملاحظة إلى صاحبها لمدير النموذج."))
        self.filtered(lambda n: n.state == "sent").write({"state": "draft", "sent_on": False})
        return True

    # ------------------------------------------------------------------ الواجهة
    @api.model
    def _field_for(self, model_key):
        if model_key == "financial":
            return "fin_question_id", "azm.fin.question"
        if model_key == "procurement":
            return "proc_question_id", "azm.question"
        raise UserError(_("نموذج غير معروف: %s", model_key))

    @api.model
    def notes_for(self, model_key, question_ids):
        """ملاحظاتي على هذه الأسئلة — ``{question id: {...}}``.

        ملاحظاتي وحدها: رأي مراجع في سؤال ليس شيئًا يراه زملاؤه قبل أن يُرسَل.
        """
        field, _model = self._field_for(model_key)
        wanted = [int(i) for i in question_ids or []]
        if not wanted:
            return {}
        found = self.search([(field, "in", wanted), ("user_id", "=", self.env.uid)])
        return {note[field].id: {
            "id": note.id, "verdict": note.verdict, "comment": note.comment or "",
            "state": note.state, "needs_work": note.needs_work,
        } for note in found}

    @api.model
    def save_note(self, model_key, question_id, verdict, comment):
        """يكتب رأيي في سؤال أو يعدّله. وملاحظة بلا نص ليست ملاحظة، فتُحذف."""
        field, model = self._field_for(model_key)
        question = self.env[model].browse(int(question_id)).exists()
        if not question:
            raise UserError(_("السؤال غير موجود."))
        if verdict not in dict(VERDICTS):
            raise UserError(_("رأي غير معروف."))
        mine = self.search([(field, "=", question.id), ("user_id", "=", self.env.uid)], limit=1)
        text = (comment or "").strip()
        if not text:
            mine.unlink()
            return {"deleted": True, "drafts": self._my_draft_count()}
        if mine:
            mine.write({"verdict": verdict, "comment": text})
        else:
            mine = self.create({field: question.id, "verdict": verdict, "comment": text})
        return {"id": mine.id, "state": mine.state, "needs_work": mine.needs_work,
                "drafts": self._my_draft_count()}

    @api.model
    def _my_draft_count(self):
        """كم رأيًا كتبتُه ولم أرسله بعد.

        يعود مع كل حفظ لأن الصفحة تعرضه حيث يُكتب: من كتب ملاحظاته داخل موديول
        ولم يعد إلى الصفحة الأولى لم يكن يرى أن عليه إرسالها، فكانت تبقى عنده
        وهو يحسبها وصلت.
        """
        return self.search_count([("user_id", "=", self.env.uid),
                                  ("state", "=", "draft")])

    @api.model
    def approve_question(self, model_key, question_id):
        """زرٌّ واحد: هذا السؤال سليم ولا يحتاج تغييرًا.

        أكثر ما يُقال عن سؤال أنه لا شيء عليه، وكتابة ذلك ألف مرة ليست مراجعة.
        فتُكتب الضغطة رأيًا كاملًا بنصّه، ليصل المدير سطرٌ يُقرأ لا خانة فارغة.

        وضغطة ثانية تتراجع عنها ما دامت لم تُرسَل — فمن ضغط سهوًا لا يحتاج إلى
        من يحذف له. أما إن كان قد كتب رأيًا قبلها فنصّه يبقى: الزر يغيّر الحكم،
        ولا يمحو ما كتبه صاحبه.
        """
        self._review_allowed()
        field, model = self._field_for(model_key)
        question = self.env[model].browse(int(question_id)).exists()
        if not question:
            raise UserError(_("السؤال غير موجود."))
        mine = self.search(
            [(field, "=", question.id), ("user_id", "=", self.env.uid)], limit=1)
        if mine.state == "sent":
            raise UserError(_("ما أُرسل إلى مدير النموذج لا يُعدَّل."))
        if not mine:
            mine = self.create({field: question.id, "verdict": "clear",
                                "comment": APPROVED})
        elif mine.verdict == "clear":
            mine.unlink()
            return {"deleted": True, "drafts": self._my_draft_count()}
        else:
            # حكمه يتغيّر، ونصّه له
            mine.write({"verdict": "clear"})
        return {"id": mine.id, "state": mine.state, "verdict": mine.verdict,
                "comment": mine.comment, "needs_work": mine.needs_work,
                "drafts": self._my_draft_count()}

    @api.model
    def send_my_notes(self):
        """إرسال كل مسوداتي دفعةً إلى مدير النموذج."""
        drafts = self.search([("user_id", "=", self.env.uid), ("state", "=", "draft")])
        if not drafts:
            raise UserError(_("لا توجد ملاحظات مسودة لإرسالها."))
        drafts.action_send()
        return {"sent": len(drafts)}

    # ------------------------------------------------------------------ المراجعة
    @api.model
    def _review_allowed(self):
        if not self.env.user.has_group("azm_operating_model.azm_group_question_reviewer"):
            raise UserError(_("مراجعة بنك الأسئلة لمن يحمل دورها."))

    @api.model
    def review_models(self):
        """صفحة المراجع الأولى: النموذجان وما قطعه فيهما.

        تقابل «مهامي» عند من يُجيب — لكن ما يُعدّ هنا أسئلة لا إجابات، وما يُنجَز
        رأيٌ لا إفادة.
        """
        self._review_allowed()
        mine = self.search([("user_id", "=", self.env.uid)])
        rows = []
        # الاسم والأيقونة واللون كما في مساحة الإجابة، فالنموذج واحد وإن اختلف
        # ما يُفعل به: من رأى «دورة المشتريات» زرقاء هناك يراها زرقاء هنا.
        for key, model, label, en, icon, tone in (
                ("financial", "azm.fin.question", "النموذج المالي الموحد",
                 "Unified financial model", "payments", "green"),
                ("procurement", "azm.question", "دورة المشتريات",
                 "Procurement cycle", "shopping_cart", "blue")):
            total = self.env[model].sudo().search_count([])
            ours = mine.filtered(lambda n, k=key: n.model_key == k)
            rows.append({
                "key": key, "name": label, "en": en, "icon": icon, "tone": tone,
                "total": total,
                "reviewed": len(ours),
                "drafts": len(ours.filtered(lambda n: n.state == "draft")),
                "sent": len(ours.filtered(lambda n: n.state == "sent")),
                "needs_work": len(ours.filtered("needs_work")),
                "progress": round(100.0 * len(ours) / total) if total else None,
            })
        return {"available": True, "models": rows,
                "verdicts": [{"key": k, "name": n} for k, n in VERDICTS],
                "user": self.env.user.name}

    @api.model
    def review_nodes(self, model_key):
        """أقسام النموذج: موديولاته أو مراحله، وما فيها من أسئلة وآراء."""
        self._review_allowed()
        mine = self.search([("user_id", "=", self.env.uid),
                            ("model_key", "=", model_key)])
        by_node = {}
        for note in mine:
            by_node[note.node] = by_node.get(note.node, 0) + 1
        nodes = []
        if model_key == "financial":
            for module in self.env["azm.fin.module"].sudo().search([], order="sequence, id"):
                count = self.env["azm.fin.question"].sudo().search_count(
                    [("module_id", "=", module.id)])
                code = f"FIN.{module.code}"
                nodes.append({"code": module.code, "name": module.name,
                              "questions": count, "reviewed": by_node.get(code, 0)})
        else:
            for stage in self.env["azm.stage"].sudo().search([], order="sequence, id"):
                count = self.env["azm.question"].sudo().search_count(
                    [("stage_id", "=", stage.id)])
                nodes.append({"code": stage.code, "name": stage.name,
                              "questions": count, "reviewed": by_node.get(f"PUR-{stage.code}", 0)})
        return [n for n in nodes if n["questions"]]

    @api.model
    def review_questions(self, model_key, node_code):
        """أسئلة قسم واحد، مجموعةً كما تُقرأ، ومع كل سؤال رأيي فيه."""
        self._review_allowed()
        groups = {}
        if model_key == "financial":
            module = self.env["azm.fin.module"].sudo().search(
                [("code", "=", node_code)], limit=1)
            questions = self.env["azm.fin.question"].sudo().search(
                [("module_id", "=", module.id)],
                order="requirement_id, sequence, id")
            title = module.name
            def group_of(q):
                req = q.requirement_id
                return (req.code or "", f"{req.code} · {req.title}" if req else "")
        else:
            stage = self.env["azm.stage"].sudo().search([("code", "=", node_code)], limit=1)
            questions = self.env["azm.question"].sudo().search(
                [("stage_id", "=", stage.id)], order="sequence, id")
            title = stage.name
            groups_named = dict(self.env["azm.question"]._fields["group"].selection)
            def group_of(q):
                return (q.group or "", groups_named.get(q.group, "أسئلة المرحلة"))

        notes = self.notes_for(model_key, questions.ids)
        for q in questions:
            key, label = group_of(q)
            bucket = groups.setdefault(key, {"key": key, "name": label, "questions": []})
            note = notes.get(q.id)
            bucket["questions"].append({
                "id": q.id, "code": q.code or q.key or "", "key": q.key or "",
                "label": q.label or "",
                "hint": (q.hint if model_key == "financial" else q.help_text) or "",
                "qtype": q.qtype or "",
                # خيارات السؤالين معًا: كانت خيارات المشتريات لا تُعرض للمراجع
                # أصلًا، ومن لا يرى الخيارات لا يسعه أن يقول إن أحدها ناقص.
                "options": q.option_ids.mapped("name"),
                "note": note,
            })
        return {"title": title, "node": node_code, "model": model_key,
                "groups": list(groups.values()),
                "count": len(questions),
                "reviewed": len([q for q in questions if notes.get(q.id)])}

    # ------------------------------------------------------------------ الإحصاء
    _STATS_LIMIT = 400

    @api.model
    def question_detail(self, model_key, code):
        """سؤال واحد كما هو في البنك، وما قيل فيه — لمدير النموذج.

        الصفحة تعرض السطر؛ وهذا ما تحته: السؤال بنصّه كاملًا، وموضعه من الشجرة،
        وخياراته كما تُعرض على المجيب، وشرط ظهوره إن كان مشروطًا، ثم كل رأي قيل
        فيه. فمن قرأ «ينقصه خيار» لا يسعه الحكم حتى يرى الخيارات التي عندها قيل.
        """
        if not self.env.user.has_group("azm_operating_model.azm_group_manager"):
            raise UserError(_("قراءة السؤال وملاحظاته لمدير النموذج."))
        field, model = self._field_for(model_key)
        questions = self.env[model].sudo()
        question = questions.search([("code", "=", code)], limit=1) \
            or questions.search([("key", "=", code)], limit=1)
        if not question:
            raise UserError(_("لم يُعثر على السؤال %s.", code))

        kinds = dict(question.option_ids._fields["kind"].selection or [])
        qtypes = dict(questions._fields["qtype"].selection or [])
        if model_key == "financial":
            req = question.requirement_id
            place = [p for p in (question.module_id.name, question.topic_id.name,
                                 f"{req.code} · {req.title}" if req else "") if p]
            node = f"FIN.{question.module_id.code}" if question.module_id else "FIN"
            hint, condition = question.hint, question.condition_text
        else:
            groups = dict(questions._fields["group"].selection or [])
            place = [p for p in (question.stage_id.name,
                                 groups.get(question.group, "")) if p]
            node = f"PUR-{question.stage_id.code}" if question.stage_id else "PUR"
            hint, condition = question.help_text, question.condition

        verdicts = dict(VERDICTS)
        notes = self.sudo().search(
            [(field, "=", question.id), ("state", "=", "sent")], order="sent_on, id")
        return {
            "model": model_key, "code": question.code or question.key or "",
            "key": question.key or "", "node": node, "place": place,
            "label": question.label or "", "hint": hint or "",
            "qtype": qtypes.get(question.qtype, question.qtype or ""),
            "condition": condition or "",
            "options": [{"name": o.name,
                         "kind": kinds.get(o.kind, "") if o.kind else ""}
                        for o in question.option_ids],
            "notes": [{"verdict": verdicts.get(n.verdict, n.verdict),
                       "needs_work": n.needs_work, "comment": n.comment or "",
                       "by": n.user_id.name, "sent_on": str(n.sent_on or "")}
                      for n in notes],
        }

    @api.model
    def comment_stats(self):
        """ما وصل مدير النموذج: كم سؤالًا عليه ملاحظة، وأين، وبأي رأي.

        يُحسب على المُرسَل وحده — فالمسودة رأي لم يُقَل بعد. والعدّ بالأسئلة لا
        بالملاحظات: سؤال علّق عليه ثلاثة مراجعين سؤال واحد عليه ملاحظة.
        """
        if not self.env.user.has_group("azm_operating_model.azm_group_manager"):
            raise UserError(_("الإحصاء لمدير النموذج."))
        sent = self.sudo().search([("state", "=", "sent")])
        verdicts = dict(VERDICTS)
        by_verdict, by_node, questions = {}, {}, set()
        for note in sent:
            key = (note.model_key, note.question_code)
            questions.add(key)
            by_verdict[note.verdict] = by_verdict.get(note.verdict, 0) + 1
            by_node[note.node or "—"] = by_node.get(note.node or "—", 0) + 1
        totals = {
            "financial": self.env["azm.fin.question"].sudo().search_count([]),
            "procurement": self.env["azm.question"].sudo().search_count([]),
        }
        commented = {
            "financial": len({c for m, c in questions if m == "financial"}),
            "procurement": len({c for m, c in questions if m == "procurement"}),
        }
        # السؤال سطرًا واحدًا وتحته آراؤه. المدير يقرأ سؤالًا اختُلف عليه، لا
        # ملاحظتين متباعدتين في قائمة لا يظهر فيها أنهما عن سؤال واحد.
        by_question = {}
        for note in sent:
            entry = by_question.setdefault((note.model_key, note.question_code), {
                "code": note.question_code, "node": note.node,
                "model": note.model_key, "label": (note.question_label or "")[:160],
                "needs_work": False, "notes": [],
            })
            entry["needs_work"] = entry["needs_work"] or note.needs_work
            entry["notes"].append({
                "verdict": note.verdict,
                "verdict_name": verdicts.get(note.verdict, note.verdict),
                "needs_work": note.needs_work,
                "comment": note.comment or "",
                "by": note.user_id.name,
                "sent_on": str(note.sent_on or ""),
            })
        # ما يحتاج نظرًا أولًا: الصفحة تُفتح على ما يُعمل به، لا على ما طُمئن إليه
        listed = sorted(by_question.values(),
                        key=lambda r: (not r["needs_work"], r["model"],
                                       r["node"] or "", r["code"] or ""))
        return {
            "notes": len(sent),
            "reviewers": len(sent.mapped("user_id")),
            "questions_commented": len(questions),
            "questions_total": totals["financial"] + totals["procurement"],
            "needs_work": len(sent.filtered("needs_work")),
            "by_model": [{"key": k, "commented": commented[k], "total": totals[k]}
                         for k in ("financial", "procurement")],
            "by_verdict": sorted(
                ({"key": k, "name": verdicts.get(k, k), "count": n}
                 for k, n in by_verdict.items()), key=lambda r: -r["count"]),
            "by_node": sorted(
                ({"node": k, "count": n} for k, n in by_node.items()),
                key=lambda r: -r["count"])[:20],
            # الكود مع ملاحظته، وهو ما طُلب أن يراه المدير. يُقطع عند حدٍّ تبقى
            # الصفحة عنده قابلة للقراءة، وتُقال البقية بعددها لا بالصمت عنها:
            # القائمة الكاملة بجانبها لمن أراد الكل.
            "questions": listed[:self._STATS_LIMIT],
            "questions_listed": len(listed),
            "questions_shown": min(len(listed), self._STATS_LIMIT),
        }


class AzmReviewableQuestion(models.AbstractModel):
    """سؤال يُكتب رأيٌ فيه من حيث يُقرأ.

    الرأي يُكتب في قائمة الأسئلة نفسها، لا في شاشة منفصلة يُنتقى فيها السؤال من
    قائمة فيها ألف وخمسمئة — فمن يقرأ السؤال هو من له رأي فيه، وأن يُغادر مكانه
    ليسجّله يعني ألّا يسجّله.

    والحقول محسوبة غير مخزّنة لأنها تخص قارئها: «رأيي» لا يُخزَّن على السؤال،
    وإنما يُقرأ من ملاحظة صاحبها.
    """
    _name = "azm.reviewable.question"
    _description = "سؤال قابل للمراجعة"

    # يُحدَّد في كل نموذج: اسم الحقل الذي تشير به الملاحظة إليه
    _azm_comment_field = None

    # للعرض فقط. الكتابة عبر action_write_note، لأن حفظ حقل على السؤال يستلزم
    # حق الكتابة عليه — ومراجع بنك الأسئلة يقرأ البنك ولا يعدّله. الرأي في
    # السؤال شيء، وتعديل السؤال شيء آخر، والحد بينهما هو الحد الذي أُريد.
    my_verdict = fields.Selection(VERDICTS, "رأيي", compute="_compute_my_note")
    my_comment = fields.Text("ملاحظتي", compute="_compute_my_note")
    my_note_state = fields.Selection([("draft", "مسودة"), ("sent", "مُرسَلة")],
                                     "حالة ملاحظتي", compute="_compute_my_note")
    comment_count = fields.Integer("ملاحظات مُرسَلة", compute="_compute_comment_count")

    def _azm_my_notes(self):
        return self.env["azm.question.comment"].search([
            (self._azm_comment_field, "in", self.ids),
            ("user_id", "=", self.env.uid),
        ])

    @api.depends_context("uid")
    def _compute_my_note(self):
        mine = {n[self._azm_comment_field].id: n for n in self._azm_my_notes()}
        for question in self:
            note = mine.get(question.id)
            question.my_verdict = note.verdict if note else False
            question.my_comment = note.comment if note else False
            question.my_note_state = note.state if note else False

    def action_write_note(self):
        """يفتح رأيي في هذا السؤال لأكتبه أو أعدّله."""
        self.ensure_one()
        Comment = self.env["azm.question.comment"]
        mine = Comment.search([(self._azm_comment_field, "=", self.id),
                               ("user_id", "=", self.env.uid)], limit=1)
        return {
            "type": "ir.actions.act_window",
            "name": _("رأيي في هذا السؤال"),
            "res_model": "azm.question.comment",
            "view_mode": "form",
            "target": "new",
            "res_id": mine.id or False,
            "context": {f"default_{self._azm_comment_field}": self.id,
                        "default_verdict": "wording"},
        }

    def _compute_comment_count(self):
        """كم مراجعًا علّق على هذا السؤال — المُرسَل وحده، فالمسودة لم تُقَل بعد."""
        counts = {}
        if self.ids:
            rows = self.env["azm.question.comment"].sudo()._read_group(
                [(self._azm_comment_field, "in", self.ids), ("state", "=", "sent")],
                [self._azm_comment_field], ["__count"])
            counts = {q.id: n for q, n in rows}
        for question in self:
            question.comment_count = counts.get(question.id, 0)
