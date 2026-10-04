import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { pct } from "../om_utils";

/**
 * AZM Platform · the unified financial model as a tree.
 *
 * The model walks FIN › module › topic › requirement on the left; picking a requirement
 * shows it in full on the right, built by the same code that writes its PDF, with the
 * document itself one click away.
 */
export class AzmFinTree extends Component {
    static template = "azm_platform.FinTree";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.pct = pct;
        this.state = proxy({
            loaded: false,
            data: null,
            open: {},          // "m-3" / "t-12" → expanded
            selected: null,    // requirement id
            node: null,        // its detail
            loadingNode: false,
            query: "",
        });
        onWillStart(async () => {
            await this.load();
        });
    }

    async load(companyId = null) {
        this.state.loaded = false;
        this.state.data = await this.orm.call("azm.dashboard", "get_fin_tree", [], {
            company_id: companyId,
        });
        this.state.loaded = true;
        // open the first module so the page never greets anyone with a wall of closed rows
        const first = this.modules[0];
        if (first) {
            this.state.open[`m-${first.id}`] = true;
        }
    }

    get d() {
        return this.state.data;
    }

    get modules() {
        return (this.d && this.d.modules) || [];
    }

    /** The tree, narrowed to what the search box matches (code, title or topic). */
    get tree() {
        const q = this.state.query.trim().toLowerCase();
        if (!q) {
            return this.modules;
        }
        const hit = (text) => (text || "").toLowerCase().includes(q);
        return this.modules
            .map((m) => {
                const topics = m.topics
                    .map((t) => {
                        const items = t.items.filter(
                            (i) => hit(i.tree_ref) || hit(i.title) || hit(t.name) || hit(t.code)
                        );
                        return items.length ? { ...t, items } : null;
                    })
                    .filter(Boolean);
                const match = hit(m.code) || hit(m.name);
                if (match && !topics.length) {
                    return m;
                }
                return topics.length ? { ...m, topics } : null;
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
        for (const m of this.modules) {
            this.state.open[`m-${m.id}`] = true;
            for (const t of m.topics) {
                this.state.open[`t-${t.id}`] = true;
            }
        }
    }

    collapseAll() {
        this.state.open = {};
    }

    async select(item) {
        this.state.selected = item.id;
        this.state.loadingNode = true;
        try {
            this.state.node = await this.orm.call("azm.dashboard", "get_fin_tree_node", [], {
                requirement_id: item.id,
                company_id: this.d.company.id,
            });
        } finally {
            this.state.loadingNode = false;
        }
    }

    async onEntityChange(ev) {
        this.state.selected = null;
        this.state.node = null;
        await this.load(parseInt(ev.target.value, 10));
    }

    get kpis() {
        const t = this.d.totals;
        return [
            { key: "modules", label: _t("Modules"), value: t.modules, icon: "folder", tone: "indigo",
                sub: _t("%(t)s topics · %(r)s requirements", { t: t.topics, r: t.requirements }) },
            { key: "applicable", label: _t("Applicable here"), value: t.applicable, icon: "checklist", tone: "blue",
                sub: _t("of %s in the model", t.requirements) },
            { key: "completion", label: _t("Completion"), value: pct(t.completion), icon: "pie_chart", tone: "teal",
                meter: t.completion, sub: _t("%s requirements complete", t.done) },
            { key: "gaps", label: _t("Gaps"), value: t.gaps, icon: "warning", tone: "orange",
                sub: _t("partly or not in place") },
        ];
    }

    get banner() {
        const a = this.d.assessment;
        if (!a) {
            return { css: "info", text: _t("This entity has not started its assessment — the tree shows what is asked.") };
        }
        if (a.is_demo) {
            return { css: "warn", text: _t("Sample data for trying the model — not this entity's real answers.") };
        }
        if (a.state === "approved") {
            return { css: "ok", text: _t("Approved · version %s", a.version) };
        }
        return { css: "info", text: _t("Draft — built from the entity's assessment, evidence not yet checked.") };
    }

    /** Read or download the requirement's document, or the entity summary. */
    async openDoc(doc, download = false) {
        if (!doc) {
            return;
        }
        const action = await this.orm.call(
            "azm.doc.publication",
            download ? "action_download" : "action_read",
            [[doc.id]]
        );
        await this.action.doAction(action);
    }

    openRequirement(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "azm.fin.requirement",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("azm_fin_tree", AzmFinTree);
