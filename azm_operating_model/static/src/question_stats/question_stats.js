/**
 * ما وصل مدير النموذج من آراء المراجعين في الأسئلة.
 *
 * الصفحة تُقرأ من أعلى إلى أسفل كما يُقرأ الموقف: كم وصل، ثم بأي رأي وأين، ثم
 * الأسئلة نفسها بأكوادها وتحت كل سؤال ما قيل فيه. ما يحتاج نظرًا أولًا — فالصفحة
 * تُفتح على ما يُعمل به لا على ما طُمئن إليه.
 */
import { Component, onWillStart, proxy, useListener, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { download } from "@web/core/network/download";

const MODEL = "azm.question.comment";
const MODEL_NAMES = {
    financial: "النموذج المالي الموحد",
    procurement: "دورة المشتريات",
};
// اللون والأيقونة كما في مساحة الإجابة ومساحة المراجعة: النموذج يُعرف بلونه
const MODEL_LOOK = {
    financial: { tone: "green", icon: "payments" },
    procurement: { tone: "blue", icon: "shopping_cart" },
};

export class AzmQuestionStats extends Component {
    static template = "azm_operating_model.QuestionStats";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ stats: null, search: "", only: "all", downloading: false,
                             detail: null, opening: null });
        onWillStart(() => this.load());
        // البطاقة المنبثقة تُغلق بالمفتاح كما تُغلق بالنقر خارجها
        useListener(window, "keydown", (ev) => {
            if (ev.key === "Escape" && this.state.detail) {
                this.closeDetail();
            }
        });
    }

    get d() {
        return this.state;
    }

    async load() {
        const stats = await this.orm.call(MODEL, "comment_stats", []);
        this.state.stats = stats;
        // تُفتح على ما يُعمل به إن كان فيه ما يُعمل به. وأكثر ما يُقال عن سؤال
        // أنه سليم، فلو فُتحت على الكل لغرق ما يحتاج نظرًا في ما لا يحتاجه.
        this.state.only = stats.needs_work ? "needs_work" : "all";
    }

    modelName(key) {
        return MODEL_NAMES[key] || key;
    }

    modelLook(key) {
        return MODEL_LOOK[key] || { tone: "slate", icon: "help" };
    }

    /** كم رأيًا من آراء هذا السؤال يطلب تغييرًا. */
    get detailNeedsWork() {
        return (this.state.detail?.notes || []).filter((n) => n.needs_work).length;
    }

    get kpis() {
        const s = this.state.stats;
        if (!s) {
            return [];
        }
        const share = s.questions_total
            ? Math.round((1000 * s.questions_commented) / s.questions_total) / 10
            : 0;
        return [
            { key: "notes", label: "ملاحظات واردة", en: "Notes received",
                value: s.notes, icon: "chat", tone: "indigo",
                sub: `من ${s.reviewers} مراجع` },
            { key: "questions", label: "أسئلة عليها ملاحظة", en: "Questions commented",
                value: s.questions_commented, icon: "help", tone: "blue",
                sub: `${share}% من ${s.questions_total} سؤالًا` },
            { key: "needs", label: "تحتاج نظرًا", en: "Need work",
                value: s.needs_work, icon: "flag",
                tone: s.needs_work ? "orange" : "green",
                sub: s.needs_work ? "رأيٌ يطلب تغييرًا" : "لا شيء معلّق" },
            { key: "reviewers", label: "مراجعون", en: "Reviewers",
                value: s.reviewers, icon: "group", tone: "slate",
                sub: "ممن أرسلوا آراءهم" },
        ];
    }

    /** أكبر عدد في توزيع ما، ليُقاس عليه طول الأعمدة. */
    peak(rows, field) {
        return Math.max(1, ...(rows || []).map((r) => r[field] || 0));
    }

    /** الأسئلة بعد البحث والتصفية — بالكود أو بنص السؤال أو بنص الملاحظة. */
    get questions() {
        const s = this.state.stats;
        if (!s) {
            return [];
        }
        const needle = (this.state.search || "").trim().toLowerCase();
        const only = this.state.only;
        return s.questions.filter((q) => {
            if (only === "needs_work" && !q.needs_work) {
                return false;
            }
            if ((only === "financial" || only === "procurement") && q.model !== only) {
                return false;
            }
            if (!needle) {
                return true;
            }
            const hay = [q.code, q.label, q.node,
                         ...q.notes.map((n) => n.comment),
                         ...q.notes.map((n) => n.by)];
            return hay.some((part) => (part || "").toLowerCase().includes(needle));
        });
    }

    get filters() {
        const s = this.state.stats;
        return [
            { key: "all", name: "الكل", count: s ? s.questions_shown : 0 },
            { key: "needs_work", name: "تحتاج نظرًا",
                count: s ? s.questions.filter((q) => q.needs_work).length : 0 },
            { key: "financial", name: "المالي",
                count: s ? s.questions.filter((q) => q.model === "financial").length : 0 },
            { key: "procurement", name: "المشتريات",
                count: s ? s.questions.filter((q) => q.model === "procurement").length : 0 },
        ];
    }

    /**
     * السؤال كما هو في البنك: نصّه كاملًا، وموضعه من الشجرة، وخياراته كما
     * تُعرض على المجيب، وشرط ظهوره — ثم ما قيل فيه. فمن قرأ «ينقصه خيار» لا
     * يسعه الحكم حتى يرى الخيارات التي عندها قيل ذلك.
     */
    async openQuestion(question) {
        this.state.opening = question.model + question.code;
        try {
            this.state.detail = await this.orm.call(MODEL, "question_detail", [], {
                model_key: question.model, code: question.code,
            });
        } finally {
            this.state.opening = null;
        }
    }

    closeDetail() {
        this.state.detail = null;
    }

    /**
     * البنك كله ملفَّ إكسل: ورقة فيها كل سؤال في النموذجين ومعه ما قيل فيه،
     * وورقة فيها كل ملاحظة على حدة. والأسئلة كلها لا المعلَّق عليها وحدها —
     * سؤال لم يقل فيه أحد شيئًا خبرٌ عن المراجعة كالذي قيل فيه.
     */
    async downloadBank() {
        this.state.downloading = true;
        try {
            await download({ url: "/azm/question_bank.xlsx", data: {} });
        } finally {
            this.state.downloading = false;
        }
    }

    /** القائمة الكاملة، لمن أراد ما لا تسعه الصفحة أو أراد تصديره. */
    openFullList() {
        this.action.doAction("azm_operating_model.azm_question_comment_sent_action");
    }
}

registry.category("actions").add("azm_question_stats", AzmQuestionStats);
