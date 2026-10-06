import { Component, computed, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { entityImageUrl } from "@azm_platform/components/utils";
import { bar, pct } from "../om_utils";

// Each model that can be walked, said in both languages of the group.
const MODELS = {
    financial: {
        name: "النموذج المالي الموحد",
        en: "Unified financial model",
        desc: "كل متطلب مالي على الكيان، نزولًا إلى المستند الذي يجيب عنه.",
        desc_en: "Every financial requirement of the entity, down to the document that answers it.",
    },
    procurement: {
        name: "دورة المشتريات",
        en: "Procurement cycle",
        desc: "كل سؤال في الدورة، نزولًا إلى الإجابة المسجّلة والخطر الذي ترفعه.",
        desc_en: "Every question of the cycle, down to the answer given and the risk it raises.",
    },
};

const LEVELS = {
    module: ["موديول", "module"],
    topic: ["موضوع", "topic"],
    requirement: ["متطلب", "requirement"],
    stage: ["مرحلة", "stage"],
    group: ["مجموعة", "group"],
    question: ["سؤال", "question"],
};

const FIGURES = {
    applicable: ["منطبق", "applicable"],
    gaps: ["فجوة", "gaps"],
    answered: ["مُجاب", "answered"],
    findings: ["ملاحظة", "findings"],
};

// How the entities may be ordered. Progress first: the page is read to see who is behind.
const SORTS = [
    { key: "progress", label: "التقدّم", en: "Progress" },
    { key: "open", label: "ما يحتاج معالجة", en: "Open work" },
    { key: "name", label: "الاسم", en: "Name" },
];

const STATUSES = {
    approved: ["معتمدة", "Approved"],
    in_progress: ["جارية", "In progress"],
    not_started: ["لم تبدأ", "Not started"],
};

/**
 * AZM Platform · Trees (landing page).
 *
 * The entities first, then the trees of whichever one is opened. A tree is always
 * somebody's — there is no financial model in the abstract, only this entity's answers
 * to it — so the reader picks who they are asking about before what they are asking.
 */
export class AzmTreesHub extends Component {
    static template = "azm_platform.TreesHub";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.pct = pct;
        this.bar = bar;
        // `opened` is the company whose trees are on screen, or null for the entities;
        // `query` and `sort` only ever narrow or reorder what is already loaded
        this.state = proxy({ loaded: false, data: null, opened: null, query: "", sort: "progress" });
        this.SORTS = SORTS;
        onWillStart(async () => {
            this.state.data = await this.orm.call("azm.dashboard", "get_trees_hub", []);
            this.state.loaded = true;
        });
    }

    get d() {
        return this.state.data;
    }

    /** The entity being read, or null while the page is still showing all of them. */
    opened = computed(() => {
        if (!this.state.opened) {
            return null;
        }
        return this.all().find((e) => e.company_id === this.state.opened) || null;
    });

    /** How far the whole group has got — the one figure the page leads with. */
    overall = computed(() => {
        const done = this.all().filter((e) => e.completion !== null).map((e) => e.completion);
        return done.length ? done.reduce((a, b) => a + b, 0) / done.length : null;
    });

    /** Every entity, dressed for the page. */
    all = computed(() => {
        return this.d.entities.map((e) => ({
            ...e,
            logoUrl: e.company && e.company.has_logo
                ? entityImageUrl(e.company.id, "logo", "64x64", e.company.unique)
                : false,
            initials: (e.name || "?").trim().slice(0, 2),
            status_label: STATUSES[e.status][0],
            status_en: STATUSES[e.status][1],
            trees: e.trees.map((t) => ({
                ...t,
                ...MODELS[t.key],
                path: t.levels.map((l) => LEVELS[l][0]).join(" › "),
                path_en: t.levels.map((l) => LEVELS[l][1]).join(" › "),
                structure: `${t.units} ${LEVELS[t.levels[0]][0]} · ${t.leaves} ${LEVELS[t.levels[2]][0]}`,
                status_label: STATUSES[t.status][0],
                status_en: STATUSES[t.status][1],
                figures: t.figures.map((f) => ({ ...f, label: FIGURES[f.key][0], en: FIGURES[f.key][1] })),
            })),
            // what this entity still owes, for the sort and the card
            open: e.trees.reduce((n, t) => n + t.figures
                .filter((f) => f.tone === "warn").reduce((m, f) => m + f.value, 0), 0),
        }));
    });

    /** The entities the page is showing: what the search left, in the chosen order. */
    entities = computed(() => {
        const needle = this.state.query.trim().toLowerCase();
        const rows = needle
            ? this.all().filter((e) => `${e.name} ${e.code}`.toLowerCase().includes(needle))
            : this.all();
        // a null completion is "not started", which sorts below nought per cent rather
        // than above it
        const score = (e) => (e.completion === null ? -1 : e.completion);
        return [...rows].sort((a, b) => {
            if (this.state.sort === "name") {
                return a.name.localeCompare(b.name, "ar");
            }
            if (this.state.sort === "open") {
                return b.open - a.open || score(b) - score(a);
            }
            return score(b) - score(a) || a.name.localeCompare(b.name, "ar");
        });
    });

    /** A card is a button: the keyboard opens it the way the pointer does. */
    onCardKey(ev, fn) {
        if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            fn();
        }
    }

    /** Show the trees of one entity. */
    openEntity(entity) {
        this.state.opened = entity.company_id;
    }

    /** Back to the entities. */
    closeEntity() {
        this.state.opened = null;
    }

    /** Open one entity's tree of one model — the card is the way in. */
    openTree(entity, tree) {
        this.action.doAction(tree.action, {
            additionalContext: { azm_company_id: entity.company_id },
        });
    }
}

registry.category("actions").add("azm_trees", AzmTreesHub);
