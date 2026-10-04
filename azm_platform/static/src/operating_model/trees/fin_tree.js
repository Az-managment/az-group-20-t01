import { registry } from "@web/core/registry";
import { pct } from "../om_utils";
import { AzmTreePage } from "./tree_base";

/**
 * AZM Platform · the unified financial model as a tree.
 *
 * FIN › module › topic › requirement on the left; picking a requirement shows it in
 * full on the right, built by the same code that writes its PDF, with the document
 * itself one click away.
 */
export class AzmFinTree extends AzmTreePage {
    static template = "azm_platform.FinTree";
    static dataMethod = "get_fin_tree";
    static nodeMethod = "get_fin_tree_node";
    static nodeArg = "requirement_id";

    get pageTitle() {
        return "شجرة النموذج المالي";
    }
    get pageTitleEn() {
        return "Financial model tree";
    }
    get pageSubtitle() {
        return "النموذج › الموديول › الموضوع › المتطلب — ومستند كل متطلب بجواره.";
    }
    get panelTitle() {
        return "شجرة النموذج";
    }
    get searchHint() {
        return "ابحث بالكود أو العنوان… مثل FIN.PUR.03";
    }

    get kpis() {
        const t = this.d.totals;
        return [
            { key: "modules", label: "الموديولات", en: "Modules", value: t.modules, icon: "folder", tone: "indigo",
                sub: `${t.topics} موضوعًا · ${t.requirements} متطلبًا` },
            { key: "applicable", label: "منطبق على الكيان", en: "Applicable here", value: t.applicable,
                icon: "checklist", tone: "blue", sub: `من ${t.requirements} في النموذج` },
            { key: "completion", label: "نسبة الاكتمال", en: "Completion", value: pct(t.completion),
                icon: "pie_chart", tone: "teal", meter: t.completion, sub: `${t.done} متطلبًا مكتملًا` },
            { key: "gaps", label: "الفجوات", en: "Gaps", value: t.gaps, icon: "warning", tone: "orange",
                sub: "مطبّق جزئيًا أو غير مطبّق" },
        ];
    }

    get banner() {
        const a = this.d.assessment;
        if (!a) {
            return { css: "info",
                text: "لم يبدأ هذا الكيان إفادته — الشجرة تعرض ما هو مطلوب منه.",
                en: "Not started — the tree shows what is asked." };
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
            text: "مسودة — مبنية على إفادة الكيان، والأدلة لم تُراجع بعد.",
            en: "Draft — built from the entity's assessment, evidence not yet checked." };
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
