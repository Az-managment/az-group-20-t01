"""Operating-model documents filed in each company's Documents workspace.

Every requirement of the unified financial model (FIN.PUR.03 …) gets a PDF
per company, built from that company's own answers, and every module gets its
current-state outputs (policies, SOPs, authority, KPIs …). The PDFs live in the
Documents app, in one folder tree per company:

    <Company>
    ├── 01 · النموذج المالي الموحد · Unified Financial Model
    │   ├── FIN.GOV · …        ← one PDF per requirement (FIN.GOV.01 …)
    │   └── FIN.PUR · …
    ├── 02 · السياسات والقواعد · Policies & Rules      ← FIN.<module> outputs
    ├── 03 · الإجراءات ومسارات العمل · SOPs & Workflows
    └── …

Nothing is typed twice: a document is re-rendered from the answers whenever
they change, and the company is the only thing that decides who can see it
(the Documents company rules), so one entity never sees another's files.
"""
import hashlib
import json
import logging

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.azm_operating_model.models import fin_engine
from odoo.addons.azm_operating_model.models.azm_fin_catalogue import PROFILES, SCOPES

_logger = logging.getLogger(__name__)

# key -> (order, arabic, english, internal users may add their own files)
FOLDERS = {
    "FIN": (1, "النموذج المالي الموحد", "Unified Financial Model", False),
    "POL": (2, "السياسات والقواعد", "Policies & Rules", True),
    "SOP": (3, "الإجراءات ومسارات العمل", "SOPs & Workflows", True),
    "AUTH": (4, "الصلاحيات والمسؤوليات", "Authority (DOA) & RACI", True),
    "CTL": (5, "الضوابط", "Controls", True),
    "FRM": (6, "النماذج", "Forms", True),
    "KPI": (7, "التقارير والمؤشرات", "Reports, KPIs & KRIs", True),
    "SRQ": (8, "التكامل ومتطلبات النظام", "Integration & System Requirements", True),
    "GAP": (9, "الفجوات والنموذج المستهدف", "Gaps & Target Design", False),
    "RPT": (10, "تقارير الإدارة", "Management Reports", False),
    "MAN": (11, "الأدلة التشغيلية", "Manuals", True),
}

# module output tab -> (folder, arabic, english, document code)
MODULE_OUTPUTS = {
    "rules": ("POL", "السياسات والقواعد", "Policies & Rules", "CS-POL"),
    "workflow": ("SOP", "الإجراءات ومسارات العمل", "Procedures & Workflows", "CS-SOP"),
    "authority": ("AUTH", "الصلاحيات والمسؤوليات", "Authority & Responsibilities", "CS-AUTH"),
    "reports": ("KPI", "التقارير والمؤشرات", "Reports & KPIs", "CS-RPT"),
    "integration": ("SRQ", "التكامل ومتطلبات النظام", "Integration & System Requirements", "CS-INT"),
    "gaps": ("GAP", "الفجوات", "Gaps", "CS-GAP"),
    "future": ("GAP", "التوجه المستهدف", "Target Direction", "CS-TOM"),
}

# status -> (arabic, english, css)
STATUS = {
    "full": ("مطبّق بالكامل", "Fully in place", "ok"),
    "partial": ("مطبّق جزئيًا", "Partly in place", "warn"),
    "unavailable": ("غير مطبّق", "Not in place", "bad"),
    "unknown": ("غير معروف", "Unknown", "muted"),
    "na": ("لا ينطبق", "Not applicable", "muted"),
    "open": ("لم تتم الإجابة بعد", "Not answered yet", "muted"),
}

KINDS = [("requirement", "متطلب · Requirement"), ("module", "مخرج موديول · Module output"),
         ("summary", "ملخص الكيان · Entity summary")]
TABS = [(k, f"{v[1]} · {v[2]}") for k, v in MODULE_OUTPUTS.items()]
BATCH = 20


def _folder_name(key):
    order, arabic, english, _upload = FOLDERS[key]
    return f"{order:02d} · {arabic} · {english}"


class AzmDocFolder(models.Model):
    """Which Documents folder plays which role for a company.

    Kept apart from the folders themselves so that a folder renamed or moved
    by a user is still found, and never duplicated by the next publication."""
    _name = "azm.doc.folder"
    _description = "AZM document folder"

    company_id = fields.Many2one("res.company", required=True, ondelete="cascade", index=True)
    path = fields.Char(required=True, help="ROOT, a folder key (POL, SOP …) or FIN/<module code>.")
    folder_id = fields.Many2one("documents.document", ondelete="set null")

    _path_uniq = models.Constraint("UNIQUE(company_id, path)", "This folder is already registered for the company.")

    @api.model
    def _folder(self, company, key="ROOT", module=None):
        """The folder of ``company`` for ``key`` (and ``module``), created on first use."""
        company = company.sudo()
        root = self._ensure(company, "ROOT", company.name, False, upload=False)
        if key == "ROOT":
            return root
        folder = self._ensure(company, key, _folder_name(key), root, upload=FOLDERS[key][3])
        if module:
            folder = self._ensure(company, f"{key}/{module.code}", f"FIN.{module.code} · {module.name}", folder,
                                  upload=False)
        return folder

    @api.model
    def _ensure(self, company, path, name, parent, upload):
        Registry = self.sudo()
        Document = self.env["documents.document"].sudo().with_company(company)
        entry = Registry.search([("company_id", "=", company.id), ("path", "=", path)], limit=1)
        folder = entry.folder_id
        if folder and not folder.active:
            folder.active = True
        if not folder:
            # adopt a folder made before (the dev hook files samples in a folder named after the company)
            folder = Document.search([
                ("type", "=", "folder"), ("name", "=", name), ("company_id", "=", company.id),
                ("folder_id", "=", parent.id if parent else False),
            ], limit=1)
            if not folder:
                folder = Document.create({
                    "name": name,
                    "type": "folder",
                    "company_id": company.id,
                    "folder_id": parent.id if parent else False,
                    # Documents default to access_internal 'none', which hides them from every internal
                    # user; the company rules still keep each entity to its own folders.
                    "access_internal": "edit" if upload else "view",
                })
            if entry:
                entry.folder_id = folder
            else:
                Registry.create({"company_id": company.id, "path": path, "folder_id": folder.id})
        return folder

    @api.model
    def _ensure_all(self, companies=None):
        companies = companies or self.env["res.company"].sudo().search([])
        modules = self.env["azm.fin.module"].sudo().search([])
        for company in companies:
            for key in FOLDERS:
                self._folder(company, key)
            for module in modules:
                self._folder(company, "FIN", module)
        return True


class AzmDocPublication(models.Model):
    """One generated document of one company, and whether it is up to date."""
    _name = "azm.doc.publication"
    _description = "AZM published document"
    _order = "company_id, kind, module_sequence, tree_ref, tab, id"
    _rec_name = "name"

    name = fields.Char("المستند", compute="_compute_name", store=True)
    key = fields.Char(required=True, index=True)
    company_id = fields.Many2one("res.company", "الكيان", required=True, ondelete="cascade", index=True)
    kind = fields.Selection(KINDS, "النوع", required=True)
    requirement_id = fields.Many2one("azm.fin.requirement", "المتطلب", ondelete="cascade", index=True)
    tree_ref = fields.Char(related="requirement_id.tree_ref", store=True, string="مرجع الشجرة")
    module_id = fields.Many2one("azm.fin.module", "الموديول", ondelete="cascade", index=True)
    module_sequence = fields.Integer(related="module_id.sequence", store=True)
    tab = fields.Selection(TABS, "المخرج")
    document_id = fields.Many2one("documents.document", "المستند في Documents", ondelete="set null", readonly=True)
    folder_id = fields.Many2one(related="document_id.folder_id", string="المجلد")
    state = fields.Selection([
        ("pending", "في الانتظار"),
        ("done", "جاهز"),
        ("empty", "لا يوجد محتوى"),
        ("error", "خطأ"),
    ], "الحالة", default="pending", required=True, readonly=True)
    generated_on = fields.Datetime("تاريخ الإصدار", readonly=True)
    assessment_id = fields.Many2one("azm.fin.assessment", "الإفادة المصدر", ondelete="set null", readonly=True)
    stamp = fields.Char(readonly=True, help="Fingerprint of the answers the document was built from.")
    outdated = fields.Boolean("يحتاج تحديث", compute="_compute_outdated",
                              help="الإجابات تغيرت بعد إصدار المستند؛ يُحدَّث تلقائيًا عند فتحه.")
    error = fields.Text("الخطأ", readonly=True)

    _company_key_uniq = models.Constraint("UNIQUE(company_id, key)", "This document already exists for the company.")

    # ---------------------------------------------------------------- computes
    @api.depends("kind", "requirement_id.tree_ref", "requirement_id.title", "module_id.code", "tab")
    def _compute_name(self):
        for pub in self:
            if pub.kind == "requirement":
                pub.name = f"{pub.requirement_id.tree_ref} · {pub.requirement_id.title}"
            elif pub.kind == "module":
                pub.name = f"FIN.{pub.module_id.code} · {MODULE_OUTPUTS[pub.tab][1]}" if pub.tab else False
            else:
                pub.name = "النموذج المالي الموحد · ملخص الكيان"

    @api.depends("state", "stamp")
    def _compute_outdated(self):
        for pub in self:
            pub.outdated = pub.state == "done" and pub.sudo()._current_stamp() != pub.stamp

    # ---------------------------------------------------------------- lookup
    @api.model
    def _key(self, kind, requirement=None, module=None, tab=None):
        if kind == "requirement":
            return f"req:{requirement.id}"
        if kind == "module":
            return f"mod:{module.id}:{tab}"
        return "summary"

    @api.model
    def _get(self, company, kind, requirement=None, module=None, tab=None):
        """The publication record (sudo), created when missing."""
        Pub = self.sudo()
        key = self._key(kind, requirement, module, tab)
        pub = Pub.search([("company_id", "=", company.id), ("key", "=", key)], limit=1)
        if not pub:
            pub = Pub.create({
                "company_id": company.id, "kind": kind, "key": key,
                "requirement_id": requirement.id if requirement else False,
                "module_id": (requirement.module_id.id if requirement else module.id if module else False),
                "tab": tab or False,
            })
        return pub

    @api.model
    def _ensure_company(self, company):
        """Every document a company should have, as publication records."""
        Pub = self.sudo()
        have = set(Pub.search([("company_id", "=", company.id)]).mapped("key"))
        vals = []
        for req in self.env["azm.fin.requirement"].sudo().search([]):
            if f"req:{req.id}" not in have:
                vals.append({"company_id": company.id, "kind": "requirement", "key": f"req:{req.id}",
                             "requirement_id": req.id, "module_id": req.module_id.id})
        for module in self.env["azm.fin.module"].sudo().search([]):
            for tab in MODULE_OUTPUTS:
                if f"mod:{module.id}:{tab}" not in have:
                    vals.append({"company_id": company.id, "kind": "module", "key": f"mod:{module.id}:{tab}",
                                 "module_id": module.id, "tab": tab})
        if "summary" not in have:
            vals.append({"company_id": company.id, "kind": "summary", "key": "summary"})
        Pub.create(vals)
        return Pub.search([("company_id", "=", company.id)])

    @api.model
    def _enqueue(self, companies=None, force=False):
        """Queue the documents of ``companies`` (all by default); only the outdated ones unless ``force``."""
        companies = companies or self.env["res.company"].sudo().search([])
        self.env["azm.doc.folder"]._ensure_all(companies)
        queued = self.sudo()
        for company in companies:
            pubs = self._ensure_company(company)
            if not force:
                pubs = pubs.filtered(lambda p: p.state != "done" or p._current_stamp() != p.stamp)
            pubs.write({"state": "pending", "error": False})
            queued |= pubs
        if queued:
            self._trigger_cron()
        return queued

    @api.model
    def _trigger_cron(self):
        cron = self.env.ref("azm_platform.ir_cron_azm_documents", raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()

    @api.model
    def _cron_process(self, limit=BATCH):
        pubs = self.sudo().search([("state", "=", "pending")], limit=limit,
                                  order="company_id, kind desc, module_sequence, tree_ref, id")
        for pub in pubs:
            pub._generate_safe()
        if self.sudo().search_count([("state", "=", "pending")]):
            self._trigger_cron()
        return True

    # ---------------------------------------------------------------- sources
    def _entity(self):
        self.ensure_one()
        return self.env["azm.entity"].sudo().with_context(active_test=False).search(
            [("company_id", "=", self.company_id.id)], limit=1)

    def _assessment(self):
        """The financial assessment the company's documents are built from: the approved one, else the latest."""
        self.ensure_one()
        Assessment = self.env["azm.fin.assessment"].sudo()
        entity = self._entity()
        if not entity:
            return Assessment
        return (Assessment.search([("entity_id", "=", entity.id), ("state", "=", "approved")],
                                  order="version desc, id desc", limit=1)
                or Assessment.search([("entity_id", "=", entity.id), ("state", "!=", "archived")],
                                     order="version desc, id desc", limit=1))

    def _lines(self, assessment):
        self.ensure_one()
        lines = assessment.answer_ids
        if self.kind == "requirement":
            return lines.filtered(lambda a: a.requirement_id == self.requirement_id)
        if self.kind == "module":
            return lines.filtered(lambda a: a.module_id == self.module_id)
        return lines

    def _current_stamp(self):
        """Fingerprint of what the document shows: the source assessment and the answers it is built from."""
        self.ensure_one()
        assessment = self._assessment()
        lines = self._lines(assessment) if assessment else self.env["azm.fin.answer"]
        req, module = self.requirement_id, self.module_id
        data = {
            "assessment": [assessment.id, assessment.version, assessment.state, assessment.is_demo,
                           str(assessment.approved_date or "")] if assessment else None,
            "catalogue": [req.tree_ref, req.title, req.question, req.owner, module.code, module.name],
            "lines": {line.code: [line.applicable, line._snapshot()] for line in lines},
        }
        return hashlib.md5(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()

    # ---------------------------------------------------------------- generation
    def _generate_safe(self):
        for pub in self:
            try:
                with self.env.cr.savepoint():
                    pub._generate()
            except Exception as error:  # noqa: BLE001 - one bad document must not stop the queue
                _logger.warning("Could not publish %s for %s", pub.name, pub.company_id.name, exc_info=True)
                pub.write({"state": "error", "error": str(error)[:2000]})

    def _generate(self):
        report = "azm_platform.action_report_azm_document"
        for pub in self.sudo():
            company = pub.company_id
            assessment = pub._assessment()
            stamp = pub._current_stamp()
            if pub.kind == "module" and not pub._module_items(assessment):
                if pub.document_id:
                    pub.document_id.active = False
                pub.write({"state": "empty", "generated_on": fields.Datetime.now(), "stamp": stamp,
                           "assessment_id": assessment.id, "error": False})
                continue
            content, fmt = self.env["ir.actions.report"].sudo().with_company(company)._render_qweb_pdf(
                report, res_ids=pub.ids)
            pdf = fmt == "pdf"
            folder_key = ("FIN" if pub.kind == "requirement" else
                          MODULE_OUTPUTS[pub.tab][0] if pub.kind == "module" else "RPT")
            folder = self.env["azm.doc.folder"]._folder(
                company, folder_key, pub.requirement_id.module_id if pub.kind == "requirement" else None)
            vals = {
                "name": f"{pub.name}.{'pdf' if pdf else 'html'}",
                "raw": content,
                "mimetype": "application/pdf" if pdf else "text/html",
                "folder_id": folder.id,
            }
            document = pub.document_id
            if document:
                document.write({**vals, "active": True})
            else:
                document = self.env["documents.document"].sudo().with_company(company).create({
                    **vals, "type": "binary", "company_id": company.id, "access_internal": "view",
                })
            pub.write({"document_id": document.id, "state": "done", "generated_on": fields.Datetime.now(),
                       "stamp": stamp, "assessment_id": assessment.id, "error": False})
        return True

    # ---------------------------------------------------------------- user actions
    def action_read(self):
        return self._open(download=False)

    def action_download(self):
        return self._open(download=True)

    def _open(self, download=False):
        """Bring the document up to date if needed, then show or download it."""
        self.ensure_one()
        self.sudo(False).check_access("read")   # the company rules decide who sees what
        pub = self.sudo()
        if pub.state != "done" or not pub.document_id or pub._current_stamp() != pub.stamp:
            pub._generate()
        if pub.state == "empty":
            raise UserError(_("No requirement of this module falls in this output for %s.", pub.company_id.name))
        attachment = pub.document_id.attachment_id
        if not attachment:
            raise UserError(_("The document could not be produced. Try again or ask an administrator."))
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download={'true' if download else 'false'}",
            "target": "download" if download else "new",
        }

    def action_open_folder(self):
        """Open the folder of the document in the Documents app."""
        self.ensure_one()
        self.sudo(False).check_access("read")
        folder = self.sudo().document_id.folder_id
        if not folder:
            raise UserError(_("This document has not been published yet."))
        action = self.env["ir.actions.act_window"]._for_xml_id("documents.document_action")
        action.update({"name": folder.name, "domain": [("folder_id", "=", folder.id)],
                       "context": {"searchpanel_default_folder_id": folder.id}})
        return action

    def action_refresh(self):
        self.sudo(False).check_access("read")
        self.sudo()._generate_safe()
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"type": "success", "message": _("Document updated."),
                           "next": {"type": "ir.actions.client", "tag": "soft_reload"}}}

    # ---------------------------------------------------------------- report payload
    def _module_items(self, assessment):
        """Requirements that belong in this module output, as engine dicts (in tree order)."""
        self.ensure_one()
        if not assessment:
            return []
        lines = self._lines(assessment).filtered("applicable").sorted(
            lambda a: (a.topic_sequence, a.requirement_sequence, a.id))
        items = [(line, line._engine_dict()) for line in lines]
        if self.tab in fin_engine.TAB_PROFILES:
            profiles = fin_engine.TAB_PROFILES[self.tab]
            return [(l, i) for l, i in items if i["profile"] in profiles and i["state"]]
        if self.tab == "gaps":
            return [(l, i) for l, i in items if i["state"] in ("partial", "unavailable")]
        if self.tab == "future":
            return [(l, i) for l, i in items if i["state"] in ("unavailable", "partial", "unknown")
                    or (i["target"] and i["target"] != "استمرار")]
        return []

    @api.model
    def _status(self, key):
        arabic, english, css = STATUS.get(key or "open", STATUS["open"])
        return {"key": key or "open", "ar": arabic, "en": english, "css": css}

    @api.model
    def _item(self, requirement, line=None, item=None):
        """One requirement, in plain words, for the report templates."""
        req = requirement
        module = req.module_id
        data = {
            "tree_ref": req.tree_ref or req.code,
            "title": req.title,
            "question": req.question,
            "ids": " · ".join(x for x in (req.req_id, req.code) if x),
            "owner": req.owner or "",
            "profile": PROFILES[req.profile][0],
            "scope": SCOPES.get(req.scope_code, ""),
            "path": [
                ("النموذج", "FIN", "النموذج المالي الموحد"),
                ("الموديول", f"FIN.{module.code}", module.name),
                ("الموضوع", req.topic_id.code or "", req.topic_id.name or ""),
                ("المتطلب", req.tree_ref or req.code, req.title),
            ],
            "topic_code": req.topic_id.code or "",
            "topic": req.topic_id.name or "",
            "answers": [], "tables": [], "steps": [], "pending": [],
            "impl": "", "rule": "", "target": "", "problems": "", "target_note": "", "na_reason": "",
            "missing": [],
        }
        if not line:
            data["status"] = self._status("open")
            data["pending"] = req.question_ids.filtered(lambda q: q.role in ("main", "follow")).mapped("label")
            return data
        item = item or line._engine_dict()
        if not line.applicable:
            data["status"] = self._status("na")
            data["na_reason"] = "خارج أنشطة الكيان المسجلة (نطاق الانطباق: %s)." % data["scope"]
            return data
        data["status"] = self._status(item["state"])
        for qa in item["qa"]:
            columns = qa["columns"]
            if qa["qtype"] == "table" and qa["rows"]:
                if columns and columns[0]["label"] in fin_engine.STEP_COLUMNS:
                    data["steps"].append({"label": qa["label"], "items": [{
                        "title": (row[0] if row else "") or "[لم يُحدد]",
                        "detail": " · ".join(f"{columns[i]['label']}: {row[i]}"
                                             for i in range(1, min(len(columns), len(row))) if row[i]),
                    } for row in qa["rows"]]})
                else:
                    data["tables"].append({
                        "label": qa["label"], "columns": [c["label"] for c in columns],
                        "rows": [[row[i] if i < len(row) else "" for i in range(len(columns))] for row in qa["rows"]],
                    })
            else:
                # the main question is already the "what is required" line: do not print it twice
                label = "الإجابة" if qa["label"].strip() == (req.question or "").strip() else qa["label"]
                data["answers"].append({"label": label, "value": qa["display"], "muted": qa["fallback"]})
        data.update({
            "impl": "، ".join(item["impl"]), "rule": item["rule"], "target": item["target"],
            "problems": item["issues"], "target_note": item["target_note"],
            "na_reason": item["reason"] if item["state"] == "na" else "",
            "missing": item["missing"],
        })
        if not item["state"]:
            # started but this requirement is not answered yet: list what is still to answer
            data["pending"] = item["missing"] or req.question_ids.filtered(
                lambda q: q.role in ("main", "follow")).mapped("label")
        return data

    def _azm_payload(self):
        """Everything the report template shows, as plain values."""
        self.ensure_one()
        pub = self.sudo()
        company = pub.company_id
        entity = pub._entity()
        assessment = pub._assessment()
        tz = pytz.timezone(self.env.user.tz or "Africa/Cairo")
        now = pytz.utc.localize(fields.Datetime.now()).astimezone(tz)

        if not assessment:
            banner = ("info", "لم تبدأ إفادة هذا الكيان بعد — هذه نسخة فارغة توضح المطلوب والأسئلة.")
        elif assessment.is_demo:
            banner = ("warn", "مثال افتراضي للتجربة — ليست بيانات فعلية عن الكيان.")
        elif assessment.state == "approved":
            approved = assessment.approved_date and fields.Date.to_string(assessment.approved_date) or ""
            banner = ("ok", f"معتمد · الإصدار {assessment.version} · {approved}")
        else:
            banner = ("info", "مسودة — مبنية على إفادة الكيان ولم يتم التحقق من الأدلة بعد.")
        source = (f"{assessment.name} · الإصدار {assessment.version} · "
                  f"{dict(assessment._fields['state'].selection)[assessment.state]}") if assessment else "لا توجد إفادة"

        payload = {
            "company": company.name,
            "entity_code": entity.code or "",
            "banner": {"css": banner[0], "text": banner[1]},
            "generated": now.strftime("%Y-%m-%d %H:%M"),
            "items": [],
            "summary": [],
        }
        if pub.kind == "requirement":
            req = pub.requirement_id
            line = pub._lines(assessment)[:1] if assessment else None
            item = self._item(req, line)
            payload.update({
                "doc_type": ("ورقة متطلب", "Requirement sheet"),
                "code": item["tree_ref"],
                "title": req.title,
                "path": item["path"],
                "glance": [
                    ("الكيان", "Entity", company.name),
                    ("الحالة اليوم", "Status today", item["status"]["ar"]),
                    ("المالك المقترح", "Proposed owner", item["owner"] or "—"),
                    ("نوع المتطلب", "Type", item["profile"]),
                    ("المصدر", "Source", source),
                    ("الأكواد", "IDs", item["ids"]),
                ],
                "items": [item],
                "single": True,
            })
        elif pub.kind == "module":
            module = pub.module_id
            folder, arabic, english, code = MODULE_OUTPUTS[pub.tab]
            items = [self._item(line.requirement_id, line, item) for line, item in pub._module_items(assessment)]
            payload.update({
                "doc_type": (arabic, english),
                "code": f"{code}-{module.code}",
                "title": f"{arabic} — {module.name}",
                "path": [("النموذج", "FIN", "النموذج المالي الموحد"),
                         ("الموديول", f"FIN.{module.code}", module.name),
                         ("المخرج", code, arabic)],
                "glance": [
                    ("الكيان", "Entity", company.name),
                    ("الموديول", "Module", f"FIN.{module.code} · {module.name}"),
                    ("عدد المتطلبات", "Requirements", str(len(items))),
                    ("المصدر", "Source", source),
                ],
                "items": items,
                "single": False,
            })
        else:
            rows = []
            if assessment:
                for module in self.env["azm.fin.module"].sudo().search([]):
                    lines = assessment.answer_ids.filtered(lambda a, m=module: a.module_id == m and a.applicable)
                    states = lines.mapped("state")
                    rows.append({
                        "code": f"FIN.{module.code}", "name": module.name, "applicable": len(lines),
                        "done": len(lines.filtered("is_done")),
                        "full": states.count("full"), "partial": states.count("partial"),
                        "unavailable": states.count("unavailable"),
                    })
            payload.update({
                "doc_type": ("ملخص الكيان", "Entity summary"),
                "code": "FIN",
                "title": f"النموذج المالي الموحد — {company.name}",
                "path": [("النموذج", "FIN", "النموذج المالي الموحد")],
                "glance": [
                    ("الكيان", "Entity", company.name),
                    ("المصدر", "Source", source),
                    ("الأسئلة المُجابة", "Answered",
                     f"{assessment.answered_count} من {assessment.question_count}" if assessment else "—"),
                    ("الفجوات", "Gaps", str(assessment.gap_count) if assessment else "—"),
                ],
                "summary": rows,
                "single": False,
            })
        payload["verify"] = f"{payload['code']} / {payload['entity_code'] or company.id}" + (
            f" / v{assessment.version}" if assessment else "")
        # module outputs group their requirements under their topic: model › module › topic › requirement
        groups = []
        for item in payload["items"]:
            if not groups or groups[-1]["code"] != item["topic_code"]:
                groups.append({"code": item["topic_code"], "name": item["topic"], "items": []})
            groups[-1]["items"].append(item)
        payload["groups"] = groups
        glance = payload["glance"]
        payload["glance_rows"] = [glance[i:i + 2] for i in range(0, len(glance), 2)]
        return payload


class AzmFinRequirement(models.Model):
    _inherit = "azm.fin.requirement"

    azm_doc_ids = fields.One2many("azm.doc.publication", "requirement_id", string="المستندات")

    def action_azm_publish_documents(self):
        """(Re)build this requirement's document for every company now."""
        Pub = self.env["azm.doc.publication"]
        for req in self:
            for company in self.env["res.company"].sudo().search([]):
                Pub._get(company, "requirement", requirement=req)._generate_safe()
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"type": "success", "message": _("Documents updated for every entity."),
                           "next": {"type": "ir.actions.client", "tag": "soft_reload"}}}


class AzmFinAnswer(models.Model):
    _inherit = "azm.fin.answer"

    def _azm_publication(self):
        self.ensure_one()
        self.check_access("read")
        return self.env["azm.doc.publication"]._get(
            self.company_id, "requirement", requirement=self.requirement_id).sudo(False)

    def action_azm_doc_read(self):
        return self._azm_publication()._open(download=False)

    def action_azm_doc_download(self):
        return self._azm_publication()._open(download=True)


class AzmFinAssessment(models.Model):
    _inherit = "azm.fin.assessment"

    azm_doc_count = fields.Integer("المستندات", compute="_compute_azm_doc_count")

    def _compute_azm_doc_count(self):
        counts = dict(self.env["azm.doc.publication"].sudo()._read_group(
            [("company_id", "in", self.company_id.ids), ("state", "=", "done")], ["company_id"], ["__count"]))
        for rec in self:
            rec.azm_doc_count = counts.get(rec.company_id, 0)

    def action_azm_publish_documents(self):
        """Queue every document of the entity; they are built in the background."""
        queued = self.env["azm.doc.publication"]._enqueue(self.company_id, force=True)
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"type": "info", "sticky": False,
                           "message": _("%s documents are being published to Documents.", len(queued))}}

    def action_azm_view_documents(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("azm_platform.action_azm_doc_publication")
        action["domain"] = [("company_id", "=", self.company_id.id)]
        action["context"] = {"search_default_by_kind": 1, "search_default_by_module": 1}
        return action

    def action_submit(self):
        res = super().action_submit()
        self.env["azm.doc.publication"]._enqueue(self.company_id)
        return res

    def action_approve(self):
        res = super().action_approve()
        self.env["azm.doc.publication"]._enqueue(self.company_id)
        return res


class ResCompany(models.Model):
    _inherit = "res.company"

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        self.env["azm.doc.folder"]._ensure_all(companies)
        return companies
