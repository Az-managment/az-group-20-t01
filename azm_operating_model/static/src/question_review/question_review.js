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
        });
        onWillStart(() => this.loadHome());
    }

    get d() {
        return this.state;
    }

    async loadHome() {
        this.state.home = await this.orm.call(MODEL, "review_models", []);
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
            if (had !== !!question.note) {
                this.state.data.reviewed += question.note ? 1 : -1;
            }
        } finally {
            this.state.saving--;
        }
    }

    async sendAll() {
        const result = await this.orm.call(MODEL, "send_my_notes", []);
        this.notification.add(`أُرسلت ${result.sent} ملاحظة إلى مدير النموذج.`,
                              { type: "success" });
        if (this.state.node) {
            await this.openNode(this.state.node);
        }
        this.state.home = await this.orm.call(MODEL, "review_models", []);
    }

    get draftCount() {
        return (this.state.home?.models || []).reduce((n, m) => n + m.drafts, 0);
    }
}

registry.category("actions").add("azm_question_review", AzmQuestionReview);
