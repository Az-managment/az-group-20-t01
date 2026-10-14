"""The group's coding, taken from AZM Master Coding Registry v2.1.

The registry is the authority on how anything the group produces is identified:

    Canonical ID   AZM-<DOMAIN>-<TYPE>-<SERIAL>   — entity, system, version and
                   lifecycle stage are *separate* from the identity, never part of it.
    Tree           Model → Module → Sub-module → Process/Topic → Requirement.
    Artifacts      0..N of every output type per process; store once, map many.
    Lifecycle      CS → GR → TD → SF → IMP → UAT → GLA → CA.
    Entities       one master artifact, with applicability per entity.
    PDF            a controlled bilingual PDF carrying code, version, status and scope.

So an artifact is registered once for the node it belongs to — and each entity's copy of
it is the same artifact at a scope, not a document of its own. That is what azm.artifact
holds, and what every document prints on its cover.

The serial runs straight through the model and the type, and the node is a field beside
it rather than part of it. That is the registry's own rule and it has a reason: *one
artifact may map to many nodes without copies*, which a code naming one node forbids.

What the registry does say about nodes is that there are **0..N of every output type per
process**. FIN.GOV has three policies — financial periods, activity oversight, additional
cases — and the old reading, one policy document per module, collapsed them into one
code that stood for all three. Each of them is its own policy, its own document and its
own code:

    AZM-FIN-POL-000001   FIN.GOV · الفترات المالية
    AZM-FIN-POL-000002   FIN.GOV · رقابة النشاط
    AZM-FIN-POL-000003   FIN.GOV · حالات إضافية

Which deliverable a requirement is comes from its answer profile — P/C/L are policy,
W procedure, A authority, R reporting, I system requirement — so the thing somebody
answers and the thing the group issues are the same thing under two names, rather than
a page about a policy filed next to the policy.

Where an entity falls short of a requirement, and where it means to take it, are
deliverables of that requirement too — each in its own document and under its own code.
A module still has a gap register and a target direction, and they are compilations of
those: bound from the deliverables under them, carrying no code of their own, exactly as
a module's compiled policy is a binding of its policies.

That is the rule, and it is the only rule: **every module-level document is a binding,
every requirement-level document is a deliverable.**
"""
from odoo import api, fields, models

CANONICAL = "AZM-{domain}-{atype}-{serial:06d}"
# Who holds the master register. The serial is assigned once, here, and every entity
# that holds the artifact holds that same serial.
HOLDER = "AZM"
# what stands in for the node on the documents that belong to a whole model
WHOLE_MODEL = "ALL"


def copy_code(master, entity_code):
    """The code an entity's copy of ``master`` prints.

    The registry numbers an artifact once, as AZM-FIN-POL-000001, and the entities it
    applies to all hold that same number — the serial names the artifact, not the copy.
    What differs is whose copy a document is, so the copy leads with the entity and
    keeps the rest of the master intact: FUE-FIN-POL-000001 beside AZM-FIN-POL-000001.

    Without an entity to name there is no copy to name either, so the master stands.
    """
    if not master:
        return ""
    if not entity_code:
        return master
    domain_type_serial = master.split("-", 1)[1] if "-" in master else master
    return f"{entity_code}-{domain_type_serial}"

# Which deliverable a financial requirement *is*, from the profile it is answered under.
# The engine already groups the module's outputs this way (fin_engine.TAB_PROFILES);
# this is the same mapping read the other way round, one requirement at a time, because
# the deliverable is the requirement and not the group of them.
PROFILE_OUTPUT = {
    "P": "rules", "C": "rules", "L": "rules",   # policy, control, legal → a policy
    "W": "workflow",                            # → a procedure
    "A": "authority",                           # → an authority
    "R": "reports",                             # → a report
    "I": "integration",                         # → a system requirement
}

# What a single requirement produces, beyond the deliverable it is: where this entity
# falls short of it, and where it intends to take it. Both belong to the requirement and
# not to the module — FIN.GOV's gap register carried one code over five gaps, which is
# the same thing as a policy document carrying one code over three policies.
REQUIREMENT_ASPECTS = ("gaps", "future")

# the profile-driven outputs, in the order a module's deliverables are read
PROFILE_TABS = ("rules", "workflow", "authority", "reports", "integration")

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
    node = fields.Char("العقدة", required=True, readonly=True, index=True,
                       default=WHOLE_MODEL,
                       help="الموديول أو المرحلة التي ينتمي إليها المخرج — بجوار الكود لا بداخله.")
    serial = fields.Integer("المسلسل", required=True, readonly=True)
    node_name = fields.Char("اسم العقدة", readonly=True)
    active = fields.Boolean("قيد الإنتاج", default=True, readonly=True,
                            help="المخرج الذي توقّف إنتاجه يحتفظ بكوده ولا يُعاد استخدامه.")

    # The registry's dedup rule, in the three parts it is written in: unique IDs,
    # unique *active* relationships, and a serial that belongs to one deliverable.
    #
    # The code constraint no longer has to be deferred. It was, because renumbering slid
    # a block of codes down one and a row would briefly hold the code of the row ahead
    # of it — a duplicate between statements that was gone by commit. Nothing renumbers
    # now, so a duplicate is a duplicate where it is written, and is worth refusing
    # there rather than at the end of the transaction.
    _code_uniq = models.Constraint("UNIQUE(code)", "هذا الكود مسجل بالفعل.")
    # A node is registered once per output type *while it is produced*. A deliverable
    # that retires keeps its row and its code, so its ref stays behind on an inactive
    # row — which is why this covers the active ones rather than the whole table.
    _ref_active_uniq = models.UniqueIndex("(ref, domain, atype) WHERE active",
                                          "هذه العقدة لها كود مسجل بالفعل.")
    # and a serial, once issued for a model and type, is never issued again
    _serial_uniq = models.Constraint("UNIQUE(domain, atype, serial)",
                                     "هذا المسلسل مستخدم بالفعل.")
    _serial_positive = models.Constraint("CHECK(serial > 0)", "المسلسل يبدأ من واحد.")

    @api.model
    def _find(self, ref):
        """The artifact registered under ``ref``, or an empty recordset.

        Reading must never number anything: a compute field, a report and a read-only
        request all ask what a document is called, and allocating a serial there writes
        to the database — which a read-only cursor refuses and a reader should not do.
        """
        # retired deliverables included: a document issued under a code goes on
        # printing that code after the group stops producing new ones
        return self.sudo().with_context(active_test=False).search(
            [("ref", "=", ref)], limit=1)

    @api.model
    def _of(self, ref, domain, atype, node=WHOLE_MODEL, name="", code=None):
        """The artifact registered under ``ref``, numbered the first time it is seen.

        This is the interim answer, not the registry's. It is reached when a document
        turns out to have content for a deliverable that was not numbered — the group
        has started doing something it did not do before — and it takes the next free
        serial so the document has a code to print right away. ``_register_all`` then
        puts it where the catalogue says it belongs. A ``code`` the registry already
        assigned — every requirement has one — is taken as given rather than allocated.
        """
        Artifact = self.sudo().with_context(active_test=False)
        # matched on the whole identity, because one node may produce a policy and a
        # procedure, and after a retirement it may hold a code for each
        identity = [("ref", "=", ref), ("domain", "=", domain), ("atype", "=", atype)]

        def revive(art):
            """Producing it again restores the code it already had."""
            if art and not art.active:
                art.active = True
            return art

        found = revive(Artifact.search(identity, limit=1))
        if found:
            return found
        # Take the lock before deciding to create. Without it two transactions asking
        # for the same unregistered ref both miss the search above, both allocate, and
        # the second dies on the uniqueness rule — so the search is repeated under it.
        self.env.cr.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",
                            (f"azm.artifact:{domain}:{atype}",))
        found = revive(Artifact.search(identity, limit=1))
        if found:
            return found
        # This node produced something else before and now produces this. The old
        # deliverable keeps its code and steps aside, rather than being re-typed under
        # a code whose type segment would stop describing it.
        Artifact.search([("ref", "=", ref), ("active", "=", True)]).write(
            {"active": False})
        if code:
            serial = int(code.rsplit("-", 1)[-1]) if code.rsplit("-", 1)[-1].isdigit() else 0
        else:
            # The next serial of this domain and type, read under the lock taken
            # above. Straight SQL over the table, so retired rows count: their codes
            # are spoken for and the next one goes above them, never into the gap.
            self.env.cr.execute(
                "SELECT COALESCE(MAX(serial), 0) FROM azm_artifact "
                "WHERE domain = %s AND atype = %s", (domain, atype))
            serial = self.env.cr.fetchone()[0] + 1
            code = CANONICAL.format(domain=domain, atype=atype, serial=serial)
        return Artifact.create({
            "code": code, "ref": ref, "domain": domain, "atype": atype,
            "node": node, "serial": serial, "node_name": name,
        })


    @api.model
    def _register_all(self, reset=False):
        """Number every deliverable of the group, in the order the registry puts them.

        The registry is derived, not accumulated. A code says two things and nothing
        else: where the deliverable falls in the catalogue, and that the group produces
        it at all. Both are read fresh every time this runs, so the codes are a function
        of the model and the answers rather than of the order in which somebody happened
        to open documents.

        Two rules follow from that:

        *Only what exists is numbered.* Every entity marked investments not applicable,
        so no entity has an investments policy — and AZM-FIN-POL-000005 stood for a
        document that does not exist anywhere, pushing every real policy after it up a
        place. A deliverable nothing is filed under yet is left alone: a requirement
        sheet is built when it is first read, and has something to say by definition.

        *The numbers close up.* Each type reads 000001..N with no holes, in the
        catalogue's order — modules by the canonical ID the registry gave them, then
        their outputs, then the leaves, then the documents that belong to the model as a
        whole. A deliverable that becomes real later takes its place in that order and
        the ones after it move down, which is why a document prints its code into its
        own fingerprint: the ones affected age by themselves and are rebuilt when next
        read.
        """
        from .azm_documents import FIN_ARTIFACTS, FIN_KIND_ARTIFACTS, MODULE_OUTPUTS
        from .azm_proc_documents import (
            PROC_ARTIFACTS, PROC_KIND_ARTIFACTS, PROC_OUTPUTS, PROC_TAB_ORDER)
        if reset:
            self.sudo().with_context(active_test=False).search([]).unlink()

        env = self.env
        plan = []   # (ref, domain, atype, node, name, code)

        # ---------------------------------------------------------- financial model
        # The deliverable is the individual requirement, in its own document, typed by
        # what it asks for: a policy, a procedure, an authority, a report, a system
        # requirement. The module's compiled version of all of them is a binding of
        # these rather than a deliverable beside them, so it is not numbered here.
        modules = env["azm.fin.module"].sudo().search([])
        ordered = modules.sorted(lambda m: (m.azm_code or "ZZZ", m.sequence, m.id))
        Pub = env["azm.doc.publication"]
        for module in ordered:
            requirements = module.requirement_ids.sorted(
                lambda r: (r.topic_sequence or 0, r.sequence or 0, r.id))
            # Everything a requirement produces, grouped by kind so that a module's
            # policies run 1..N before its procedures start again at one — the registry
            # is read a kind at a time, not a requirement at a time.
            for tab in (PROFILE_TABS + REQUIREMENT_ASPECTS):
                for req in requirements:
                    if tab not in Pub._requirement_tabs(req):
                        continue
                    aspect = (f" · {MODULE_OUTPUTS[tab][1]}"
                              if tab in REQUIREMENT_ASPECTS else "")
                    plan.append((f"azm.fin.requirement,{req.id},{tab}", "FIN",
                                 FIN_ARTIFACTS[tab][0], module.code,
                                 f"FIN.{module.code} · {req.title}{aspect}", None))
        for kind, (atype, _stage) in FIN_KIND_ARTIFACTS.items():
            if kind != "requirement":
                plan.append((f"fin:{kind}", "FIN", atype, WHOLE_MODEL, kind, None))

        # ---------------------------------------------------------- procurement cycle
        # A stage's outputs are written for the stage as a whole — the policy of the
        # requisition stage is one policy, not one per question — so the stage is the
        # node and its outputs are what is numbered under it.
        for stage in env["azm.stage"].sudo().search([]):
            for tab in stage._azm_outputs():
                plan.append((f"azm.stage,{stage.id},{tab}", "PUR", PROC_ARTIFACTS[tab][0],
                             stage.code, f"PUR-{stage.code} · {PROC_OUTPUTS[tab][1]}", None))
        for question in env["azm.question"].sudo().search(
                [], order="stage_sequence, sequence, id"):
            plan.append((f"azm.question,{question.id}", "PUR", "REQ",
                         question.stage_id.code, question.label, None))
        for kind, (atype, _stage) in PROC_KIND_ARTIFACTS.items():
            if kind != "question":
                plan.append((f"pur:{kind}", "PUR", atype, WHOLE_MODEL, kind, None))

        # ------------------------------------------------------------ what exists
        # The catalogue says what could be produced; the answers say what is. A ref
        # nothing has been filed under is not judged — only one whose every copy is
        # empty is dropped.
        filed, produced = env["azm.doc.publication"]._produced_refs()
        plan = [row for row in plan if row[0] not in filed or row[0] in produced]

        # ------------------------------------------------------------ the numbers
        # A code is allocated once, and is never allocated again.
        #
        # This used to renumber on every run: each type was counted from one, so the
        # catalogue read 000001..N with no holes. What that costs only shows when
        # something retires. Dropping a single policy from FIN.GOV moved 108 codes onto
        # different deliverables — AZM-FIN-POL-000003 stopped meaning "حالات إضافية"
        # and started meaning the policy after it — while every PDF already issued went
        # on carrying the old number. The registry's rule is that approved history is
        # immutable, and a code that moves underneath an issued document cannot keep it.
        #
        # So an identity that already holds a code keeps it, and only something genuinely
        # new draws a serial — from above the highest ever issued, never from the holes
        # that retirement leaves behind.
        Artifact = self.sudo().with_context(active_test=False)
        # One lock for the whole register. Two runs overlapping would each read the same
        # highest serial and hand one code to two deliverables; the per-type lock in
        # _of does not cover this, which allocates across every type at once.
        env.cr.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("azm.artifact",))

        # An artifact is what a node produces *of one type*. When a requirement changes
        # profile the old deliverable is not re-typed in place: the policy that was
        # issued stays issued under its own code, and the procedure that takes over is
        # a new deliverable with a new one.
        existing = {(art.ref, art.domain, art.atype): art for art in Artifact.search([])}
        # the highest serial ever issued per model and type, retired rows counted, so a
        # retired code can never come back attached to something else
        env.cr.execute("SELECT domain, atype, MAX(serial) FROM azm_artifact "
                       "GROUP BY domain, atype")
        highest = {(domain, atype): serial
                   for domain, atype, serial in env.cr.fetchall()}

        wanted = []
        for ref, domain, atype, node, name, code in plan:
            art = existing.get((ref, domain, atype))
            if art:
                # it has an identity already, and an identity does not move
                wanted.append((ref, domain, atype, node, name, art.code, art.serial))
                continue
            key = (domain, atype)
            serial = highest.get(key, 0) + 1
            highest[key] = serial
            wanted.append((ref, domain, atype, node, name,
                           CANONICAL.format(domain=domain, atype=atype, serial=serial),
                           serial))

        # ------------------------------------------------------------ apply
        keep = {(ref, domain, atype) for ref, domain, atype, *_rest in wanted}
        # A deliverable the group has stopped producing is retired, not deleted. The row
        # stays so the code stays spoken for, and the documents issued under it go on
        # meaning what they said. Every reader of this register filters on active, so a
        # retired artifact leaves the catalogue without leaving the record.
        retired = [art.id for identity, art in existing.items()
                   if identity not in keep and art.active]
        if retired:
            Artifact.browse(retired).write({"active": False})
        fresh = []
        for ref, domain, atype, node, name, code, serial in wanted:
            art = existing.get((ref, domain, atype))
            if not art:
                fresh.append({"code": code, "ref": ref, "domain": domain, "atype": atype,
                              "node": node, "serial": serial, "node_name": name})
                continue
            # the code and the serial are settled; what the node is called is not, and
            # producing it again brings it back under the code it already had
            vals = {field: value for field, value in
                    (("node_name", name), ("node", node), ("active", True))
                    if art[field] != value}
            if vals:
                art.write(vals)
        if fresh:
            Artifact.create(fresh)
        return len(wanted)


class AzmFinModule(models.Model):
    _inherit = "azm.fin.module"

    azm_code = fields.Char("الكود المعتمد", compute="_compute_azm_code", store=True,
                           help="المعرّف المعتمد في سجل الترميز الرئيسي.")

    @api.depends("code")
    def _compute_azm_code(self):
        for module in self:
            module.azm_code = MODULE_IDS.get(module.code or "", False)
