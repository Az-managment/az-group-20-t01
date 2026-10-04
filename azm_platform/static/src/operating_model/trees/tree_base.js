import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { pct } from "../om_utils";

/**
 * AZM Platform · the shell every tree page shares.
 *
 * A tree is a model read from its catalogue down to its leaf — three levels, the same
 * three everywhere — with one entity's own answers hung on it. What changes between
 * the financial model and the procurement cycle is what a leaf *is*, so only the
 * detail panel is written twice; walking, searching, folding and picking the entity
 * live here, and the tree panel itself is one template (azm_platform.TreePanel).
 *
 * A subclass gives its template, the two model methods and the name of the argument
 * that carries a leaf's id.
 */
export class AzmTreePage extends Component {
    static dataMethod = "";   // azm.dashboard method returning the whole tree
    static nodeMethod = "";   // ... and the one returning a single leaf
    static nodeArg = "id";    // what that method calls the leaf's id

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.pct = pct;
        this.state = proxy({
            loaded: false,
            data: null,
            open: {},          // "n-3" / "c-12" → expanded
            docs: {},          // branch id → its outputs are showing
            selected: null,    // leaf id
            node: null,        // its detail
            loadingNode: false,
            query: "",
            preview: null,     // the document being read in place, if any
            family: null,      // only this family of outputs is showing, if any
        });
        // the Trees page opens a card by handing us its entity
        const context = this.props.action.context || {};
        onWillStart(async () => {
            await this.load(context.azm_company_id || null);
        });
    }

    /** Extra arguments a subclass sends with every call (an assessment, a filter…). */
    get extra() {
        return {};
    }

    /** What the header says. A subclass names its own model. */
    get pageTitle() {
        return "";
    }
    get pageTitleEn() {
        return "";
    }
    get pageSubtitle() {
        return "";
    }
    get panelTitle() {
        return "الشجرة";
    }
    get searchHint() {
        return "ابحث بالكود أو العنوان…";
    }

    /** The selects in the header. Which entity the tree is read for is always one. */
    get selects() {
        return [{
            key: "company",
            title: "الكيان",
            value: this.d.company.id,
            options: this.d.entity_options,
        }];
    }

    async onSelectChange(key, ev) {
        if (key === "company") {
            await this.load(parseInt(ev.target.value, 10));
        }
    }

    async load(companyId = null, extra = {}) {
        this.state.loaded = false;
        this.state.selected = null;
        this.state.node = null;
        this.state.preview = null;
        this.state.family = null;
        this.state.docs = {};
        this.state.data = await this.orm.call("azm.dashboard", this.constructor.dataMethod, [], {
            company_id: companyId,
            ...extra,
        });
        this.state.loaded = true;
        // open the first node so the page never greets anyone with a wall of closed rows
        const first = this.nodes[0];
        if (first) {
            this.state.open[`n-${first.id}`] = true;
        }
    }

    get d() {
        return this.state.data;
    }

    get nodes() {
        return (this.d && this.d.nodes) || [];
    }

    /** The tree, narrowed to what the search box matches (code, title or branch name). */
    get tree() {
        const q = this.state.query.trim().toLowerCase();
        if (!q) {
            return this.nodes;
        }
        const hit = (text) => (text || "").toLowerCase().includes(q);
        return this.nodes
            .map((n) => {
                const children = n.children
                    .map((c) => {
                        const items = c.items.filter(
                            (i) => hit(i.code) || hit(i.title) || hit(c.name) || hit(c.code)
                        );
                        return items.length ? { ...c, items } : null;
                    })
                    .filter(Boolean);
                const match = hit(n.code) || hit(n.name);
                if (match && !children.length) {
                    return n;
                }
                return children.length ? { ...n, children } : null;
            })
            .filter(Boolean);
    }

    get searching() {
        return !!this.state.query.trim();
    }

    isOpen(kind, id) {
        return this.searching || !!this.state.open[`${kind}-${id}`];
    }

    toggle(kind, id) {
        if (this.searching) {
            return;
        }
        this.state.open[`${kind}-${id}`] = !this.state.open[`${kind}-${id}`];
    }

    expandAll() {
        for (const n of this.nodes) {
            this.state.open[`n-${n.id}`] = true;
            for (const c of n.children) {
                this.state.open[`c-${c.id}`] = true;
            }
        }
    }

    collapseAll() {
        this.state.open = {};
        this.state.docs = {};
        this.state.family = null;
    }

    /** Whether the documents on offer would say what the page says. */
    get docsAvailable() {
        return true;
    }

    /** Why they are not on offer, when they are not. */
    get docsNote() {
        return "";
    }

    async select(item) {
        this.state.selected = item.id;
        this.state.preview = null;
        this.state.loadingNode = true;
        try {
            this.state.node = await this.orm.call("azm.dashboard", this.constructor.nodeMethod, [], {
                [this.constructor.nodeArg]: item.id,
                company_id: this.d.company.id,
                ...this.extra,
            });
        } finally {
            this.state.loadingNode = false;
        }
    }

    /** The outputs of a branch — policy, procedure, authority, KPIs … — folded away
     *  until asked for, so the tree stays a tree. */
    docsOpen(id) {
        return !!this.state.docs[id];
    }

    toggleDocs(id) {
        this.state.docs[id] = !this.state.docs[id];
    }

    /**
     * Open (or download) the document a node stands for.
     *
     * The tree offers every output the catalogue defines, published or not; the
     * server resolves the document and builds it if this is the first time anyone
     * has asked to read it.
     */
    async openDoc(doc, download = false) {
        if (!doc || !this.docsAvailable) {
            return;
        }
        const action = await this.orm.call("azm.dashboard", "open_tree_document", [], {
            kind: doc.kind,
            node_id: doc.id || null,
            tab: doc.tab || null,
            company_id: this.d.company.id,
            download,
        });
        await this.action.doAction(action);
    }

    /** The outputs a branch shows: all of them, or just the family being looked for. */
    docsOf(node) {
        const family = this.state.family;
        return family ? node.docs.filter((d) => d.tab === family) : node.docs;
    }

    /** A family of documents is a way in only if it hangs on the branches. */
    outputsOpen(family) {
        return !["requirement", "question"].includes(family.tab);
    }

    /**
     * Follow a family: the entity-wide ones open straight away, and a branch output
     * — policies, SOPs, authority … — unfolds every branch showing just that one,
     * which is what "how many policies" is really asking to see.
     */
    openOutputs(family) {
        if (!this.docsAvailable) {
            return;
        }
        if (family.tab === "summary" || family.tab === "cycle") {
            this.previewDoc({ kind: family.tab, label: family.label });
            return;
        }
        if (!this.outputsOpen(family)) {
            return;
        }
        const same = this.state.family === family.tab;
        this.state.family = same ? null : family.tab;
        this.state.docs = {};
        if (!same) {
            for (const node of this.nodes) {
                this.state.docs[node.id] = true;
            }
        }
    }

    /**
     * Read a node's document inside the tree, instead of sending the reader away to
     * a new tab. The server builds it if nobody has opened it before, which is why
     * the pane shows that it is working before it shows anything.
     */
    async previewDoc(doc) {
        if (!doc || !this.docsAvailable) {
            return;
        }
        this.state.preview = { doc, loading: true, error: "", name: doc.label || "" };
        try {
            const found = await this.orm.call("azm.dashboard", "preview_tree_document", [], {
                kind: doc.kind,
                node_id: doc.id || null,
                tab: doc.tab || null,
                company_id: this.d.company.id,
            });
            this.state.preview = { doc, loading: false, error: "", ...found };
        } catch (error) {
            // the document may be empty, or have failed to build: say so where the
            // reader is looking rather than throwing them a dialog
            this.state.preview = {
                doc, loading: false, name: doc.label || "",
                error: (error && error.data && error.data.message) || (error && error.message)
                    || "تعذّر عرض هذا المستند.",
            };
        }
    }

    closePreview() {
        this.state.preview = null;
    }

    /** Back to the page that lists every tree of every entity. */
    openTrees() {
        this.action.doAction("azm_platform.action_azm_trees");
    }
}
