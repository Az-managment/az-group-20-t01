import { Component, computed, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { KeepLast } from "@web/core/utils/concurrency";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

// mirrors STALE_AFTER in azm_progress.py: the page says the same number it counts by
const STALE_AFTER = 7;

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

    kpis = computed(() => {
        const t = this.d.totals;
        return [
            { key: "left", label: "أسئلة متبقية", en: "Questions left", value: t.left,
                icon: "help", tone: t.left ? "orange" : "green", sub: "عبر الكيانات كلها" },
            { key: "review", label: "تحت المراجعة", en: "In review", value: t.in_review,
                icon: "fact_check", tone: "blue", sub: `${t.approved} معتمدة` },
            // what has stopped moving, which is the thing a tracking page is read for
            { key: "stalled", label: "متوقفة", en: "Stalled", value: t.stalled,
                icon: "schedule", tone: t.stalled ? "orange" : "slate",
                sub: `بلا حركة منذ ${STALE_AFTER}+ أيام` },
            { key: "gaps", label: "فجوات مفتوحة", en: "Open gaps", value: t.gaps,
                icon: "report", tone: t.gaps ? "purple" : "slate", sub: "عبر النماذج كلها" },
            // work that came back and work nobody holds: the two things that stop on
            // their own if nobody is watching for them
            { key: "returned", label: "أجزاء مُعادة", en: "Sent back", value: t.returned,
                icon: "undo", tone: t.returned ? "orange" : "slate", sub: "بانتظار المعالجة" },
            { key: "unheld", label: "بلا مسؤول", en: "Unassigned", value: t.unheld,
                icon: "person_off", tone: t.unheld ? "orange" : "slate", sub: "أجزاء لم تُسند" },
            { key: "people", label: "الأشخاص", en: "People", value: t.people,
                icon: "group", tone: "slate", sub: `على ${t.entities} كيانًا` },
        ];
    });

    /** How far everything in reach has got, for the gauge the page opens with. */
    overall = computed(() => (this.state.data ? this.d.totals.progress : null));

    /** The models grouped by the entity they belong to. */
    byEntity = computed(() => {
        const blocks = [];
        for (const row of this.d.rows) {
            let block = blocks.find((b) => b.id === row.entity_id);
            if (!block) {
                block = { id: row.entity_id, name: row.entity, rows: [] };
                blocks.push(block);
            }
            block.rows.push(row);
        }
        // each entity's own standing, so a block says where it is before it is opened
        for (const block of blocks) {
            const done = block.rows.filter((r) => r.progress !== null);
            block.progress = done.length
                ? Math.round(done.reduce((sum, r) => sum + r.progress, 0) / done.length)
                : 0;
            block.left = block.rows.reduce((sum, r) => sum + r.left, 0);
            block.gaps = block.rows.reduce((sum, r) => sum + r.gaps, 0);
            block.returned = block.rows.reduce((sum, r) => sum + r.returned.length, 0);
            block.unheld = block.rows.reduce((sum, r) => sum + r.unheld.length, 0);
            block.stalled = block.rows.filter((r) => r.stalled).length;
        }
        return blocks;
    });

    /** How long ago, in the words somebody chasing work would use. */
    ago(value) {
        if (!value) {
            return "";
        }
        const days = Math.floor((Date.now() - new Date(value.replace(" ", "T") + "Z")) / 86400000);
        if (days <= 0) {
            return "اليوم";
        }
        if (days === 1) {
            return "أمس";
        }
        return `منذ ${days} يومًا`;
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
