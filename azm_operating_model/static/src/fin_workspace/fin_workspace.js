import { Component, markup, onWillStart, onWillUnmount, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { KeepLast } from "@web/core/utils/concurrency";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const MODEL = "azm.fin.assessment";
const FALLBACK = ["unknown", "not_listed", "none"];
const UNIFIED_ROLES = ["status", "impl", "rule", "target"];

/**
 * Unified financial model · answer workspace.
 * Same layout and answer widgets as the procurement workspace: module rail · questions · live documents.
 * Each requirement has its own questions (single / multiple choice, number, table) and the
 * four unified status questions; «يظهر لو» conditions are evaluated server side.
 */
export class AzmFinWorkspace extends Component {
    static template = "azm_operating_model.FinWorkspace";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.keepLast = new KeepLast();
        const params = this.props.action.params || {};
        this.assessmentId = params.assessment_id || this.props.action.context?.active_id;
        this.focusCode = params.requirement_code || false;
        this.state = proxy({
            data: null,
            moduleCode: params.module_code || null,
            tab: "book",
            scope: "module",
            output: markup(""),
            showAll: false,
            onlyOpen: false,
            onlyReturned: false,
            // DEV19 — بحث بالاسم والكود. الموديول الواحد يبلغ 44 متطلبًا و157
            // سؤالًا، ولم تكن هناك وسيلة للوصول إلى واحد منها إلا بالتمرير.
            search: "",
            busy: false,
            saving: 0,
            openPrompts: {},
            otherReason: {},
            // the part a reviewer is sending back, and the reason being typed for it
            returning: null,
            returnNote: "",
        });
        this.timers = {};
        onWillStart(() => this.load());
        onWillUnmount(() => {
            clearTimeout(this.scrollTimer);
            // the pending saves are still sent — leaving a page should not lose what
            // was typed — but nothing of their answer is written back into a component
            // that is going away, and a failure here is reported rather than left as
            // an unhandled rejection
            this.leaving = true;
            Promise.resolve(this.flushAll()).catch((error) =>
                console.warn("AZM: a pending answer could not be saved on leaving", error));
        });
    }

    // ------------------------------------------------------------ review
    /** Start sending a part back: the current module, or one requirement of it. */
    startReturn(level, id, name) {
        this.state.returning = { level, id, name };
        this.state.returnNote = "";
    }

    cancelReturn() {
        this.state.returning = null;
        this.state.returnNote = "";
    }

    async confirmReturn() {
        const note = (this.state.returnNote || "").trim();
        if (!note || !this.state.returning) {
            return;
        }
        this.state.busy = true;
        try {
            await this.orm.call("azm.dashboard", "return_review_part", [], {
                res_model: MODEL,
                assessment_id: this.assessmentId,
                level: this.state.returning.level,
                part_id: this.state.returning.id,
                note,
            });
            this.cancelReturn();
            await this.load();
        } finally {
            this.state.busy = false;
        }
    }

    /** Ask for the work to be reviewed. */
    async requestReview() {
        this.state.busy = true;
        try {
            await this.flushAll();
            await this.orm.call(MODEL, "action_submit", [[this.assessmentId]]);
            await this.load();
        } finally {
            this.state.busy = false;
        }
    }

    // ------------------------------------------------------------ data
    async load(moduleCode = this.state.moduleCode) {
        this.flushAll();
        const data = await this.keepLast.add(
            this.orm.call(MODEL, "workspace_data", [[this.assessmentId]], {
                module_code: moduleCode,
                tab: this.state.tab,
                scope: this.state.scope,
                show_all: this.state.showAll,
            })
        );
        this.state.data = data;
        this.state.moduleCode = data.module.code;
        this.state.output = markup(data.output);
        if (this.focusCode) {
            const code = this.focusCode;
            this.focusCode = false;
            // held so it can be cancelled: the component can be left before it fires,
            // and a timer that outlives it reaches into a page that has gone
            this.scrollTimer = setTimeout(
                () => document.querySelector(`[data-req="${code}"]`)
                    ?.scrollIntoView({ block: "start" }), 50);
        }
    }

    async refreshOutput() {
        this.state.busy = true;
        try {
            const html = await this.keepLast.add(
                this.orm.call(MODEL, "workspace_output", [[this.assessmentId]], {
                    module_code: this.state.moduleCode,
                    tab: this.state.tab,
                    scope: this.state.scope,
                })
            );
            this.state.output = markup(html);
        } finally {
            this.state.busy = false;
        }
    }

    get d() {
        return this.state.data;
    }
    get readonly() {
        return this.d.header.readonly;
    }

    requirements() {
        return this.d.topics.flatMap((t) => t.requirements);
    }

    // ------------------------------------------------------------ saving
    async call(method, req, args) {
        if (this.readonly) {
            return;
        }
        this.state.saving++;
        try {
            const result = await this.orm.call(MODEL, method, [[this.assessmentId], req.answer_id, ...args], {
                module_code: this.state.moduleCode,
                tab: this.state.tab,
                scope: this.state.scope,
            });
            if (this.leaving) {
                // the save was sent and has landed; there is no component left to tell
                return;
            }
            this.applyRequirement(result.requirement);
            this.d.header = result.header;
            this.d.modules = result.modules;
            this.state.output = markup(result.output);
        } finally {
            this.state.saving--;
        }
    }

    /** «ما زالت صحيحة» — تأكيد إجابة عادت مع فرعها دون تغيير قيمتها. */
    async confirmStale(req, question) {
        await this.call("workspace_confirm", req, [question.id]);
    }

    applyRequirement(fresh) {
        for (const topic of this.d.topics) {
            const idx = topic.requirements.findIndex((r) => r.answer_id === fresh.answer_id);
            if (idx >= 0) {
                // keep what is still being typed in a question with a pending save
                for (const q of fresh.questions) {
                    if (Object.keys(this.timers).some((id) => id.startsWith(`${fresh.answer_id}:${q.id}:`))) {
                        const old = topic.requirements[idx].questions.find((x) => x.id === q.id);
                        if (old) {
                            q.value = old.value;
                        }
                    }
                }
                topic.requirements[idx] = fresh;
            }
        }
    }

    answer(req, q, vals) {
        return this.call("workspace_answer", req, [q.id, vals]);
    }

    debounce(req, q, key, vals) {
        const id = `${req.answer_id}:${q.id}:${key}`;
        clearTimeout(this.timers[id]?.handle);
        this.timers[id] = { run: () => this.answer(req, q, vals), handle: setTimeout(() => this.flush(id), 700) };
    }

    debounceLine(req, vals) {
        const id = `${req.answer_id}:line`;
        clearTimeout(this.timers[id]?.handle);
        this.timers[id] = {
            run: () => this.call("workspace_requirement", req, [vals]),
            handle: setTimeout(() => this.flush(id), 700),
        };
    }

    flush(id) {
        const pending = this.timers[id];
        if (pending) {
            clearTimeout(pending.handle);
            delete this.timers[id];
            pending.run();
        }
    }

    flushAll() {
        Object.keys(this.timers).forEach((id) => this.flush(id));
    }

    // ------------------------------------------------------------ answer handlers
    pick(req, q, option) {
        if (this.readonly) {
            return;
        }
        if (q.qtype === "multi") {
            const ids = new Set(q.value.option_ids);
            if (ids.has(option.id)) {
                ids.delete(option.id);
            } else if (FALLBACK.includes(option.kind)) {
                ids.clear();
                ids.add(option.id);
            } else {
                for (const o of q.options) {
                    if (FALLBACK.includes(o.kind)) {
                        ids.delete(o.id);
                    }
                }
                ids.add(option.id);
            }
            q.value.option_ids = [...ids];
            this.answer(req, q, { option_ids: q.value.option_ids });
        } else {
            q.value.option_id = q.value.option_id === option.id ? false : option.id;
            const vals = { option_id: q.value.option_id };
            if (q.qtype === "table" && q.value.option_id) {
                q.value.table = [];
            }
            this.answer(req, q, vals);
        }
    }

    pickSelect(req, q, ev) {
        const id = parseInt(ev.target.value, 10);
        q.value.option_id = Number.isNaN(id) ? false : id;
        this.answer(req, q, { option_id: q.value.option_id });
    }

    setNumber(req, q, ev) {
        const raw = ev.target.value;
        const value = raw === "" ? null : parseFloat(raw);
        q.value.number = Number.isNaN(value) ? null : value;
        this.debounce(req, q, "number", { number: q.value.number });
    }

    setNote(req, q, ev) {
        q.value.note = ev.target.value;
        this.debounce(req, q, "note", { note: q.value.note });
    }

    rows(q) {
        const cols = q.columns.length;
        const rows = q.value.table.length ? q.value.table : [Array(cols).fill("")];
        return rows.map((row) => Array.from({ length: cols }, (_v, i) => row[i] || ""));
    }

    onCell(req, q, rowIndex, colIndex, ev) {
        const rows = this.rows(q);
        rows[rowIndex][colIndex] = ev.target.value;
        q.value.table = rows;
        if (q.value.option_id) {
            q.value.option_id = false;
        }
        if (ev.target.tagName === "SELECT") {
            this.answer(req, q, { table: rows });
        } else {
            this.debounce(req, q, "table", { table: rows });
        }
    }

    addRow(req, q) {
        q.value.table = [...this.rows(q), Array(q.columns.length).fill("")];
    }

    removeRow(req, q, rowIndex) {
        q.value.table = this.rows(q).filter((_r, i) => i !== rowIndex);
        this.answer(req, q, { table: q.value.table });
    }

    toggleNa(req) {
        req.na = !req.na;
        this.call("workspace_requirement", req, [{ na: req.na }]);
    }

    // «لا ينطبق»: a reason from the list; «سبب آخر» opens a box for the typed reason
    reasonChoice(req) {
        if (this.state.otherReason[req.answer_id]) {
            return "سبب آخر";
        }
        if (!req.reason) {
            return false;
        }
        return this.d.na_reasons.includes(req.reason) ? req.reason : "سبب آخر";
    }

    reasonDetail(req) {
        return this.d.na_reasons.includes(req.reason) ? "" : req.reason.replace(/^سبب آخر: /, "");
    }

    pickReason(req, reason) {
        const other = reason === "سبب آخر";
        this.state.otherReason[req.answer_id] = other && this.reasonChoice(req) !== "سبب آخر";
        const value = other || req.reason === reason ? "" : reason;
        req.reason = value;
        this.call("workspace_requirement", req, [{ reason: value }]);
    }

    setReason(req, ev) {
        const text = ev.target.value.trim();
        req.reason = text ? `سبب آخر: ${text}` : "";
        this.debounceLine(req, { reason: req.reason });
    }

    toggleTag(req, q, tag) {
        const tags = new Set(q.value.note_tags);
        tags.has(tag) ? tags.delete(tag) : tags.add(tag);
        q.value.note_tags = q.note_options.filter((t) => tags.has(t));
        this.answer(req, q, { note_tags: q.value.note_tags });
    }

    setPriority(req, q, key) {
        q.value.priority = q.value.priority === key ? false : key;
        this.answer(req, q, { priority: q.value.priority });
    }

    // ------------------------------------------------------------ navigation
    selectModule(module) {
        this.load(module.code);
    }

    /** The modules the nav is showing, in the order it shows them. */
    get navModules() {
        return this.d.modules.filter((m) => (this.state.showAll ? m.total : m.applicable));
    }

    /** Still owed answers. A module is finished when every question it shows is answered. */
    unfinished(module) {
        return (module.answered || 0) < (module.questions || 0);
    }

    get missing() {
        return this.navModules.filter((m) => this.unfinished(m));
    }

    get atLastModule() {
        const mods = this.navModules;
        return !!mods.length && mods[mods.length - 1].code === this.state.moduleCode;
    }

    /** Whether the assessment can go for review — the server's answer, not ours. */
    get canSend() {
        return !!(this.d && this.d.header && this.d.header.can_send);
    }

    /**
     * What the forward button says.
     *
     * At the end of the model it stops being "next" and becomes whatever is actually
     * left to do: the first module still missing answers, or — when there is nothing
     * missing — sending the whole thing for review, which is what somebody who has just
     * finished came here to do. It only offers that when the server says it may: the
     * preparer, from draft, with the whole of it answered.
     */
    get nextLabel() {
        if (!this.atLastModule) {
            return "الموديول التالي";
        }
        const left = this.missing.length;
        if (left) {
            return `أكمل الناقص (${left})`;
        }
        return this.canSend ? "أرسل للمراجعة" : "عُد إلى البداية";
    }

    get nextIsSend() {
        return this.atLastModule && !this.missing.length && this.canSend;
    }

    async onNext() {
        if (this.nextIsSend) {
            await this.sendForReview();
            return;
        }
        this.nextModule(1);
    }

    /** Hand it to whoever reviews it, through the one guarded way in. */
    async sendForReview() {
        if (this.sending) {
            return;
        }
        this.sending = true;
        try {
            await this.orm.call("azm.dashboard", "submit_my_work", [], {
                res_model: "azm.fin.assessment",
                assessment_id: this.d.header.id,
            });
            await this.load();   // so the header reads "with the reviewer"
        } finally {
            this.sending = false;
        }
    }

    /**
     * Step through the modules, wrapping round at the ends.
     *
     * The last module's "next" used to do nothing at all — the reader reached the end
     * of the model and the button simply stopped answering. It wraps now, and it wraps
     * to the first module still missing answers rather than to the top, because at the
     * end of a pass what is left to do is behind you, not in front.
     */
    nextModule(step) {
        const mods = this.navModules;
        const at = mods.findIndex((m) => m.code === this.state.moduleCode);
        const to = at + step;
        if (to >= 0 && to < mods.length) {
            this.load(mods[to].code);
            return;
        }
        // wrapped: the rest of the model in the direction of travel, this one aside
        const rest = step > 0
            ? [...mods.slice(0, at), ...mods.slice(at + 1)]
            : [...mods.slice(at + 1), ...mods.slice(0, at)].reverse();
        const target = rest.find((m) => this.unfinished(m)) || rest[0];
        if (target) {
            this.load(target.code);
        }
    }

    toggleShowAll() {
        this.state.showAll = !this.state.showAll;
        this.load();
    }

    toggleOnlyOpen() {
        this.state.onlyOpen = !this.state.onlyOpen;
    }

    /** Show only what the reviewer sent back to be answered again. */
    toggleOnlyReturned() {
        this.state.onlyReturned = !this.state.onlyReturned;
    }

    togglePrompts(topic) {
        this.state.openPrompts[topic.id] = !this.state.openPrompts[topic.id];
    }

    setTab(tab) {
        this.state.tab = tab;
        this.refreshOutput();
    }

    setScope(scope) {
        this.state.scope = scope;
        this.refreshOutput();
    }

    openRecord() {
        this.flushAll();
        this.actionService.doAction({
            type: "ir.actions.act_window", res_model: MODEL, res_id: this.assessmentId, views: [[false, "form"]],
        });
    }

    openEvidence(req) {
        this.flushAll();
        this.actionService.doAction({
            type: "ir.actions.act_window", res_model: "azm.fin.answer", res_id: req.answer_id,
            views: [[false, "form"]], target: "new", name: req.title,
        }, { onClose: () => this.load() });
    }

    // ------------------------------------------------------------ view helpers
    get filtering() {
        return this.state.onlyOpen || this.state.onlyReturned || !!this.needle;
    }

    /** نص البحث بعد تسوية المسافات وحالة الأحرف — فليست من الكود ولا من الاسم. */
    get needle() {
        return (this.state.search || "").trim().toLowerCase();
    }

    /** يُطابَق المتطلب بكوده ومرجعه وعنوانه ونص أسئلته وخياراتها.
     *
     * بنصّ السؤال أيضًا، لأن من يبحث عن «تعارض المصالح» يعرف ما يريده ولا يعرف
     * بالضرورة تحت أي متطلب وُضع.
     */
    matches(req) {
        const needle = this.needle;
        if (!needle) {
            return true;
        }
        const parts = [req.code, req.req_id, req.tree_ref, req.title, req.question];
        for (const question of req.questions || []) {
            parts.push(question.label, question.key, question.hint);
        }
        return parts.some((part) => (part || "").toLowerCase().includes(needle));
    }

    /** ينتقل إلى أول متطلب لم يكتمل — «انتقال للسؤال التالي الناقص». */
    goToNextOpen(from) {
        const all = this.d.topics.flatMap((t) => this.topicRequirements(t));
        const start = from ? all.findIndex((r) => r.code === from) + 1 : 0;
        const next = all.slice(start).find((r) => !r.done) || all.find((r) => !r.done);
        if (next) {
            document.querySelector(`[data-req="${next.code}"]`)
                ?.scrollIntoView({ block: "start", behavior: "smooth" });
        }
        return next;
    }

    get openCount() {
        return this.d.topics.reduce(
            (n, topic) => n + this.topicRequirements(topic).filter((r) => !r.done).length, 0);
    }

    clearSearch() {
        this.state.search = "";
    }

    /** عدد ما طابق البحث في هذا الموديول، ليقول للقارئ ما لا يراه. */
    get found() {
        if (!this.needle) {
            return null;
        }
        return this.d.topics.reduce(
            (n, topic) => n + topic.requirements.filter((r) => this.matches(r)).length, 0);
    }

    visibleTopics() {
        if (!this.filtering) {
            return this.d.topics;
        }
        // a topic earns its place by what survives the filters, so the two can be
        // used together without one of them quietly winning
        return this.d.topics.filter((t) => this.topicRequirements(t).length);
    }

    topicRequirements(topic) {
        let requirements = topic.requirements;
        if (this.state.onlyReturned) {
            requirements = requirements.filter((r) => r.returned);
        }
        if (this.state.onlyOpen) {
            requirements = requirements.filter((r) => !r.done);
        }
        if (this.needle) {
            requirements = requirements.filter((r) => this.matches(r));
        }
        return requirements;
    }

    /** How many returned parts are in the module being looked at, as against the
     * whole assessment — what came back may be under a module the reader is not on. */
    returnedHere() {
        return this.d.topics.reduce(
            (n, topic) => n + topic.requirements.filter((r) => r.returned).length, 0);
    }

    specific(req) {
        return req.questions.filter((q) => q.visible && !UNIFIED_ROLES.includes(q.role));
    }

    unified(req) {
        return req.questions.filter((q) => q.visible && UNIFIED_ROLES.includes(q.role));
    }

    hiddenCount(req) {
        return req.questions.filter((q) => !q.visible).length;
    }

    isChosen(q, option) {
        return q.qtype === "multi" ? q.value.option_ids.includes(option.id) : q.value.option_id === option.id;
    }

    mainOptions(q) {
        return q.options.filter((o) => !FALLBACK.includes(o.kind));
    }

    fallbackOptions(q) {
        return q.options.filter((o) => FALLBACK.includes(o.kind));
    }

    roleLabel(q) {
        return { main: "رئيسي", follow: "تابع", status: "الوضع الحالي", impl: "وسيلة التنفيذ",
                 rule: "حالة القاعدة", target: "التوجه المستهدف" }[q.role];
    }

    stateLabel(req) {
        const st = this.d.states.find((s) => s.key === req.state);
        return st ? st.name : "";
    }

    moduleStatus(module) {
        const total = this.state.showAll ? module.total : module.applicable;
        if (!total) {
            return "none";
        }
        if (module.done === total) {
            return "full";
        }
        return module.answered ? "partial" : "unknown";
    }

    /** نسبة الإنجاز، أو null إذا لم يكن ثمّة ما يُنجَز.
     *
     * المقام هو الأسئلة المنطبقة؛ فإن كان صفرًا فلا نسبة. وكانت تُعرض صفرًا —
     * فيقرأ القارئ «0٪» عن موديول لا ينطبق منه شيء على كيانه، وهو حكم بالتقصير
     * حيث لا تقصير. لا أسئلة منطبقة ليست نسبة، وتُقال كما هي.
     */
    /** النسبة كما حسبها الخادم — و null حين لا يوجد ما يُنجَز. */
    modulePercent(module) {
        return module.percent;
    }

    /** هل لهذا الموديول ما يُنجَز أصلًا؟ يقرأ حكم الخادم لا يعيد استنتاجه. */
    moduleHasWork(module) {
        return module.percent !== null && module.percent !== undefined;
    }
}

registry.category("actions").add("azm_fin_workspace", AzmFinWorkspace);
