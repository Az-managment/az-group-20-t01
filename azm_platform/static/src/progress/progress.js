import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { KeepLast } from "@web/core/utils/concurrency";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

/**
 * AZM Platform · التقدّم — who is doing what, and how far they have got.
 *
 * مساحتي is one person's own page. This is the other half of the same subject and
 * deliberately not that: somebody tracking the work does not want their own, they want
 * everybody's — who prepares each model, who reviews it, where it stands, and where the
 * work has been divided, which part belongs to whom.
 */
export class AzmProgress extends Component {
    static template = "azm_platform.Progress";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.keepLoad = new KeepLast();
        this.state = proxy({ loaded: false, data: null, error: "", open: {} });
        onWillStart(async () => {
            await this.load();
        });
    }

    async load() {
        this.state.loaded = false;
        this.state.error = "";
        try {
            this.state.data = await this.keepLoad.add(
                this.orm.call("azm.dashboard", "get_progress", [], {})
            );
        } catch (error) {
            this.state.data = null;
            this.state.error = (error && error.data && error.data.message)
                || (error && error.message) || "تعذّر تحميل التقدّم.";
        } finally {
            this.state.loaded = true;
        }
    }

    get d() {
        return this.state.data;
    }

    get kpis() {
        const t = this.d.totals;
        return [
            { key: "progress", label: "متوسط الاكتمال", en: "Completion", value: `${t.progress}%`,
                icon: "donut_large", tone: "indigo", sub: `${t.models} نموذجًا قيد العمل` },
            { key: "left", label: "أسئلة متبقية", en: "Questions left", value: t.left,
                icon: "help", tone: t.left ? "orange" : "green", sub: "عبر الكيانات كلها" },
            { key: "review", label: "تحت المراجعة", en: "In review", value: t.in_review,
                icon: "fact_check", tone: "blue", sub: `${t.approved} معتمدة` },
            { key: "people", label: "الأشخاص", en: "People", value: t.people,
                icon: "group", tone: "slate", sub: `على ${t.entities} كيانًا` },
        ];
    }

    /** The models grouped by the entity they belong to. */
    get byEntity() {
        const blocks = [];
        for (const row of this.d.rows) {
            let block = blocks.find((b) => b.id === row.entity_id);
            if (!block) {
                block = { id: row.entity_id, name: row.entity, rows: [] };
                blocks.push(block);
            }
            block.rows.push(row);
        }
        return blocks;
    }

    isOpen(row) {
        return !!this.state.open[`${row.res_model}-${row.id}`];
    }

    toggle(row) {
        const key = `${row.res_model}-${row.id}`;
        this.state.open[key] = !this.state.open[key];
    }

    open(row) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: row.res_model,
            res_id: row.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openAssignments() {
        this.action.doAction("azm_operating_model.azm_assignment_action");
    }
}

registry.category("actions").add("azm_progress", AzmProgress);
