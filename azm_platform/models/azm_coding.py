"""The group's coding, taken from AZM Master Coding Registry v2.1.

The registry is the authority on how anything the group produces is identified:

    Canonical ID   AZM-<DOMAIN>-<TYPE>-<SERIAL>   — entity, system, version and
                   lifecycle stage are *separate* from the identity, never part of it.
    Tree           Model → Module → Sub-module → Process/Topic → Requirement.
    Artifacts      0..N of every output type per process; store once, map many.
    Lifecycle      CS → GR → TD → SF → IMP → UAT → GLA → CA.
    Entities       one master artifact, with applicability per entity.
    PDF            a controlled bilingual PDF carrying code, version, status and scope.

So an artifact is registered once for the node it belongs to — the policy of FIN.GOV is
AZM-FIN-POL-000001 for the whole group — and each entity's copy of it is the same
artifact at a scope, not a document of its own. That is what azm.artifact holds, and
what every document prints on its cover.
"""
from odoo import api, fields, models

CANONICAL = "AZM-{domain}-{atype}-{serial:06d}"

# The models the group codes for. HRF requirements are numbered inside FIN, exactly as
# the registry numbers them (167 = 107 FIN + 60 HRF, all AZM-FIN-REQ-…).
DOMAINS = [
    ("FIN", "النموذج المالي الموحد", "Unified Financial Model"),
    ("PUR", "دورة المشتريات", "Procurement Cycle"),
]

# Lifecycle / دورة الحياة — a stage an artifact is in, never part of its identity.
LIFECYCLE = [
    ("CS", "الوضع الحالي", "Current State"),
    ("GR", "الفجوات والمخاطر", "Gap & Risk"),
    ("TD", "التصميم المستهدف", "Target Design"),
    ("SF", "ملاءمة الحل", "Solution Fit"),
    ("IMP", "التنفيذ", "Implementation"),
    ("UAT", "الاختبار والقبول", "User Acceptance Testing"),
    ("GLA", "الإطلاق والتبني", "Go-Live & Adoption"),
    ("CA", "الضمان المستمر", "Continuous Assurance"),
]

# Artifact Type Dictionary / قاموس أنواع المخرجات — the complete registry dictionary.
ARTIFACT_TYPES = [
    ("GOV", "حوكمة", "Governance"),
    ("POL", "سياسة", "Policy"),
    ("PRO", "إجراء", "Procedure"),
    ("WFL", "مسار عمل", "Workflow"),
    ("RACI", "مصفوفة أدوار ومسؤوليات", "RACI Matrix"),
    ("DOA", "مصفوفة صلاحيات", "Delegation of Authority"),
    ("CTL", "ضابط", "Control"),
    ("BRL", "قاعدة أعمال", "Business Rule"),
    ("FRM", "نموذج", "Form"),
    ("KPI", "مؤشر أداء رئيسي", "Key Performance Indicator"),
    ("KRI", "مؤشر مخاطر رئيسي", "Key Risk Indicator"),
    ("DSH", "لوحة متابعة", "Dashboard"),
    ("RPT", "تقرير", "Report"),
    ("SRQ", "متطلب نظام", "System Requirement"),
    ("UC", "حالة استخدام", "Use Case"),
    ("EVD", "دليل", "Evidence"),
    ("GAP", "فجوة", "Gap"),
    ("RSK", "خطر", "Risk"),
    ("DEC", "قرار", "Decision"),
    ("FIT", "تقييم ملاءمة حل", "Solution Fit Assessment"),
    ("IMP", "حزمة تنفيذ", "Implementation Work Package"),
    ("CHG", "طلب تغيير", "Change Request"),
    ("TST", "حالة اختبار", "Test Case"),
    ("DEF", "عيب", "Defect"),
    ("ACC", "قبول", "Acceptance"),
    ("DEP", "نشر", "Deployment"),
    ("TRG", "تدريب", "Training"),
    ("ADP", "تبني", "Adoption Action"),
    ("FND", "ملاحظة ضمان", "Assurance Finding"),
    ("CAP", "إجراء تصحيحي", "Corrective Action"),
    ("MAN", "دليل تشغيلي / مجموعة", "Manual / Collection"),
    # The registry has no type for a requirement itself; it numbers them AZM-FIN-REQ-…,
    # so REQ is carried here as the type those canonical IDs already use.
    ("REQ", "متطلب", "Requirement"),
]
TYPE_LABELS = {code: (arabic, english) for code, arabic, english in ARTIFACT_TYPES}
LIFECYCLE_LABELS = {code: (arabic, english) for code, arabic, english in LIFECYCLE}

# Canonical module IDs, as the registry assigns them. They are *not* derivable from our
# own ordering — the registry puts INV before PUR and we do not — so they are taken from
# the file rather than computed.
MODULE_IDS = {
    "GOV": "AZM-FIN-MOD-000001", "GLD": "AZM-FIN-MOD-000002", "BUD": "AZM-FIN-MOD-000003",
    "REV": "AZM-FIN-MOD-000004", "INV": "AZM-FIN-MOD-000005", "PUR": "AZM-FIN-MOD-000006",
    "TRY": "AZM-FIN-MOD-000007", "ADV": "AZM-FIN-MOD-000008", "AST": "AZM-FIN-MOD-000009",
    "PAY": "AZM-FIN-MOD-000010", "PRJ": "AZM-FIN-MOD-000011", "CON": "AZM-FIN-MOD-000012",
    "REA": "AZM-FIN-MOD-000013", "FND": "AZM-FIN-MOD-000014", "TAX": "AZM-FIN-MOD-000015",
    "CLS": "AZM-FIN-MOD-000016", "ICO": "AZM-FIN-MOD-000017", "RPT": "AZM-FIN-MOD-000018",
    "DAT": "AZM-FIN-MOD-000019",
}


class AzmArtifact(models.Model):
    """One master artifact of the group, registered once and mapped to many entities.

    The registry's first rule is that identity carries no entity, no version and no
    lifecycle stage. So the policy of a module is one artifact with one code, and the
    nine entities that have a copy of it share that code; what differs between them is
    scope, which the document prints beside the code rather than inside it.
    """
    _name = "azm.artifact"
    _description = "AZM master artifact"
    _order = "domain, atype, serial"
    _rec_name = "code"

    code = fields.Char("الكود المعتمد", required=True, index=True, readonly=True)
    ref = fields.Char("مرجع العقدة", required=True, index=True, readonly=True,
                      help="ما يُرقَّم: عقدة في الشجرة ومخرجها، أو مستند على مستوى النموذج.")
    domain = fields.Selection([(d, f"{ar} · {en}") for d, ar, en in DOMAINS],
                              "النموذج", required=True, readonly=True)
    atype = fields.Selection([(c, f"{ar} · {en}") for c, ar, en in ARTIFACT_TYPES],
                             "نوع المخرج", required=True, readonly=True)
    serial = fields.Integer("المسلسل", required=True, readonly=True)
    node_name = fields.Char("اسم العقدة", readonly=True)

    _code_uniq = models.Constraint("UNIQUE(code)", "هذا الكود مسجل بالفعل.")
    _ref_uniq = models.Constraint("UNIQUE(ref)", "هذه العقدة لها كود مسجل بالفعل.")

    @api.model
    def _find(self, ref):
        """The artifact registered under ``ref``, or an empty recordset.

        Reading must never number anything: a compute field, a report and a read-only
        request all ask what a document is called, and allocating a serial there writes
        to the database — which a read-only cursor refuses and a reader should not do.
        """
        return self.sudo().search([("ref", "=", ref)], limit=1)

    @api.model
    def _of(self, ref, domain, atype, name="", code=None):
        """The artifact registered under ``ref``, numbered the first time it is seen.

        The serial is allocated once and then never moves: the registry keeps approved
        history immutable, so adding a module must not renumber the ones after it. A
        ``code`` that the registry already assigned — every requirement has one — is
        taken as given rather than allocated again.
        """
        Artifact = self.sudo()
        found = Artifact.search([("ref", "=", ref)], limit=1)
        if found:
            return found
        # Take the lock before deciding to create. Without it two transactions asking
        # for the same unregistered ref both miss the search above, both allocate, and
        # the second dies on _ref_uniq — so the search is repeated under the lock.
        self.env.cr.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",
                            (f"azm.artifact:{domain}:{atype}",))
        found = Artifact.search([("ref", "=", ref)], limit=1)
        if found:
            return found
        if code:
            serial = int(code.rsplit("-", 1)[-1]) if code.rsplit("-", 1)[-1].isdigit() else 0
        else:
            # the next serial of this domain and type, read under the lock taken above
            self.env.cr.execute(
                "SELECT COALESCE(MAX(serial), 0) FROM azm_artifact "
                "WHERE domain = %s AND atype = %s", (domain, atype))
            serial = self.env.cr.fetchone()[0] + 1
            code = CANONICAL.format(domain=domain, atype=atype, serial=serial)
        return Artifact.create({
            "code": code, "ref": ref, "domain": domain, "atype": atype,
            "serial": serial, "node_name": name,
        })


    @api.model
    def _register_all(self, reset=False):
        """Number every artifact of the group, in the order the registry puts them.

        A serial allocated the first time somebody happens to open a document follows
        the reader, not the model: the policy of whichever module was read first would
        be POL-000001. So the whole catalogue is walked in its own order — modules by
        the canonical ID the registry gave them, then their outputs, then the leaves,
        then the documents that belong to the model as a whole — and each artifact is
        numbered where it falls. Once numbered it never moves; a module added later
        takes the next serial rather than displacing anyone.
        """
        from .azm_documents import FIN_ARTIFACTS, FIN_KIND_ARTIFACTS, MODULE_OUTPUTS
        from .azm_proc_documents import (
            PROC_ARTIFACTS, PROC_KIND_ARTIFACTS, PROC_OUTPUTS, PROC_TAB_ORDER)
        if reset:
            self.sudo().search([]).unlink()

        env = self.env
        plan = []   # (ref, domain, atype, name, code)

        # the financial model: its modules in the registry's own order, each with its
        # outputs, then every requirement under the ID the registry already gave it
        modules = env["azm.fin.module"].sudo().search([])
        for module in modules.sorted(lambda m: (m.azm_code or "ZZZ", m.sequence, m.id)):
            # only the outputs this module can ever fill: an output a module has no
            # requirements for is not an artifact, so it takes no number
            for tab in module._azm_outputs():
                plan.append((f"azm.fin.module,{module.id},{tab}", "FIN", FIN_ARTIFACTS[tab][0],
                             f"FIN.{module.code} · {MODULE_OUTPUTS[tab][1]}", None))
        for req in env["azm.fin.requirement"].sudo().search([], order="tree_ref, id"):
            plan.append((f"azm.fin.requirement,{req.id}", "FIN", "REQ", req.title, req.req_id or None))
        for kind, (atype, _stage) in FIN_KIND_ARTIFACTS.items():
            if kind != "requirement":
                plan.append((f"fin:{kind}", "FIN", atype, kind, None))

        # the cycle: its stages in order, each with its outputs, then every question
        for stage in env["azm.stage"].sudo().search([]):
            # likewise: an output a stage cannot have is not an artifact
            for tab in stage._azm_outputs():
                plan.append((f"azm.stage,{stage.id},{tab}", "PUR", PROC_ARTIFACTS[tab][0],
                             f"PUR-{stage.code} · {PROC_OUTPUTS[tab][1]}", None))
        for question in env["azm.question"].sudo().search([], order="stage_sequence, sequence, id"):
            plan.append((f"azm.question,{question.id}", "PUR", "REQ", question.label, None))
        for kind, (atype, _stage) in PROC_KIND_ARTIFACTS.items():
            if kind != "question":
                plan.append((f"pur:{kind}", "PUR", atype, kind, None))

        for ref, domain, atype, name, code in plan:
            self._of(ref, domain, atype, name=name, code=code)
        return len(plan)


class AzmFinModule(models.Model):
    _inherit = "azm.fin.module"

    azm_code = fields.Char("الكود المعتمد", compute="_compute_azm_code", store=True,
                           help="المعرّف المعتمد في سجل الترميز الرئيسي.")

    @api.depends("code")
    def _compute_azm_code(self):
        for module in self:
            module.azm_code = MODULE_IDS.get(module.code or "", False)
