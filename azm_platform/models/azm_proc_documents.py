"""The procurement cycle's documents, filed exactly like the financial model's.

The same record carries them (azm.doc.publication), the same report draws them and
the same folder tree in Documents holds them, so a policy produced from the cycle and
a requirement sheet produced from the financial model are the same kind of object to
everyone who files, opens or searches for one:

    <Company>
    ├── 02 · السياسات والقواعد      ← PUR-REQ · السياسة …
    ├── 03 · الإجراءات ومسارات العمل ← PUR-REQ · الإجراء · رسم الدورة …
    ├── 04 · الصلاحيات والمسؤوليات  ← PUR-REQ · الصلاحيات …
    └── …

Three kinds are added: a sheet per question, one document per output of each stage
(policy, procedure, workflow, authority, controls, risks, gaps, system, KPIs — the
engine writes those bodies itself, so the document wraps its prose rather than
re-deriving it), and one summary of the whole cycle.

They are built the first time somebody opens one, not all at once: the cycle asks 396
questions of every entity, and pre-rendering that for every company would spend
hundreds of megabytes on PDFs nobody has asked to read.
"""
import hashlib
import json

from markupsafe import Markup

from odoo import _, api, fields, models

from odoo.addons.azm_operating_model.models import engine

# tab value -> (folder key, arabic, english, document code). The tab values are
# prefixed because the financial model already owns "workflow", "authority" and
# "gaps"; the suffix after pur_ is the engine's own name for the output.
PROC_OUTPUTS = {
    "pur_book": ("MAN", "الوضع الحالي", "Current state", "PR-BOK"),
    "pur_policy": ("POL", "السياسة", "Policy", "PR-POL"),
    "pur_procedure": ("SOP", "الإجراء", "Procedure", "PR-SOP"),
    "pur_workflow": ("SOP", "رسم الدورة", "Workflow map", "PR-FLW"),
    "pur_authority": ("AUTH", "الصلاحيات", "Authority & RACI", "PR-AUT"),
    "pur_gaps": ("GAP", "النواقص", "Gaps", "PR-GAP"),
    "pur_risks": ("GAP", "المخاطر", "Risks", "PR-RSK"),
    "pur_controls": ("CTL", "الضوابط المقترحة", "Proposed controls", "PR-CTL"),
    "pur_system": ("SRQ", "متطلبات النظام واختبارها", "System requirements", "PR-SRQ"),
    "pur_kpi": ("KPI", "مؤشرات المتابعة", "KPIs & KRIs", "PR-KPI"),
    "pur_coverage": ("RPT", "تغطية المخرجات", "Output coverage", "PR-COV"),
}
# shown in the order the engine lists its outputs, so the tree and the workspace agree
PROC_TAB_ORDER = [f"pur_{key}" for key, _title in engine.OUTPUT_TABS if f"pur_{key}" in PROC_OUTPUTS]
PROC_TABS = [(k, f"{PROC_OUTPUTS[k][1]} · {PROC_OUTPUTS[k][2]}") for k in PROC_TAB_ORDER]

# Which registry artifact type each output of the cycle is, and the stage it speaks from
PROC_ARTIFACTS = {
    "pur_book": ("MAN", "CS"),
    "pur_policy": ("POL", "CS"),
    "pur_procedure": ("PRO", "CS"),
    "pur_workflow": ("WFL", "CS"),
    "pur_authority": ("DOA", "CS"),
    "pur_gaps": ("GAP", "GR"),
    "pur_risks": ("RSK", "GR"),
    "pur_controls": ("CTL", "TD"),
    "pur_system": ("SRQ", "TD"),
    "pur_kpi": ("KPI", "CA"),
    "pur_coverage": ("RPT", "CS"),
}
PROC_KIND_ARTIFACTS = {
    "question": ("REQ", "CS"),
    "cycle": ("RPT", "CS"),
    "cycle_book": ("MAN", "CS"),
}

# Outputs a governance stage does not have: the engine says so itself — governance is
# not written as an operating procedure, and the cycle is drawn whole rather than per
# governance stage. So there is no procedure of PUR-GOV to number, offer or count.
GOVERNANCE_HAS_NO = {"pur_procedure", "pur_workflow"}

PROC_KINDS = [
    ("question", "سؤال · Question"),
    ("stage", "مخرج مرحلة · Stage output"),
    ("cycle", "ملخص الدورة · Cycle summary"),
    ("cycle_book", "كتاب الدورة · Cycle book"),
]
PROC_KEYS = {k for k, _label in PROC_KINDS}

# a question's answer said in the vocabulary every document already uses
PROC_STATE = {"answered": "full", "unsure": "unknown", "open": "open", "hidden": "na"}


def _engine_tab(tab):
    return tab[4:]


class AzmDocPublication(models.Model):
    _inherit = "azm.doc.publication"

    kind = fields.Selection(selection_add=PROC_KINDS, ondelete={k: "cascade" for k in PROC_KEYS})
    tab = fields.Selection(selection_add=PROC_TABS, ondelete={k: "cascade" for k in PROC_OUTPUTS})
    question_id = fields.Many2one("azm.question", "السؤال", ondelete="cascade", index=True)
    stage_id = fields.Many2one("azm.stage", "المرحلة", ondelete="cascade", index=True)
    stage_sequence = fields.Integer(related="stage_id.sequence", store=True)
    proc_assessment_id = fields.Many2one("azm.assessment", "إفادة المشتريات المصدر",
                                         ondelete="set null", readonly=True)

    # ---------------------------------------------------------------- naming
    @api.depends("kind", "question_id.code", "question_id.label", "stage_id.code", "stage_id.name", "tab")
    def _compute_name(self):
        mine = self.filtered(lambda p: p.kind in PROC_KEYS)
        super(AzmDocPublication, self - mine)._compute_name()
        for pub in mine:
            if pub.kind == "question":
                pub.name = f"{pub.question_id.code} · {pub.question_id.label}"
            elif pub.kind == "stage":
                pub.name = f"PUR-{pub.stage_id.code} · {PROC_OUTPUTS[pub.tab][1]}" if pub.tab else False
            elif pub.kind == "cycle":
                pub.name = "دورة المشتريات · ملخص الكيان"
            else:
                pub.name = "دورة المشتريات · الكتاب الكامل"

    # ---------------------------------------------------------------- lookup
    # ---------------------------------------------------------------- coding
    def _artifact(self):
        self.ensure_one()
        if self.kind not in PROC_KEYS:
            return super()._artifact()
        Artifact = self.env["azm.artifact"]
        if self.kind == "question":
            question = self.question_id
            return Artifact._of(f"azm.question,{question.id}", "PUR", "REQ", name=question.label)
        if self.kind == "stage":
            atype = PROC_ARTIFACTS[self.tab][0]
            return Artifact._of(f"azm.stage,{self.stage_id.id},{self.tab}", "PUR", atype,
                                name=f"PUR-{self.stage_id.code} · {PROC_OUTPUTS[self.tab][1]}")
        return Artifact._of(f"pur:{self.kind}", "PUR", PROC_KIND_ARTIFACTS[self.kind][0],
                            name=self.name)

    def _tree_ref(self):
        self.ensure_one()
        if self.kind not in PROC_KEYS:
            return super()._tree_ref()
        if self.kind == "question":
            return self.question_id.code or "PUR"
        if self.kind == "stage":
            return f"PUR-{self.stage_id.code}"
        return "PUR"

    def _lifecycle(self):
        self.ensure_one()
        if self.kind not in PROC_KEYS:
            return super()._lifecycle()
        if self.kind == "stage":
            return PROC_ARTIFACTS[self.tab][1]
        return PROC_KIND_ARTIFACTS[self.kind][1]

    @api.model
    def _book_kinds(self):
        return super()._book_kinds() | {"cycle_book"}

    def _book_parts(self):
        """The cycle bound in one volume: its summary, then every output of every stage."""
        self.ensure_one()
        if self.kind not in PROC_KEYS:
            return super()._book_parts()
        Pub = self.env["azm.doc.publication"].sudo()
        company, assessment = self.company_id, self._assessment()
        parts = [Pub._get(company, "cycle")]
        if assessment:
            for stage in self.env["azm.stage"].sudo().search([]):
                for tab in stage._azm_outputs():
                    parts.append(Pub._get(company, "stage", stage=stage, tab=tab))
        return parts

    def _book_cover(self, parts, source):
        self.ensure_one()
        if self.kind not in PROC_KEYS:
            return super()._book_cover(parts, source)
        company = self.company_id
        return {
            "doc_type": ("كتاب دورة المشتريات", "Procurement cycle book"),
            "code": "PUR-BOOK",
            "title": f"دورة المشتريات — {company.name}",
            "path": [("الدورة", "PUR", "دورة المشتريات"),
                     ("الكتاب", "PUR-BOOK", "الكتاب الكامل")],
            "glance": [
                ("الكيان", "Entity", company.name),
                ("المصدر", "Source", source),
                ("عدد المستندات", "Documents", str(len(parts))),
                ("تاريخ التجميع", "Bound on", fields.Date.to_string(fields.Date.today())),
            ],
            "summary_title": ("محتويات الكتاب", "Contents"),
            "summary_label": "المستند",
        }

    @api.model
    def _key(self, kind, requirement=None, module=None, tab=None, question=None, stage=None):
        if kind == "question":
            return f"qst:{question.id}"
        if kind == "stage":
            return f"stg:{stage.id}:{tab}"
        if kind in ("cycle", "cycle_book"):
            return kind
        return super()._key(kind, requirement=requirement, module=module, tab=tab)

    @api.model
    def _get(self, company, kind, requirement=None, module=None, tab=None, question=None, stage=None):
        if kind not in PROC_KEYS:
            return super()._get(company, kind, requirement=requirement, module=module, tab=tab)
        Pub = self.sudo()
        key = self._key(kind, tab=tab, question=question, stage=stage)
        pub = Pub.search([("company_id", "=", company.id), ("key", "=", key)], limit=1)
        if not pub:
            pub = Pub.create({
                "company_id": company.id, "kind": kind, "key": key, "build": "on_open",
                "question_id": question.id if question else False,
                "stage_id": (question.stage_id.id if question else stage.id if stage else False),
                "tab": tab or False,
            })
        return pub

    @api.model
    def _ensure_company(self, company):
        """Add the cycle's documents to the ones the company already has."""
        pubs = super()._ensure_company(company)
        Pub = self.sudo()
        have = set(pubs.mapped("key"))
        vals = []
        for question in self.env["azm.question"].sudo().search([]):
            if f"qst:{question.id}" not in have:
                vals.append({"company_id": company.id, "kind": "question", "build": "on_open",
                             "key": f"qst:{question.id}", "question_id": question.id,
                             "stage_id": question.stage_id.id})
        for stage in self.env["azm.stage"].sudo().search([]):
            for tab in stage._azm_outputs():
                if f"stg:{stage.id}:{tab}" not in have:
                    vals.append({"company_id": company.id, "kind": "stage", "build": "on_open",
                                 "key": f"stg:{stage.id}:{tab}", "stage_id": stage.id, "tab": tab})
        for kind in ("cycle", "cycle_book"):
            if kind not in have:
                vals.append({"company_id": company.id, "kind": kind, "key": kind, "build": "on_open"})
        Pub.create(vals)
        return Pub.search([("company_id", "=", company.id)])

    # ---------------------------------------------------------------- sources
    def _assessment(self):
        self.ensure_one()
        if self.kind not in PROC_KEYS:
            return super()._assessment()
        Assessment = self.env["azm.assessment"].sudo()
        entity = self._entity()
        if not entity:
            return Assessment
        return (Assessment.search([("entity_id", "=", entity.id), ("state", "=", "approved")],
                                  order="version desc, id desc", limit=1)
                or Assessment.search([("entity_id", "=", entity.id), ("state", "!=", "archived")],
                                     order="version desc, id desc", limit=1))

    def _lines(self, assessment):
        self.ensure_one()
        if self.kind not in PROC_KEYS:
            return super()._lines(assessment)
        lines = assessment.answer_ids
        if self.kind in ("question", "stage"):
            # a question sheet is read through its whole stage — the engine decides from
            # the siblings whether this question is asked at all, and the sentence it
            # prints can quote them — so the stage is what the document depends on
            stage = self.stage_id or self.question_id.stage_id
            return lines.filtered(lambda a: a.stage_id == stage)
        return lines

    def _current_stamp(self):
        """Fingerprint of what the document shows, so it is rebuilt when the answers move."""
        self.ensure_one()
        if self.kind not in PROC_KEYS or self.kind in self._book_kinds():
            return super()._current_stamp()
        assessment = self._assessment()
        lines = self._lines(assessment) if assessment else self.env["azm.answer"]
        data = {
            "assessment": [assessment.id, assessment.version, assessment.state, assessment.is_demo,
                           str(assessment.approved_date or "")] if assessment else None,
            "catalogue": [self.question_id.code, self.question_id.label, self.stage_id.code,
                          self.stage_id.name, self.tab],
            # gaps, risks, controls, system and KPIs are written from the risk rules as
            # well as the answers, so an edited rule has to age the output it feeds
            "rules": self._rules_stamp() if self.kind == "stage" else None,
            "coding": [self._artifact().code, self._lifecycle()],
            "lines": {line.code: [line.is_visible, line.is_known, line._engine_value(), line.note or ""]
                      for line in lines},
        }
        return hashlib.md5(json.dumps(data, sort_keys=True, ensure_ascii=False,
                                      default=str).encode()).hexdigest()

    def _rules_stamp(self):
        rules = self.env["azm.risk.rule"].sudo().search([])
        return [len(rules), str(max(rules.mapped("write_date")) if rules else "")]

    def _source_vals(self, assessment):
        self.ensure_one()
        if self.kind not in PROC_KEYS:
            return super()._source_vals(assessment)
        return {"proc_assessment_id": assessment.id}

    # ---------------------------------------------------------------- filing
    def _folder_key(self):
        self.ensure_one()
        if self.kind not in PROC_KEYS or self.kind in self._book_kinds():
            return super()._folder_key()
        if self.kind == "question":
            stage = self.question_id.stage_id
            return "PUR", (stage.code, f"PUR-{stage.code} · {stage.name}")
        if self.kind == "stage":
            return PROC_OUTPUTS[self.tab][0], None
        return "RPT", None

    def _is_empty(self, assessment):
        self.ensure_one()
        if self.kind not in PROC_KEYS or self.kind in self._book_kinds():
            return super()._is_empty(assessment)
        # a stage output with no assessment behind it has nothing to say yet; a question
        # sheet always has something — at the very least, what is being asked
        return self.kind == "stage" and not assessment

    # ---------------------------------------------------------------- payload
    def _proc_payload(self, stage):
        """Visible questions and answers of one stage, through the workspace's own engine."""
        assessment = self._assessment()
        if not assessment:
            return {}, set(), {}
        sdict, qdicts, answers, by_q = assessment._stage_payload(stage)
        visible = {q["id"] for q in engine.visible_questions(sdict, qdicts, answers)}
        return answers, visible, by_q

    def _proc_item(self, question, answers, visible, line):
        """One question, in the same shape a requirement takes in these documents."""
        stage = question.stage_id
        group = engine.GROUP_TITLES.get(question.group or "0", "")
        if visible is not None and question.id not in visible:
            state = "hidden"
        elif line and line.has_value:
            state = "answered" if line.is_known else "unsure"
        else:
            state = "open"
        value = answers.get(question.key)
        data = {
            "tree_ref": question.code,
            "title": question.label,
            "question": question.label,
            "ids": " · ".join(x for x in (question.code, question.key) if x),
            "owner": stage.default_owner or "",
            "profile": dict(question._fields["qtype"]._description_selection(self.env)).get(
                question.qtype, question.qtype or ""),
            "scope": group,
            "path": [
                ("الدورة", "PUR", "دورة المشتريات"),
                ("المرحلة", f"PUR-{stage.code}", stage.name),
                ("المجموعة", "", group),
                ("السؤال", question.code or question.key, question.label),
            ],
            "topic_code": f"PUR-{stage.code}",
            "topic": group,
            "answers": [], "tables": [], "steps": [], "pending": [],
            "impl": "", "rule": "", "target": "", "problems": "", "target_note": "", "na_reason": "",
            "missing": [],
            "status": self._status(PROC_STATE[state]),
        }
        if state == "hidden":
            data["na_reason"] = "لا يُسأل هذا السؤال عن هذا الكيان بناءً على إجاباته السابقة في نفس المرحلة."
            return data
        if state == "open":
            data["pending"] = [question.label]
        else:
            data["answers"].append({
                "label": "الإجابة",
                "value": engine.show(value) if value is not None else "—",
                "muted": not engine.known(value),
            })
            data["impl"] = engine.sentence(question._engine_dict(), answers)
        if line and line.note:
            data["answers"].append({"label": "ملاحظة المُجيب", "value": line.note, "muted": True})
        if question.option_ids:
            chosen = set((line.option_ids | line.option_id).ids) if line else set()
            data["tables"].append({
                "label": "الاختيارات المتاحة",
                "columns": ["الاختيار", "المختار"],
                "rows": [[o.name, "✓" if o.id in chosen else ""] for o in question.option_ids],
            })
        rules = self.env["azm.risk.rule"].sudo().search([("question_id", "=", question.id)])
        if rules:
            data["tables"].append({
                "label": "المخاطر المرتبطة بهذه الإجابة",
                "columns": ["تُفعَّل عند", "الممارسة", "الأثر المحتمل", "الضابط المقترح"],
                "rows": [[r.trigger_option_id.name, r.fact, r.risk, r.control] for r in rules],
            })
            fired = rules.filtered(lambda r: r.trigger_option_id.name == value
                                   or (isinstance(value, (list, tuple)) and r.trigger_option_id.name in value))
            if fired:
                data["problems"] = "، ".join(r.risk for r in fired)
        return data

    def _azm_payload_extra(self, assessment, source):
        self.ensure_one()
        if self.kind not in PROC_KEYS:
            return super()._azm_payload_extra(assessment, source)
        company = self.company_id

        if self.kind == "question":
            question = self.question_id
            answers, visible, by_q = self._proc_payload(question.stage_id)
            item = self._proc_item(question, answers, visible or None, by_q.get(question.id))
            return {
                "doc_type": ("ورقة سؤال", "Question sheet"),
                "code": item["tree_ref"],
                "title": question.label,
                "path": item["path"],
                "glance": [
                    ("الكيان", "Entity", company.name),
                    ("الحالة اليوم", "Status today", item["status"]["ar"]),
                    ("المرحلة", "Stage", f"PUR-{question.stage_id.code} · {question.stage_id.name}"),
                    ("المجموعة", "Group", item["scope"]),
                    ("المصدر", "Source", source),
                    ("الأكواد", "IDs", item["ids"]),
                ],
                "items": [item],
                "single": True,
            }

        if self.kind == "stage":
            stage = self.stage_id
            folder, arabic, english, code = PROC_OUTPUTS[self.tab]
            # the body prints the code the cover prints, not a shorthand of its own
            body = assessment._render(_engine_tab(self.tab), stage,
                                      doc_code=self._artifact().code) if assessment else ""
            return {
                "doc_type": (arabic, english),
                "code": f"{code}-{stage.code}",
                "title": f"{arabic} — {stage.name}",
                "path": [("الدورة", "PUR", "دورة المشتريات"),
                         ("المرحلة", f"PUR-{stage.code}", stage.name),
                         ("المخرج", code, arabic)],
                "glance": [
                    ("الكيان", "Entity", company.name),
                    ("المرحلة", "Stage", f"PUR-{stage.code} · {stage.name}"),
                    ("المدخل", "Input", stage.input_desc or "—"),
                    ("المخرج", "Output", stage.output_desc or "—"),
                    ("المالك المعتاد", "Usual owner", stage.default_owner or "—"),
                    ("المصدر", "Source", source),
                ],
                "html": Markup(body) if body else False,
                "single": False,
            }

        # the cycle at a glance: one row per stage
        rows = []
        if assessment:
            rules = assessment._rules()
            for stage in self.env["azm.stage"].sudo().search([]):
                sdict, qdicts, answers, _by_q = assessment._stage_payload(stage)
                stats = engine.stage_stats(sdict, qdicts, answers)
                rows.append({
                    "code": f"PUR-{stage.code}", "name": stage.name,
                    "applicable": stats["total"], "done": stats["answered"],
                    "full": stats["known"], "partial": stats["answered"] - stats["known"],
                    "unavailable": len(engine.findings(sdict, qdicts, answers, rules)),
                })
        return {
            "doc_type": ("ملخص الدورة", "Cycle summary"),
            "code": "PUR",
            "title": f"دورة المشتريات — {company.name}",
            "path": [("الدورة", "PUR", "دورة المشتريات")],
            "glance": [
                ("الكيان", "Entity", company.name),
                ("المصدر", "Source", source),
                ("الأسئلة المُجابة", "Answered",
                 f"{sum(r['done'] for r in rows)} من {sum(r['applicable'] for r in rows)}" if rows else "—"),
                ("المخاطر المرصودة", "Risks", str(sum(r["unavailable"] for r in rows)) if rows else "—"),
            ],
            "summary": rows,
            "summary_title": ("حالة مراحل الدورة", "Stages at a glance"),
            "summary_label": "المرحلة",
            "summary_columns": [("يُسأل", "applicable"), ("مُجاب", "done"),
                                ("مؤكد", "full"), ("غير مؤكد", "partial"), ("مخاطر", "unavailable")],
            "single": False,
        }


class AzmQuestion(models.Model):
    _inherit = "azm.question"

    azm_doc_ids = fields.One2many("azm.doc.publication", "question_id", string="المستندات")


class AzmStage(models.Model):
    _inherit = "azm.stage"

    azm_doc_ids = fields.One2many("azm.doc.publication", "stage_id", string="المستندات")

    def _azm_outputs(self):
        """The outputs this stage can ever have, whatever any entity answers."""
        self.ensure_one()
        if not self.question_ids:
            return []
        if self.is_governance:
            return [tab for tab in PROC_TAB_ORDER if tab not in GOVERNANCE_HAS_NO]
        return list(PROC_TAB_ORDER)
