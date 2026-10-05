import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { KeepLast } from "@web/core/utils/concurrency";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { closeDocument, deliver, openDocument, previewDocument } from "@azm_platform/components/doc_preview";

/**
 * AZM Platform · the outputs library.
 *
 * The trees read one model for one entity. This reads the other way round — one
 * deliverable across every entity — which is the question the trees cannot answer:
 * how many of our entities have a procurement policy, and which ones are missing it.
 *
 * A deliverable appears once however many entities hold a copy; the bar on its row is
 * how many of them have theirs. Opening a row names them, and each can be read in place
 * or downloaded.
 */
export class AzmOutputsLibrary extends Component {
    static template = "azm_platform.OutputsLibrary";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.keepRows = new KeepLast();
        this.keepPreview = new KeepLast();
        this.scope = 0;          // bumped whenever the entities being counted change
        this.state = proxy({
            loaded: false,
            data: null,
            error: "",
            preview: null,
            open: {},            // artifact id → its entities are showing
            entities: {},        // artifact id → the rows for them
            filters: { atype: null, domain: null, stage: null, node: null,
                       approval: null, query: "", sheets: false, company_ids: [] },
        });
        onWillStart(async () => {
            await this.load();
        });
    }

    get d() {
        return this.state.data;
    }

    /**
     * The chips follow what was actually counted, not what was asked for.
     *
     * The entity filter only ever narrows: an id the reader does not work in is
     * dropped on the way in and the library is read across all of theirs instead. The
     * client holds its own copy of the filters, so without this the rail would go on
     * showing one entity lit while the figures beside it were the whole group's.
     * Picking every chip is the same as picking none, and settles to none.
     */
    adoptEntities() {
        const counted = (this.d && this.d.filters && this.d.filters.company_ids) || [];
        const offered = ((this.d && this.d.entity_options) || []).map((e) => e.id);
        const asked = this.state.filters.company_ids;
        const kept = asked.filter((id) => counted.includes(id));
        const settled = kept.length === offered.length ? [] : kept;
        if (settled.length !== asked.length || settled.some((id, i) => id !== asked[i])) {
            this.state.filters.company_ids = settled;
        }
    }

    /** The library is read across entities, so a document says which one it is for. */
    get previewCompanyId() {
        return this.state.filters.company_ids[0] || null;
    }

    async load() {
        this.state.loaded = false;
        this.state.error = "";
        try {
            this.state.data = await this.keepRows.add(
                this.orm.call("azm.dashboard", "get_outputs_library", [], {
                    ...this.state.filters,
                    company_ids: this.state.filters.company_ids.length
                        ? this.state.filters.company_ids : null,
                })
            );
            this.adoptEntities();
        } catch (error) {
            this.state.data = null;
            this.state.error = (error && error.data && error.data.message)
                || (error && error.message) || "تعذّر تحميل المكتبة.";
        } finally {
            this.state.loaded = true;
        }
    }

    // ---------------------------------------------------------------- filtering
    /** Picking the filter already on turns it off, so a chip is its own undo. */
    async setFilter(key, value) {
        this.state.filters[key] = this.state.filters[key] === value ? null : value;
        this.forgetRows();
        await this.load();
    }

    async setQuery(value) {
        this.state.filters.query = value;
        await this.load();
    }

    async toggleSheets() {
        this.state.filters.sheets = !this.state.filters.sheets;
        await this.load();
    }

    /** Entities are a set: a library of nine entities is read a few at a time. */
    async toggleEntity(id) {
        const chosen = this.state.filters.company_ids;
        this.state.filters.company_ids = chosen.includes(id)
            ? chosen.filter((x) => x !== id)
            : [...chosen, id];
        this.forgetRows();
        await this.load();
    }

    /** Whether this entity is one of the picked ones. With none picked the library is
     *  read across all of them, which is not the same as all of them being picked: a
     *  chip that drew itself as "on" there was offering to switch itself off and in
     *  fact switched every other one off. */
    isEntityOn(id) {
        return this.state.filters.company_ids.includes(id);
    }

    /** No entity picked: the rail reads across all of them, and says so rather than
     *  lighting every chip. */
    get allEntities() {
        return this.state.filters.company_ids.length === 0;
    }

    get filtering() {
        const f = this.state.filters;
        return !!(f.atype || f.domain || f.stage || f.node || f.approval || f.query
                  || f.company_ids.length);
    }

    async clearFilters() {
        this.state.filters = { atype: null, domain: null, stage: null, node: null,
                               approval: null, query: "",
                               sheets: this.state.filters.sheets, company_ids: [] };
        this.forgetRows();
        await this.load();
    }

    /** The entities of an open row were read for the scope that was in force; a filter
     *  that changes the scope has to forget them, or the row answers for the old one.
     *
     *  Clearing the cache is not enough on its own: a lookup already in flight resolves
     *  afterwards and writes its answer into the fresh cache. So the scope carries a
     *  number, and a reply is only kept if the scope it was asked under is still the
     *  one in force. */
    forgetRows() {
        this.state.open = {};
        this.state.entities = {};
        this.scope += 1;
    }

    // ---------------------------------------------------------------- a deliverable
    isOpen(id) {
        return !!this.state.open[id];
    }

    async toggleRow(row) {
        if (this.state.open[row.id]) {
            this.state.open[row.id] = false;
            return;
        }
        this.state.open[row.id] = true;
        if (!this.state.entities[row.id]) {
            const asked = this.scope;
            try {
                const found = await this.orm.call("azm.dashboard", "get_output_entities", [], {
                    artifact_id: row.id,
                    company_ids: this.state.filters.company_ids.length
                        ? this.state.filters.company_ids : null,
                });
                if (asked === this.scope) {
                    this.state.entities[row.id] = found.rows || [];
                }
            } catch {
                if (asked === this.scope) {
                    this.state.entities[row.id] = [];
                }
            }
        }
    }

    entitiesOf(row) {
        return this.state.entities[row.id] || [];
    }

    coverage(row) {
        return row.entities ? Math.round((100 * row.ready) / row.entities) : 0;
    }

    // ---------------------------------------------------------------- reading
    async previewDoc(doc) {
        await previewDocument(this, doc);
    }

    closePreview() {
        closeDocument(this);
    }

    async openDoc(doc, download = false) {
        await openDocument(this, doc, download);
    }

    /** The whole model of one entity, bound as one PDF. */
    async book(companyId, domain) {
        await openDocument(this, {
            kind: domain === "PUR" ? "cycle_book" : "book",
            company_id: companyId,
            label: "الكتاب الكامل",
        }, true);
    }

    /**
     * Find this deliverable on the tree it belongs to.
     *
     * "Show it on the tree" has to show *it*, and on whose tree. Handing the tree only
     * the entity opened the model at the top and left the reader to find the branch
     * again by hand — the search they had just done here — and the row offered one
     * button for nine entities, so it opened whichever the filter happened to leave.
     * Each entity now has its own, and it lands on the branch with the output showing.
     */
    openTree(row, companyId = null) {
        const doc = row.doc || {};
        this.action.doAction(
            row.domain === "PUR" ? "azm_platform.action_azm_proc_tree"
                                 : "azm_platform.action_azm_fin_tree",
            { additionalContext: {
                azm_company_id: companyId || this.previewCompanyId || undefined,
                azm_node_id: doc.id || undefined,
                azm_family: doc.tab || undefined,
            } }
        );
    }

    // ---------------------------------------------------------------- binding a manual
    /**
     * What a "combine these into one document" would bind, or null.
     *
     * A manual is one kind of deliverable for one entity, so both have to be settled
     * before the button means anything: all the policies of whom? The model filter
     * rides along when it is on, which is how you get the procurement policies alone
     * rather than every policy the group has.
     */
    get combining() {
        const filters = this.state.filters;
        const type = filters.atype
            && (this.d.types || []).find((t) => t.key === filters.atype);
        if (!type) {
            return null;
        }
        const only = filters.company_ids.length === 1 ? filters.company_ids[0] : null;
        const entity = only
            && (this.d.entity_options || []).find((e) => e.id === only);
        return { type, entity: entity || null };
    }

    get combineLabel() {
        const what = this.combining;
        return what ? `اجمع ${what.type.label} في مستند واحد` : "";
    }

    get combineHint() {
        const what = this.combining;
        if (!what) {
            return "";
        }
        return what.entity
            ? `${what.type.count} مستند · ${what.entity.name}`
            : "اختر كيانًا واحدًا من الأعلى";
    }

    async combineOutputs() {
        const what = this.combining;
        if (!what || !what.entity) {
            return;
        }
        // the dialog an empty manual raises says which entity has nothing to bind,
        // which is the answer to the question the button asks
        const action = await this.orm.call("azm.dashboard", "open_outputs_book", [], {
            atype: what.type.key,
            company_id: what.entity.id,
            domain: this.state.filters.domain || null,
            download: true,
        });
        // binding a manual takes a moment, and doAction would be asking for a window
        // long after the click that earned one
        deliver(this, action, true);
    }

    get kpis() {
        const t = this.d.totals;
        return [
            { key: "deliverables", label: "المخرجات", en: "Deliverables", value: t.deliverables,
                icon: "inventory_2", tone: "indigo", sub: `${t.types} نوعًا من المخرجات` },
            { key: "ready", label: "نسخ جاهزة", en: "Copies ready", value: t.ready,
                icon: "task_alt", tone: "green", sub: `من ${t.copies} نسخة لدى الكيانات` },
            // a file being ready and the answers behind it being approved are two
            // different things, and the second is what counts as issued
            { key: "approved", label: "نسخ معتمدة", en: "Approved copies", value: t.approved,
                icon: "verified", tone: "teal",
                sub: t.unissued ? `${t.unissued} لم تُعتمد بعد` : "كلها معتمدة" },
            { key: "entities", label: "الكيانات", en: "Entities", value: t.entities,
                icon: "business", tone: "slate", sub: "تُحسب التغطية عليها" },
        ];
    }
}

registry.category("actions").add("azm_outputs_library", AzmOutputsLibrary);
