/**
 * مساحة مراجعة بنك الأسئلة.
 *
 * تقابل مساحة الإجابة في شكلها — نموذجان، ثم أقسام، ثم أسئلة — وتختلف عنها في
 * موضوعها: هنا يُقرأ السؤال ويُكتب رأي فيه، ولا تُقرأ إجابة ولا تُكتب. ولذلك لا
 * تمرّ بإفادة كيان أصلًا: مراجع بنك الأسئلة لا يرى إجابات أحد.
 */
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const MODEL = "azm.question.comment";

export class AzmQuestionReview extends Component {
    static template = "azm_operating_model.QuestionReview";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = proxy({
            home: null,        // النموذجان
            model: null,       // النموذج المفتوح
            nodes: [],         // أقسامه
            node: null,        // القسم المفتوح
            data: null,        // أسئلته
            busy: false,
            saving: 0,
            search: "",
            drafts: 0,        // ما كتبتُه ولم أرسله — يُعرض حيث يُكتب
        });
        onWillStart(() => this.loadHome());
    }

    get d() {
        return this.state;
    }

    async loadHome() {
        this.state.home = await this.orm.call(MODEL, "review_models", []);
        this.state.drafts = this.state.home.models.reduce((n, m) => n + m.drafts, 0);
        this.state.model = null;
        this.state.node = null;
        this.state.data = null;
    }

    async openModel(key) {
        this.state.busy = true;
        try {
            this.state.model = key;
            this.state.nodes = await this.orm.call(MODEL, "review_nodes", [], { model_key: key });
            const first = this.state.nodes[0];
            if (first) {
                await this.openNode(first.code);
            }
        } finally {
            this.state.busy = false;
        }
    }

    async openNode(code) {
        this.state.busy = true;
        try {
            this.state.node = code;
            this.state.data = await this.orm.call(MODEL, "review_questions", [], {
                model_key: this.state.model, node_code: code,
            });
        } finally {
            this.state.busy = false;
        }
    }

    backHome() {
        this.loadHome();
    }

    modelName(key) {
        const found = (this.state.home?.models || []).find((m) => m.key === key);
        return found ? found.name : "";
    }

    verdicts() {
        return this.state.home?.verdicts || [];
    }

    verdictName(key) {
        const found = this.verdicts().find((v) => v.key === key);
        return found ? found.name : "";
    }

    /** الأسئلة المعروضة بعد البحث — بالكود أو بالنص. */
    questionsOf(group) {
        const needle = (this.state.search || "").trim().toLowerCase();
        if (!needle) {
            return group.questions;
        }
        return group.questions.filter((q) =>
            [q.code, q.key, q.label, q.hint].some(
                (part) => (part || "").toLowerCase().includes(needle)));
    }

    visibleGroups() {
        return (this.state.data?.groups || []).filter((g) => this.questionsOf(g).length);
    }

    /** يحفظ الرأي فور كتابته — فمن كتب رأيه ثم انتقل لا يعود ليضغط حفظًا. */
    async saveNote(question, change) {
        const note = question.note || {};
        if (note.state === "sent") {
            return;
        }
        const verdict = change.verdict ?? note.verdict ?? "wording";
        const comment = change.comment ?? note.comment ?? "";
        this.state.saving++;
        try {
            const saved = await this.orm.call(MODEL, "save_note", [], {
                model_key: this.state.model, question_id: question.id, verdict, comment,
            });
            const had = !!question.note;
            question.note = saved.deleted ? false : { ...saved, verdict, comment };
            this.state.drafts = saved.drafts ?? this.state.drafts;
            if (had !== !!question.note) {
                this.state.data.reviewed += question.note ? 1 : -1;
            }
        } finally {
            this.state.saving--;
        }
    }

    /**
     * «سليم» بضغطة. أكثر ما يُقال عن سؤال أنه لا شيء عليه، ومن اضطُرّ إلى كتابة
     * ذلك ألف مرة لم يراجع. وضغطة ثانية تتراجع عنها ما دامت لم تُرسَل.
     */
    async approve(question) {
        if (question.note && question.note.state === "sent") {
            return;
        }
        this.state.saving++;
        try {
            const saved = await this.orm.call(MODEL, "approve_question", [], {
                model_key: this.state.model, question_id: question.id,
            });
            const had = !!question.note;
            question.note = saved.deleted ? false : saved;
            this.state.drafts = saved.drafts ?? this.state.drafts;
            if (had !== !!question.note) {
                this.state.data.reviewed += question.note ? 1 : -1;
            }
        } finally {
            this.state.saving--;
        }
    }

    isApproved(question) {
        return !!question.note && question.note.verdict === "clear";
    }

    async sendAll() {
        const result = await this.orm.call(MODEL, "send_my_notes", []);
        this.notification.add(`أُرسلت ${result.sent} ملاحظة إلى مدير النموذج.`,
                              { type: "success" });
        this.state.drafts = 0;
        if (this.state.node) {
            await this.openNode(this.state.node);
        }
        this.state.home = await this.orm.call(MODEL, "review_models", []);
    }

    get draftCount() {
        return this.state.drafts;
    }

    /**
     * الأرقام الأربعة أعلى الصفحة. تقابل أرقام «مساحتي» عند من يُجيب، ويُعدّ فيها
     * ما يخص المراجعة: كم سؤالًا أمامه، وكم قال رأيه فيه، وكم رأيًا لم يُرسله بعد.
     */
    get kpis() {
        const models = this.state.home?.models || [];
        const sum = (field) => models.reduce((n, m) => n + (m[field] || 0), 0);
        const total = sum("total");
        const reviewed = sum("reviewed");
        const left = total - reviewed;
        return [
            { key: "total", label: "أسئلة البنك", en: "Questions in the bank",
                value: total, icon: "help", tone: "slate",
                sub: `في ${models.length} نموذج` },
            { key: "reviewed", label: "قلتُ رأيي فيها", en: "Reviewed",
                value: reviewed, icon: "rate_review", tone: "indigo",
                sub: total ? `${Math.round((100 * reviewed) / total)}% من البنك` : "" },
            { key: "left", label: "لم أقرأها بعد", en: "Left to review",
                value: left, icon: "pending", tone: left ? "orange" : "green",
                sub: left ? "بانتظارك" : "اكتملت المراجعة" },
            { key: "drafts", label: "مسودات لم تُرسل", en: "Unsent notes",
                value: this.draftCount, icon: "drafts",
                tone: this.draftCount ? "orange" : "green",
                sub: `أُرسل منها ${sum("sent")}` },
        ];
    }
}

registry.category("actions").add("azm_question_review", AzmQuestionReview);
