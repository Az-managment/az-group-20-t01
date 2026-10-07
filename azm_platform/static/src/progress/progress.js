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
            { key: "people", label: "الأشخاص", en: "People", value: t.people,
                icon: "group", tone: "slate", sub: `على ${t.entities} كيانًا` },
        ];
    });

    /** How far everything in reach has got, for the gauge the page opens with. */
    overall = computed(() => (this.state.data ? this.d.totals.progress : null));

    /** The models grouped by the entity they belong to, each block carrying the few
     * figures its header states — counted here rather than in the template, which
     * would recount them on every render. */
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
        for (const block of blocks) {
            const answered = block.rows.reduce((n, r) => n + (r.answered || 0), 0);
            const total = block.rows.reduce((n, r) => n + (r.total || 0), 0);
            block.models = block.rows.length;
            block.left = block.rows.reduce((n, r) => n + (r.left || 0), 0);
            block.stalled = block.rows.filter((r) => r.stalled).length;
            block.progress = total ? Math.round((100 * answered) / total) : 0;
        }
        return blocks;
    });

    /** Somebody's initials, for the disc that stands in for a face.

    Arabic names carry no case, so the usual uppercase() does nothing and is left off.
    Two words give two letters; anything else gives one, because three letters of an
    Arabic name read as a word rather than a monogram. */
    initials(name) {
        const words = (name || "").trim().split(/\s+/).filter(Boolean);
        if (!words.length) {
            return "؟";
        }
        return words.length > 1 ? words[0][0] + words[1][0] : words[0][0];
    }

    /** A stable colour per person: the same face keeps the same disc between loads,
     * which is what makes it worth having a colour at all. */
    personTone(person) {
        const tones = ["indigo", "blue", "teal", "purple", "orange", "green", "slate"];
        return tones[Math.abs(person.id || 0) % tones.length];
    }

    /** What somebody is on, as separate words the template lays out rather than one
     * sentence it has to punctuate with nested conditionals. */
    personRoles(person) {
        const roles = [];
        if (person.parts) {
            roles.push({ key: "parts", text: `يجيب ${person.parts} جزءًا` });
        }
        if (person.preparing) {
            roles.push({ key: "prep", text: `يُعدّ ${person.preparing} إفادة` });
        }
        if (person.reviewing) {
            roles.push({ key: "rev", text: `يراجع ${person.reviewing} إفادة` });
        }
        return roles;
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
