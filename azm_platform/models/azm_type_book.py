"""One volume of everything of a kind: all the policies, all the procedures, all the
authority matrices.

The entity book binds one model whole — every output of every branch, in tree order.
That is the right shape for "show me our financial model", and the wrong one for "give
me our policies": a policy manual is read by people who will never open a KPI sheet, and
it crosses the two models rather than following one of them down.

So this binds the other way round, the way the outputs library reads: one kind of
deliverable, every branch that has one, for one entity. It is a compilation of numbered
deliverables rather than a deliverable itself — each part carries its own registry code,
and the volume takes none.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .azm_coding import TYPE_LABELS

# the kinds worth binding: the ones a reader asks for by name. The per-requirement and
# per-question sheets are the tree's business, and there are nine hundred of them.
BINDABLE = {"POL", "PRO", "WFL", "DOA", "CTL", "KPI", "RPT", "SRQ", "GAP", "RSK",
            "DEC", "MAN"}


class AzmDocPublication(models.Model):
    _inherit = "azm.doc.publication"

    kind = fields.Selection(selection_add=[("type_book", "دليل مخرجات · Outputs manual")],
                            ondelete={"type_book": "cascade"})

    # ---------------------------------------------------------------- identity
    @api.model
    def _type_book_key(self, atype, domain=None):
        return f"typebook:{atype}:{domain or 'ALL'}"

    def _type_book_scope(self):
        """``(atype, domain)`` this volume binds, read back off its key."""
        self.ensure_one()
        parts = (self.key or "").split(":")
        atype = parts[1] if len(parts) > 1 else ""
        domain = parts[2] if len(parts) > 2 and parts[2] != "ALL" else None
        return atype, domain

    @api.model
    def _get_type_book(self, company, atype, domain=None):
        """The volume of ``atype`` for ``company``, filed the first time it is asked for.

        Not created with the rest of a company's documents: there are a dozen kinds and
        most entities will never ask for most of them, and an unasked-for volume is a
        rebuild on every answer for nobody's benefit.
        """
        if atype not in BINDABLE:
            raise UserError(_("There is no manual of this kind."))
        Pub = self.sudo()
        key = self._type_book_key(atype, domain)
        pub = Pub.search([("company_id", "=", company.id), ("key", "=", key)], limit=1)
        if not pub:
            pub = Pub.create({"company_id": company.id, "kind": "type_book", "key": key,
                              "build": "on_open"})
        return pub

    def _compute_name(self):
        """What the volume is called — and, since the file takes its name from this,
        what lands in the entity's Documents folder."""
        mine = self.filtered(lambda p: p.kind == "type_book")
        super(AzmDocPublication, self - mine)._compute_name()
        for pub in mine:
            atype, domain = pub._type_book_scope()
            arabic = TYPE_LABELS.get(atype, (atype, atype))[0]
            scope = {"FIN": "النموذج المالي الموحد", "PUR": "دورة المشتريات"}.get(
                domain, "نماذج التشغيل")
            pub.name = f"{scope} · دليل {arabic}"

    # ---------------------------------------------------------------- binding
    @api.model
    def _book_kinds(self):
        return super()._book_kinds() | {"type_book"}

    def _book_parts(self):
        """Every deliverable of this kind the entity holds, in the registry's order.

        Read through the artifact, which is what "of this kind" means: the registry
        decides that a module's `rules` output is a POL, and this follows it rather than
        keeping a second list that could disagree with it.
        """
        self.ensure_one()
        if self.kind != "type_book":
            return super()._book_parts()
        atype, domain = self._type_book_scope()
        where = [("company_id", "=", self.company_id.id),
                 ("artifact_id", "!=", False),
                 ("artifact_id.atype", "=", atype)]
        if domain:
            where.append(("artifact_id.domain", "=", domain))
        found = self.env["azm.doc.publication"].sudo().search(where)
        found = found.sorted(lambda p: (p.artifact_id.domain, p.artifact_id.serial))
        cache = self._source_cache(found)
        return [part for part in found
                if not part._is_empty(cache.get(part._source_key()))]

    def _is_empty(self, assessment):
        self.ensure_one()
        if self.kind == "type_book":
            # no summary of its own to discount: a volume with no parts is nothing
            return not self._book_parts()
        return super()._is_empty(assessment)

    def _empty_message(self):
        self.ensure_one()
        if self.kind == "type_book":
            atype, _domain = self._type_book_scope()
            return _("%(entity)s has no %(kind)s to bind yet.",
                     entity=self.company_id.name,
                     kind=TYPE_LABELS.get(atype, ("", ""))[0])
        return super()._empty_message()

    # ---------------------------------------------------------------- coding
    def _artifact_ref(self):
        """A volume is a compilation, not a deliverable, so it is not numbered.

        Its parts each carry their own registry code and print it; giving the binding a
        code of its own would put something in the registry the registry does not
        define, and the next pass over the catalogue would take it straight back out.
        """
        self.ensure_one()
        if self.kind == "type_book":
            return ""
        return super()._artifact_ref()

    def _artifact(self, create=True):
        self.ensure_one()
        if self.kind == "type_book":
            return self.env["azm.artifact"]
        return super()._artifact(create=create)

    def _lifecycle(self):
        """A manual is issued where the model book is: it is a binding of what the
        entity has now, not a step of its own in CS → GR → TD → …"""
        self.ensure_one()
        if self.kind == "type_book":
            return "CS"
        return super()._lifecycle()

    def _tree_ref(self):
        self.ensure_one()
        if self.kind == "type_book":
            _atype, domain = self._type_book_scope()
            return domain or "AZM"
        return super()._tree_ref()

    # ---------------------------------------------------------------- the cover
    def _book_cover(self, parts, source):
        self.ensure_one()
        if self.kind != "type_book":
            return super()._book_cover(parts, source)
        atype, domain = self._type_book_scope()
        arabic, english = TYPE_LABELS.get(atype, (atype, atype))
        company = self.company_id
        scope_ar = {"FIN": "النموذج المالي الموحد", "PUR": "دورة المشتريات"}.get(
            domain, "نماذج التشغيل")
        scope_en = {"FIN": "Unified financial model", "PUR": "Procurement cycle"}.get(
            domain, "Operating models")
        return {
            "doc_type": (f"دليل {arabic}", f"{english} manual"),
            "code": f"{domain or 'AZM'}-{atype}-BOOK",
            "title": f"دليل {arabic} — {company.name}",
            "path": [("النطاق", domain or "AZM", scope_ar),
                     ("الدليل", atype, f"دليل {arabic}")],
            "glance": [
                ("الكيان", "Entity", company.name),
                ("النطاق", "Scope", f"{scope_ar} · {scope_en}"),
                ("المصدر", "Source", source),
                ("عدد المستندات", "Documents", str(len(parts))),
                ("تاريخ التجميع", "Bound on", fields.Date.to_string(fields.Date.today())),
            ],
            "summary_title": (f"محتويات دليل {arabic}", f"{english} contents"),
            "summary_label": "المستند",
        }
