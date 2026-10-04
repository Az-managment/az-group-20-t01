import { registry } from "@web/core/registry";
import { pct } from "../om_utils";
import { AzmTreePage } from "./tree_base";

/**
 * AZM Platform · the procurement cycle as a tree.
 *
 * PUR › stage › group › question on the left; picking a question shows what is asked,
 * what this entity answered, the sentence the book will print from it and the risks
 * the catalogue watches on that answer.
 */
export class AzmProcTree extends AzmTreePage {
    static template = "azm_platform.ProcTree";
    static dataMethod = "get_proc_tree";
    static nodeMethod = "get_proc_tree_node";
    static nodeArg = "question_id";

    get pageTitle() {
        return "شجرة دورة المشتريات";
    }
    get pageTitleEn() {
        return "Procurement cycle tree";
    }
    get pageSubtitle() {
        return "الدورة › المرحلة › المجموعة › السؤال — وإجابة الكيان والمخاطر المرتبطة بها.";
    }
    get panelTitle() {
        return "شجرة الدورة";
    }
    get searchHint() {
        return "ابحث بالكود أو السؤال… مثل PUR-REQ";
    }

    /** An entity may have several assessments; a leaf is read from the one on screen. */
    get extra() {
        const a = this.d && this.d.assessment;
        return a ? { assessment_id: a.id } : {};
    }

    get selects() {
        const selects = super.selects;
        if (this.d.assessment && this.d.assessment_options.length > 1) {
            selects.push({
                key: "assessment",
                title: "الإفادة",
                value: this.d.assessment.id,
                options: this.d.assessment_options,
            });
        }
        return selects;
    }

    async onSelectChange(key, ev) {
        if (key === "assessment") {
            await this.load(this.d.company.id, { assessment_id: parseInt(ev.target.value, 10) });
            return;
        }
        await super.onSelectChange(key, ev);
    }

    /** The documents are built from one assessment; another one on screen must not
     *  be handed documents that answer differently. */
    get docsAvailable() {
        return !!(this.d.documents && this.d.documents.match);
    }

    get docsNote() {
        if (this.docsAvailable) {
            return "";
        }
        const from = this.d.documents && this.d.documents.from;
        return from
            ? `المستندات تُبنى من ${from} — اخترها لعرضها.`
            : "لا توجد إفادة تُبنى منها مستندات هذا الكيان بعد.";
    }

    get kpis() {
        const t = this.d.totals;
        return [
            { key: "stages", label: "مراحل الدورة", en: "Stages", value: t.stages, icon: "account_tree",
                tone: "indigo", sub: `${t.groups} مجموعة · ${t.questions} سؤالًا` },
            { key: "asked", label: "يُسأل هنا", en: "Asked here", value: t.asked, icon: "checklist",
                tone: "blue", sub: `من ${t.questions} في الكتالوج` },
            { key: "completion", label: "نسبة الاكتمال", en: "Completion", value: pct(t.completion),
                icon: "pie_chart", tone: "teal", meter: t.completion, sub: `${t.known} إجابة مؤكدة` },
            { key: "findings", label: "ملاحظات مفتوحة", en: "Open findings", value: t.findings,
                icon: "warning", tone: "orange", sub: "نتجت عن الإجابات المسجّلة" },
        ];
    }

    get banner() {
        const a = this.d.assessment;
        if (!a) {
            return { css: "info",
                text: "لا توجد إفادة مشتريات لهذا الكيان — الشجرة تعرض ما هو مطلوب منه.",
                en: "No procurement assessment — the tree shows what is asked." };
        }
        if (a.is_demo) {
            return { css: "warn",
                text: "بيانات تجريبية لتجربة النموذج — ليست إجابات هذا الكيان الحقيقية.",
                en: "Sample data for trying the model — not this entity's real answers." };
        }
        if (a.state === "approved") {
            return { css: "ok", text: `معتمدة · الإصدار ${a.version}`, en: `Approved · version ${a.version}` };
        }
        return { css: "info",
            text: `${a.state_label} · ${a.name} — الإجابات ما زالت قابلة للتغيير.`,
            en: "Draft — answers may still change." };
    }

    openAssessment() {
        const a = this.d.assessment;
        if (!a) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "azm.assessment",
            res_id: a.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openQuestion(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "azm.question",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openFinding(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "azm.finding",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("azm_proc_tree", AzmProcTree);
