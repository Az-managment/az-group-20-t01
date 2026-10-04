import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
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

const STATUSES = {
    approved: ["معتمدة", "Approved"],
    in_progress: ["جارية", "In progress"],
    not_started: ["لم تبدأ", "Not started"],
};

/**
 * AZM Platform · Trees (landing page).
 *
 * One section per model that can be walked as a tree, one card per entity under it.
 * A card carries that entity's own figures and opens that entity's tree — a tree is
 * always read for somebody, never in the abstract.
 */
export class AzmTreesHub extends Component {
    static template = "azm_platform.TreesHub";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.pct = pct;
        this.bar = bar;
        this.state = proxy({ loaded: false, data: null });
        onWillStart(async () => {
            this.state.data = await this.orm.call("azm.dashboard", "get_trees_hub", []);
            this.state.loaded = true;
        });
    }

    get d() {
        return this.state.data;
    }

    get totals() {
        const t = this.d.totals;
        return [
            { key: "trees", label: "شجر", en: "Trees", value: t.trees, mark: true, tone: "green",
                sub: `${t.units} فرعًا · ${t.leaves} ورقة`,
                sub_en: `${t.units} branches · ${t.leaves} leaves` },
            { key: "entities", label: "الكيانات", en: "Entities", icon: "business", tone: "slate",
                value: `${t.entities_covered}/${t.entities}`,
                sub: "بدأت شجرتها بالفعل", sub_en: "with a tree already started" },
        ];
    }

    get sections() {
        return this.d.sections.map((s) => ({
            ...s,
            ...MODELS[s.key],
            path: s.levels.map((l) => LEVELS[l][0]).join(" › "),
            path_en: s.levels.map((l) => LEVELS[l][1]).join(" › "),
            structure: `${s.units} ${LEVELS[s.levels[0]][0]} · ${s.leaves} ${LEVELS[s.levels[2]][0]}`,
            cards: s.cards.map((c) => ({
                ...c,
                logoUrl: c.company && c.company.has_logo
                    ? entityImageUrl(c.company.id, "logo", "64x64", c.company.unique)
                    : false,
                initials: (c.name || "?").trim().slice(0, 2),
                status_label: STATUSES[c.status][0],
                status_en: STATUSES[c.status][1],
                figures: c.figures.map((f) => ({ ...f, label: FIGURES[f.key][0], en: FIGURES[f.key][1] })),
            })),
        }));
    }

    /** A card is a button: the keyboard opens it the way the pointer does. */
    onCardKey(ev, section, card) {
        if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            this.open(section, card);
        }
    }

    /** Open one entity's tree of one model — the card is the way in. */
    open(section, card) {
        this.action.doAction(section.action, {
            additionalContext: { azm_company_id: card.company_id },
        });
    }
}

registry.category("actions").add("azm_trees", AzmTreesHub);
