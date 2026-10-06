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
import os
from datetime import timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.azm_operating_model.models import fin_engine

from .azm_coding import (LIFECYCLE_LABELS, MODULE_WIDE_OUTPUTS, PROFILE_OUTPUT,
                         TYPE_LABELS, WHOLE_MODEL)
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
    "PUR": (12, "دورة المشتريات", "Procurement Cycle", False),
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

# Which registry artifact type each output of the financial model is, and which
# lifecycle stage it speaks from. Identity is the type; the stage is said beside it.
FIN_ARTIFACTS = {
    "rules": ("POL", "CS"),
    "workflow": ("PRO", "CS"),
    "authority": ("DOA", "CS"),
    "reports": ("RPT", "CS"),
    "integration": ("SRQ", "TD"),
    "gaps": ("GAP", "GR"),
    "future": ("DEC", "TD"),
}
# … and the documents that are not an output of a module
FIN_KIND_ARTIFACTS = {
    "requirement": ("REQ", "CS"),
    "summary": ("RPT", "CS"),
    "book": ("MAN", "CS"),
}

KINDS = [("requirement", "متطلب · Requirement"), ("module", "مخرج موديول · Module output"),
         ("summary", "ملخص الكيان · Entity summary"), ("book", "كتاب النموذج · Model book")]
TABS = [(k, f"{v[1]} · {v[2]}") for k, v in MODULE_OUTPUTS.items()]
BATCH = 20
# Minutes to wait before each retry of a document that failed to render. A failure is
# usually transient (a registry reload mid-flight, a lock, a renderer hiccup), so the
# first retry comes quickly; after the last one the document stays in error for a human.
RETRY_BACKOFF = (5, 15, 60, 240, 720)


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
    def _folder(self, company, key="ROOT", sub=None):
        """The folder of ``company`` for ``key``, created on first use.

        ``sub`` is an optional (code, name) pair for a folder inside it — one per
        module of the financial model, one per stage of the cycle."""
        company = company.sudo()
        root = self._ensure(company, "ROOT", company.name, False, upload=False)
        if key == "ROOT":
            return root
        folder = self._ensure(company, key, _folder_name(key), root, upload=FOLDERS[key][3])
        if sub:
            code, name = sub
            folder = self._ensure(company, f"{key}/{code}", name, folder, upload=False)
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
        stages = self.env["azm.stage"].sudo().search([])
        for company in companies:
            for key in FOLDERS:
                self._folder(company, key)
            for module in modules:
                self._folder(company, "FIN", (module.code, f"FIN.{module.code} · {module.name}"))
            for stage in stages:
                self._folder(company, "PUR", (stage.code, f"PUR-{stage.code} · {stage.name}"))
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
    module_sequence = fields.Integer("ترتيب المكوّن", related="module_id.sequence", store=True)
    tab = fields.Selection(TABS, "المخرج")
    artifact_id = fields.Many2one("azm.artifact", "المخرج المعتمد", readonly=True, index=True,
                                  ondelete="set null",
                                  help="المخرج الذي يُعد هذا المستند نسخة الكيان منه.")
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
    # Where the answers behind this document stand. A deliverable built from a draft is
    # a draft deliverable however finished the file looks, and one built from an
    # approved assessment is approved — which is the difference between something being
    # written and something being issued. Stored so the library can group and filter on
    # it; it recomputes when an assessment changes state, which is exactly when a
    # deliverable becomes issued.
    source_state = fields.Selection([
        ("draft", "مسودة"),
        ("review", "تحت المراجعة"),
        ("approved", "معتمدة"),
        ("archived", "نسخة سابقة"),
    ], "حالة المصدر", compute="_compute_source_state", store=True, index=True)
    stamp = fields.Char(readonly=True, help="Fingerprint of the answers the document was built from.")
    outdated = fields.Boolean("يحتاج تحديث", compute="_compute_outdated",
                              help="الإجابات تغيرت بعد إصدار المستند؛ يُحدَّث تلقائيًا عند فتحه.")
    build = fields.Selection([
        ("queued", "يُبنى مع الدفعة"),
        ("on_open", "يُبنى عند أول فتح"),
    ], "طريقة الإصدار", default="queued", required=True, readonly=True,
        help="المستندات الكثيرة العدد تُبنى عند أول فتح بدل إصدارها كلها مقدمًا، "
             "فلا يشغل القرص إلا ما يُقرأ فعلًا.")
    error = fields.Text("الخطأ", readonly=True)
    attempts = fields.Integer("محاولات الإصدار", readonly=True, default=0,
                              help="عدد المحاولات الفاشلة المتتالية. يُصفَّر عند نجاح الإصدار.")
    retry_after = fields.Datetime("إعادة المحاولة بعد", readonly=True,
                                  help="موعد إعادة المحاولة تلقائيًا بعد فشل الإصدار.")

    _company_key_uniq = models.Constraint("UNIQUE(company_id, key)", "This document already exists for the company.")

    # ---------------------------------------------------------------- computes
    @api.depends("kind", "requirement_id.tree_ref", "requirement_id.title", "module_id.code", "tab")
    def _compute_name(self):
        for pub in self:
            if pub.kind == "requirement":
                req = pub.requirement_id
                pub.name = f"{req.tree_ref or req.code} · {req.title}"
            elif pub.kind == "module":
                pub.name = f"FIN.{pub.module_id.code} · {MODULE_OUTPUTS[pub.tab][1]}" if pub.tab else False
            elif pub.kind == "summary":
                pub.name = "النموذج المالي الموحد · ملخص الكيان"
            elif pub.kind == "book":
                pub.name = "النموذج المالي الموحد · الكتاب الكامل"

    @api.depends("assessment_id.state", "proc_assessment_id.state")
    def _compute_source_state(self):
        for pub in self:
            source = pub.assessment_id or pub.proc_assessment_id
            pub.source_state = source.state if source else False

    @api.depends("state", "stamp")
    def _compute_outdated(self):
        # the list view shows this column, so it is computed for a whole page at a time:
        # the source assessment is resolved once per company rather than once per row
        live = self.filtered(lambda p: p.state == "done").sudo()
        cache = self._source_cache(live)
        for pub in self:
            source = pub.sudo()
            pub.outdated = (pub.state == "done"
                            and source._current_stamp(cache.get(source._source_key())) != pub.stamp)

    # ---------------------------------------------------------------- lookup
    @api.model
    def _key(self, kind, requirement=None, module=None, tab=None):
        if kind == "requirement":
            return f"req:{requirement.id}"
        if kind == "module":
            return f"mod:{module.id}:{tab}"
        return kind   # summary, book — one of each per company

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
            # looked up, never numbered here: _get is reached from reads
            pub.artifact_id = pub._artifact(create=False).id
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
            for tab in module._azm_outputs():
                if f"mod:{module.id}:{tab}" not in have:
                    vals.append({"company_id": company.id, "kind": "module", "key": f"mod:{module.id}:{tab}",
                                 "module_id": module.id, "tab": tab})
        if "summary" not in have:
            vals.append({"company_id": company.id, "kind": "summary", "key": "summary"})
        if "book" not in have:
            # bound from every other document of the model, so it is built when asked for
            vals.append({"company_id": company.id, "kind": "book", "key": "book", "build": "on_open"})
        Pub.create(vals)
        self._drop_impossible(company)
        return Pub.search([("company_id", "=", company.id)])

    @api.model
    def _drop_impossible(self, company):
        """Retire documents for outputs their node cannot have.

        A module with no requirement of a kind has no document of that kind. Such
        documents were filed before the catalogue was asked what it could actually
        produce, and they linger as empty files that are counted and offered. Their
        record goes and the file in Documents is archived rather than deleted, so
        nothing a person may have linked to disappears under them.
        """
        Pub = self.sudo()
        stale = Pub.browse()
        # what a node can have is a property of the node, so it is asked once per node
        # rather than once per document filed against it
        allowed = {}
        for kind, field in (("module", "module_id"), ("stage", "stage_id")):
            for pub in Pub.search([("company_id", "=", company.id), ("kind", "=", kind)]):
                node = pub[field]
                if node.id not in allowed:
                    allowed[node.id] = set(node._azm_outputs()) if node else set()
                if pub.tab not in allowed[node.id]:
                    stale |= pub
        if stale:
            stale.document_id.filtered("active").write({"active": False})
            stale.unlink()
        return stale

    @api.model
    def _due_domain(self, now=None):
        """Documents the queue may pick up: the pending ones, and the failed ones whose
        backoff has elapsed and that have retries left (a failure from before this field
        existed carries no retry_after and is due at once)."""
        now = now or fields.Datetime.now()
        return [
            ("build", "=", "queued"),
            "|",
                ("state", "=", "pending"),
            "&", ("state", "=", "error"),
            "&", ("attempts", "<=", len(RETRY_BACKOFF)),
            "|", ("retry_after", "=", False), ("retry_after", "<=", now),
        ]

    @api.model
    def _enqueue(self, companies=None, force=False):
        """Queue the documents of ``companies`` (all by default); only the outdated ones unless ``force``."""
        companies = companies or self.env["res.company"].sudo().search([])
        self.env["azm.doc.folder"]._ensure_all(companies)
        queued = self.sudo()
        # the catalogue is the same for every company: read it once for the whole loop
        self.env["azm.fin.requirement"].sudo().search([])
        self.env["azm.fin.module"].sudo().search([])
        self.env["azm.question"].sudo().search([])
        self.env["azm.stage"].sudo().search([])
        # The documents come first. The registry numbers what the group produces, and
        # what it produces is read off them — so numbering before they exist would count
        # a deliverable nobody has as real. Numbering must still happen before the
        # outdated check below, because a document prints its code and ages when it
        # changes: a renumbered one has to be queued in the same pass.
        filed = [(company, self._ensure_company(company)) for company in companies]
        self.env["azm.artifact"]._register_all()
        self._link_artifacts()
        for company, pubs in filed:
            pubs = pubs.filtered(lambda p: p.build == "queued")
            if not force:
                cache = self._source_cache(pubs)
                pubs = pubs.filtered(
                    lambda p: p.state != "done"
                    or p._current_stamp(cache.get(p._source_key())) != p.stamp)
            pubs.write({"state": "pending", "error": False, "attempts": 0, "retry_after": False})
            queued |= pubs
        if queued:
            self._trigger_cron()
        return queued

    @api.model
    def _trigger_cron(self, at=None):
        cron = self.env.ref("azm_platform.ir_cron_azm_documents", raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger(at)

    @api.model
    def _cron_process(self, limit=BATCH):
        pubs = self.sudo().search(self._due_domain(), limit=limit,
                                  order="company_id, kind desc, module_sequence, tree_ref, id")
        for pub in pubs:
            pub._generate_safe()
        self._schedule_next()
        return True

    @api.model
    def _schedule_next(self):
        """Keep the queue moving: straight away while work is ready, otherwise at the moment
        the next failed document is due again — never a tight loop over documents in backoff."""
        now = fields.Datetime.now()
        if self.sudo().search_count(self._due_domain(now), limit=1):
            self._trigger_cron()
            return
        waiting = self.sudo().search(
            [("state", "=", "error"), ("attempts", "<=", len(RETRY_BACKOFF)), ("retry_after", ">", now)],
            order="retry_after", limit=1)
        if waiting:
            self._trigger_cron(at=waiting.retry_after)

    # ---------------------------------------------------------------- sources
    def _entity(self):
        self.ensure_one()
        return self.env["azm.entity"].sudo().with_context(active_test=False).search(
            [("company_id", "=", self.company_id.id)], limit=1)

    def _source_key(self):
        """What the source assessment depends on: the company, and which model asks.

        Every document of a company is built from the same assessment, so resolving it
        per document meant three searches each — ~250 documents of one company all
        finding the same record.
        """
        self.ensure_one()
        return self.company_id.id, "fin"

    @api.model
    def _source_cache(self, publications):
        """{source key: assessment} for a batch, each resolved once."""
        cache = {}
        for pub in publications:
            key = pub._source_key()
            if key not in cache:
                cache[key] = pub._assessment()
        return cache

    def _assessment(self):
        """The financial assessment the company's documents are built from: the approved
        one, else the latest.

        Elevated on purpose, and not the same decision as the tree's. A document is the
        entity's published output — azm.doc.publication is readable by anyone who works
        in the company (security/ir.access.csv), and it is built by a cron that runs as
        nobody — so it is resolved regardless of who is reading. The *tree* shows the
        answers live rather than as a published document, so it reads them as the user
        (azm_fin_tree._fin_assessment) and shows nothing it may not.
        """
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

    def _current_stamp(self, assessment=None):
        """Fingerprint of what the document shows: the source assessment and the answers
        it is built from. ``assessment`` lets a batch resolve it once for the company."""
        self.ensure_one()
        if self.kind in self._book_kinds():
            # a book is exactly its parts: it ages when any one of them would
            parts = self._book_parts()
            cache = self._source_cache(parts)
            stamps = [part._current_stamp(cache.get(part._source_key())) for part in parts]
            return hashlib.md5(json.dumps(stamps).encode()).hexdigest()
        if assessment is None:
            assessment = self._assessment()
        lines = self._lines(assessment) if assessment else self.env["azm.fin.answer"]
        req, module = self.requirement_id, self.module_id
        data = {
            "assessment": [assessment.id, assessment.version, assessment.state, assessment.is_demo,
                           str(assessment.approved_date or "")] if assessment else None,
            "catalogue": [req.tree_ref, req.title, req.question, req.owner, module.code, module.name],
            # The code a document prints is part of what it says, so one filed under an
            # older coding ages by itself and is rebuilt when next read. It is the
            # *scoped* code that is printed — the entity's own — so renaming an entity
            # ages that entity's documents and nobody else's. Looked up and not
            # allocated: this runs inside the `outdated` compute.
            "coding": [self._scoped_code(), self._lifecycle()],
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
                attempts = pub.attempts + 1
                delay = RETRY_BACKOFF[attempts - 1] if attempts <= len(RETRY_BACKOFF) else None
                _logger.warning("Could not publish %s for %s (attempt %s/%s, %s)", pub.name,
                                pub.company_id.name, attempts, len(RETRY_BACKOFF) + 1,
                                f"retrying in {delay} min" if delay else "giving up", exc_info=True)
                pub.write({
                    "state": "error", "error": str(error)[:2000], "attempts": attempts,
                    "retry_after": fields.Datetime.now() + timedelta(minutes=delay) if delay else False,
                })

    def _generate(self):
        report = "azm_platform.action_report_azm_document"
        for pub in self.sudo():
            company = pub.company_id
            assessment = pub._assessment()
            stamp = pub._current_stamp()
            if pub._is_empty(assessment):
                if pub.document_id:
                    pub.document_id.active = False
                pub.write({"state": "empty", "generated_on": fields.Datetime.now(), "stamp": stamp,
                           "error": False, "attempts": 0, "retry_after": False,
                           **pub._source_vals(assessment)})
                continue
            content, fmt = self.env["ir.actions.report"].sudo().with_company(company)._render_qweb_pdf(
                report, res_ids=pub._report_ids())
            pdf = fmt == "pdf"
            folder = self.env["azm.doc.folder"]._folder(company, *pub._folder_key())
            vals = {
                # a question is coded PUR-GOV/model, and a slash is a path separator to
                # every browser that downloads the file: it is filed with a dash
                "name": f"{pub.name}.{'pdf' if pdf else 'html'}".replace("/", "-"),
                "raw": content,
                "mimetype": "application/pdf" if pdf else "text/html",
                "folder_id": folder.id,
            }
            document = pub.document_id
            if document:
                if pub._file_missing() and document.attachment_id:
                    # the old file is gone, and Odoo reads it to replace it: let go of
                    # the dangling pointer first, or rebuilding fails on the very thing
                    # it is meant to repair
                    self.env.cr.execute(
                        "UPDATE ir_attachment SET store_fname = NULL, db_datas = NULL, "
                        "file_size = 0 WHERE id = %s", (document.attachment_id.id,))
                    document.attachment_id.invalidate_recordset()
                document.write({**vals, "active": True})
            else:
                document = self.env["documents.document"].sudo().with_company(company).create({
                    **vals, "type": "binary", "company_id": company.id, "access_internal": "view",
                })
            pub.write({"document_id": document.id, "state": "done", "generated_on": fields.Datetime.now(),
                       "stamp": stamp, "error": False, "attempts": 0, "retry_after": False,
                       # building one is the moment its artifact certainly exists
                       "artifact_id": pub._artifact().id,
                       **pub._source_vals(assessment)})
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
        if (pub.state != "done" or not pub.document_id or pub._file_missing()
                or pub._current_stamp() != pub.stamp):
            # _generate_safe, not _generate: a document built here is often the first of
            # its kind anyone has asked for, and a failure has to be recorded and retried
            # like any other instead of reaching the reader as a traceback
            pub._generate_safe()
        if pub.state == "error":
            raise UserError(_("The document could not be produced: %s", pub.error or ""))
        if pub.state == "empty":
            raise UserError(pub._empty_message())
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
        # it rewrites the document and files a new one: the right to do that is write,
        # and read-only users had been able to force it
        self.sudo(False).check_access("write")
        pub = self.sudo()
        pub.write({"attempts": 0, "retry_after": False})   # an explicit retry starts the budget over
        pub._generate_safe()
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"type": "success", "message": _("Document updated."),
                           "next": {"type": "ir.actions.client", "tag": "soft_reload"}}}

    def _empty_message(self):
        """Why this document has nothing in it, in the words of its own model."""
        self.ensure_one()
        return _("No requirement of this module falls in this output for %s.", self.company_id.name)

    def _file_missing(self):
        """True when the document says it is ready but its file is not on disk.

        It should not happen, and it has: the filestore's garbage collector cannot see
        a file that no live transaction references yet, so one dropped out from under a
        published document. Rather than hand the reader a broken link, the document is
        simply built again — it is reproducible from the answers.
        """
        self.ensure_one()
        attachment = self.document_id.attachment_id
        if not attachment:
            return True
        if not attachment.store_fname:
            return not attachment.db_datas
        return not os.path.exists(os.path.join(attachment._filestore(), attachment.store_fname))

    def _is_empty(self, assessment):
        """True when the document would carry nothing: it is filed as empty, not built."""
        self.ensure_one()
        if self.kind in self._book_kinds():
            return len(self._book_parts()) <= 1   # nothing but the entity's own summary
        if self.kind == "requirement":
            # A requirement is now the deliverable itself, so the promise that only what
            # the group produces gets numbered has to hold here too: a requirement no
            # entity finds applicable — nobody does investments — is not a policy of
            # theirs, and a page saying so is not one either.
            #
            # Not having started is a different thing from not applying. An entity with
            # no assessment yet gets the blank sheet, which is the list of what it has
            # to answer; that is the whole use of it.
            if not assessment:
                return False
            line = self._lines(assessment)[:1]
            return not (line and line.applicable)
        return self.kind == "module" and not self._module_items(assessment)

    # ---------------------------------------------------------------- coding
    def _artifact_ref(self):
        """What this document is registered under in the coding registry."""
        self.ensure_one()
        if self.kind == "requirement":
            return f"azm.fin.requirement,{self.requirement_id.id}"
        if self.kind == "module":
            return f"azm.fin.module,{self.module_id.id},{self.tab}"
        return f"fin:{self.kind}"

    def _artifact(self, create=True):
        """The master artifact this document is a copy of, per the coding registry.

        One artifact per node and output for the whole group: the nine entities that
        hold the policy of FIN.GOV all print AZM-FIN-POL-000001 on it, and what tells
        their copies apart is the scope beside the code, never the code itself.

        ``create=False`` only looks: a compute field and a read-only request both ask
        what a document is called, and numbering one there would be a write.
        """
        self.ensure_one()
        Artifact = self.env["azm.artifact"]
        ref = self._artifact_ref()
        if not create:
            return Artifact._find(ref)
        if self.kind == "requirement":
            # A requirement *is* the deliverable — a policy, a procedure, an authority —
            # and which one comes from the profile it is answered under. One that falls
            # in no output is a question nobody issues anything for.
            req = self.requirement_id
            tab = PROFILE_OUTPUT.get(req.profile)
            if not tab:
                return Artifact
            module = req.module_id
            return Artifact._of(ref, "FIN", FIN_ARTIFACTS[tab][0], node=module.code,
                                name=f"FIN.{module.code} · {req.title}")
        if self.kind == "module":
            # the module's compiled version of its policies is a binding of them, not a
            # deliverable beside them; its gap register and target direction are
            # readings across the module and are
            if self.tab not in MODULE_WIDE_OUTPUTS:
                return Artifact
            return Artifact._of(ref, "FIN", FIN_ARTIFACTS[self.tab][0],
                                node=self.module_id.code,
                                name=f"FIN.{self.module_id.code} · {MODULE_OUTPUTS[self.tab][1]}")
        return Artifact._of(ref, "FIN", FIN_KIND_ARTIFACTS[self.kind][0],
                            node=WHOLE_MODEL, name=self.name)

    def _scoped_code(self):
        """This entity's copy of the deliverable, under its own name.

        The master is the group's — AZM-FIN-GOV-POL-000001 — and every entity holds the
        same one; that is what "store once, map many" means and it is why the entity is
        not part of the master's identity. But the thing that sits in Future
        University's folders is *their* copy, and it says so: FUE-FIN-GOV-POL-000001,
        the same deliverable at their scope. The master code travels with it, so one can
        always be read back to the other.
        """
        self.ensure_one()
        artifact = self._artifact(create=False)
        if not artifact:
            return ""
        entity = self._entity()
        prefix = (entity.code or "").strip() if entity else ""
        if not prefix:
            return artifact.code
        _group, _sep, rest = artifact.code.partition("-")
        return f"{prefix}-{rest}" if rest else artifact.code

    def _tree_ref(self):
        """Where to find this document's node in the tree.

        The canonical code is the identity; this is how a reader gets back to the thing
        the document is about. It names the node — not the pre-registry shorthand the
        output used to be coded by, which no longer identifies anything.
        """
        self.ensure_one()
        if self.kind == "requirement":
            return self.requirement_id.tree_ref or self.requirement_id.code or "FIN"
        if self.kind == "module":
            return f"FIN.{self.module_id.code}"
        return "FIN"

    def _lifecycle(self):
        """Which stage of CS → GR → TD → … this document speaks from."""
        self.ensure_one()
        if self.kind == "module":
            return FIN_ARTIFACTS[self.tab][1]
        return FIN_KIND_ARTIFACTS[self.kind][1]

    @api.model
    def _produced_refs(self):
        """``(filed, produced)`` — the deliverables the group has documents filed under,
        and the ones it actually produces something for.

        A deliverable the registry *could* define is not a deliverable. Every entity in
        the group marked investments, real estate and inter-company not applicable, so
        every copy of the investments policy is empty: there is no investments policy to
        number, to shelve or to count, and numbering one pushed every real policy after
        it up by a place.

        The question is put to the answers rather than to the built files, so a document
        nobody has ever opened is judged on what it would say rather than counted as
        produced because nothing has disproved it yet. A document already built with
        content answers for itself and is not asked twice.
        """
        filed, produced = set(), set()
        pubs = self.sudo().search([])
        cache = self._source_cache(pubs)
        for pub in pubs:
            ref = pub._artifact_ref()
            filed.add(ref)
            if ref in produced:
                continue
            # Asked of the answers every time, not read off the file. "Already built,
            # so it must have had something in it" is only true of the rule it was built
            # under: a requirement sheet filed as done before a requirement became a
            # deliverable in its own right would be grandfathered in for ever.
            if not pub._is_empty(cache.get(pub._source_key())):
                produced.add(ref)
        return filed, produced

    @api.model
    def _link_artifacts(self):
        """Point every document at the artifact it is a copy of.

        The link is derivable — a document knows its node and its output — but deriving
        it per row is what made a library of the group's deliverables expensive. It is
        stored once instead, and refreshed whenever the registry gains an entry.
        """
        Artifact = self.env["azm.artifact"].sudo()
        by_ref = {art.ref: art.id for art in Artifact.search([])}
        pending = self.sudo().search([("artifact_id", "=", False)])
        grouped = {}
        for pub in pending:
            artifact = by_ref.get(pub._artifact_ref())
            if artifact:
                grouped.setdefault(artifact, []).append(pub.id)
        linked = 0
        for artifact, ids in grouped.items():
            self.sudo().browse(ids).write({"artifact_id": artifact})
            linked += len(ids)
        # what was linked, not what was looked at: a document whose artifact is not in
        # the registry stays unlinked, and saying otherwise would hide that
        return linked

    @api.model
    def _book_kinds(self):
        """The kinds that are bound from other documents rather than printed alone."""
        return {"book"}

    def _report_ids(self):
        """The documents the report prints for this one: itself, or a book's parts."""
        self.ensure_one()
        if self.kind in self._book_kinds():
            return [self.id] + [part.id for part in self._book_parts()]
        return self.ids

    def _book_parts(self):
        """Every document this book binds, in the order the tree walks them.

        Read in one search and indexed, rather than asked for one at a time: a book of
        the financial model binds some seventy documents, and _get() is a search each.
        """
        self.ensure_one()
        Pub = self.env["azm.doc.publication"].sudo()
        company, assessment = self.company_id, self._assessment()
        existing = {}
        for pub in Pub.search([("company_id", "=", company.id),
                               ("kind", "in", ("summary", "module"))]):
            existing[(pub.kind, pub.module_id.id, pub.tab)] = pub
        parts = [existing.get(("summary", False, False)) or Pub._get(company, "summary")]
        for module in self.env["azm.fin.module"].sudo().search([]):
            for tab in module._azm_outputs():
                part = (existing.get(("module", module.id, tab))
                        or Pub._get(company, "module", module=module, tab=tab))
                if not part._is_empty(assessment):
                    parts.append(part)
        return parts

    def _source_vals(self, assessment):
        """Which field records the assessment a document was built from."""
        self.ensure_one()
        return {"assessment_id": assessment.id}

    def _folder_key(self):
        """(folder key, sub-folder) the document is filed under, for azm.doc.folder._folder()."""
        self.ensure_one()
        if self.kind in self._book_kinds():
            return "RPT", None
        if self.kind == "requirement":
            module = self.requirement_id.module_id
            return "FIN", (module.code, f"FIN.{module.code} · {module.name}")
        if self.kind == "module":
            return MODULE_OUTPUTS[self.tab][0], None
        return "RPT", None

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

    def _book_cover(self, parts, source):
        """The front of a book: what it is, for whom, and how much of it there is."""
        self.ensure_one()
        company = self.company_id
        return {
            "doc_type": ("كتاب النموذج المالي الموحد", "Unified financial model book"),
            "code": "FIN-BOOK",
            "title": f"النموذج المالي الموحد — {company.name}",
            "path": [("النموذج", "FIN", "النموذج المالي الموحد"),
                     ("الكتاب", "FIN-BOOK", "الكتاب الكامل")],
            "glance": [
                ("الكيان", "Entity", company.name),
                ("المصدر", "Source", source),
                ("عدد المستندات", "Documents", str(len(parts))),
                ("تاريخ التجميع", "Bound on", fields.Date.to_string(fields.Date.today())),
            ],
            "summary_title": ("محتويات الكتاب", "Contents"),
            "summary_label": "المستند",
        }

    def _azm_payload_extra(self, assessment, source):
        """What a kind added by another model puts in the payload. Overridden there."""
        self.ensure_one()
        return {}

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
            # an output whose body is written by its own engine (a policy, a procedure,
            # a workflow drawing) hands the report ready-made HTML instead of items;
            # everything around it — cover, path, glance, banner, footer — is the same
            "html": False,
            "summary_title": ("حالة الموديولات", "Modules at a glance"),
            "summary_label": "الموديول",
            "summary_columns": [("منطبق", "applicable"), ("مكتمل", "done"), ("مطبّق", "full"),
                                ("جزئيًا", "partial"), ("غير مطبّق", "unavailable")],
        }
        if pub.kind in pub._book_kinds():
            parts = pub._book_parts()
            payload.update(pub._book_cover(parts, source))
            # the artifact knows the code; building each part's entire payload to read
            # one key of it meant rendering the whole book twice
            payload["summary"] = [{"code": part._artifact().code, "name": part.name}
                                  for part in parts]
            payload["summary_columns"] = []
            payload["single"] = False
        elif pub.kind not in ("requirement", "module", "summary"):
            payload.update(pub._azm_payload_extra(assessment, source))
        elif pub.kind == "requirement":
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
        # The registry asks every controlled PDF to carry a code, a version, a status
        # and a scope. The code identifies the master artifact — the same for every
        # entity — so the entity is the scope beside it, never part of it.
        artifact = pub._artifact()
        stage = pub._lifecycle()
        payload.update({
            # what this entity's copy is called, with the group's master beside it
            "code": pub._scoped_code() or artifact.code,
            "master_code": artifact.code,
            "azm_type": TYPE_LABELS.get(artifact.atype, ("", "")),
            "status": LIFECYCLE_LABELS.get(stage, ("", "")),
            "stage": stage,
            "scope": company.name,
            "version": assessment.version if assessment else 0,
            "tree_ref": pub._tree_ref(),   # how the tree names it, for the reader
        })
        payload["verify"] = " · ".join(x for x in (
            payload["code"],
            artifact.code if payload["code"] != artifact.code else "",
            payload["entity_code"] or company.name,
            f"v{assessment.version}" if assessment else "",
            stage,
        ) if x)
        # module outputs group their requirements under their topic: model › module › topic › requirement
        groups = []
        for item in payload["items"]:
            if not groups or groups[-1]["code"] != item["topic_code"]:
                groups.append({"code": item["topic_code"], "name": item["topic"], "items": []})
            groups[-1]["items"].append(item)
        payload["groups"] = groups
        # the canonical code is the identity; the tree reference is how a reader finds
        # it again in the tree, so both are on the page
        glance = payload["glance"] + [
            ("مرجع الشجرة", "Tree reference", payload["tree_ref"]),
            ("المرحلة", "Lifecycle", f"{payload['stage']} · {payload['status'][1]}"),
        ]
        payload["glance"] = glance
        payload["glance_rows"] = [glance[i:i + 2] for i in range(0, len(glance), 2)]
        return payload


class AzmFinModule(models.Model):
    _inherit = "azm.fin.module"

    def _azm_outputs(self):
        """The outputs this module can ever have, whatever any entity answers.

        A module with no requirement of a kind has nothing to say in that output for
        anybody: FIN.GOV holds no procedure, so there is no procedure of FIN.GOV to
        number, to offer on the tree, or to count. Gaps and target direction are not
        filtered that way — any requirement can turn into either — so a module with
        requirements at all can have both.
        """
        self.ensure_one()
        profiles = set(self.requirement_ids.mapped("profile"))
        return [tab for tab in MODULE_OUTPUTS
                if profiles and (tab not in fin_engine.TAB_PROFILES
                                 or profiles & set(fin_engine.TAB_PROFILES[tab]))]


class AzmFinRequirement(models.Model):
    _inherit = "azm.fin.requirement"

    azm_doc_ids = fields.One2many("azm.doc.publication", "requirement_id", string="المستندات")

    def action_azm_publish_documents(self):
        """(Re)build this requirement's document for the entities the user works in."""
        self.check_access("read")
        Pub = self.env["azm.doc.publication"]
        # env.companies, not every company there is: this writes documents into each
        # entity's workspace, and it was reaching entities the user cannot even see
        companies = self.env.companies
        for req in self:
            for company in companies:
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
