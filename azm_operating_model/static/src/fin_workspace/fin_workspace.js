import { Component, markup, onWillStart, onWillUnmount, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { KeepLast } from "@web/core/utils/concurrency";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const MODEL = "azm.fin.assessment";

/**
 * Unified financial model · answer workspace.
 * Same layout as the procurement workspace: module rail · requirements · live documents.
 * Rendering lives server side (azm.fin.assessment.workspace_*); this component
 * shows the payload and saves one answer at a time.
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
            busy: false,
            saving: false,
            openTables: {},
            showQuestion: {},
            showHelp: {},
            detailsOpen: false,
        });
        this.timers = {};
        onWillStart(() => this.load());
        onWillUnmount(() => this.flushAll());
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
        this.state.detailsOpen = false;
        if (this.focusCode) {
            const req = data.requirements.find((r) => r.code === this.focusCode);
            if (req) {
                this.state.openTables[req.answer_id] = true;
            }
            this.focusCode = false;
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

    // ------------------------------------------------------------ saving
    async save(req, vals) {
        if (this.readonly) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(MODEL, "workspace_save", [[this.assessmentId], req.answer_id, vals], {
                module_code: this.state.moduleCode,
                tab: this.state.tab,
                scope: this.state.scope,
            });
            const target = this.d.requirements.find((r) => r.answer_id === req.answer_id);
            if (target) {
                for (const key of ["state", "impl", "branches", "done", "attachments"]) {
                    target[key] = result.answer[key];
                }
            }
            this.d.header = result.header;
            this.d.modules = result.modules;
            this.state.output = markup(result.output);
        } finally {
            this.state.saving = false;
        }
    }

    debounce(req, key, vals) {
        const id = `${req.answer_id}:${key}`;
        clearTimeout(this.timers[id]?.handle);
        this.timers[id] = { req, vals, handle: setTimeout(() => this.flush(id), 700) };
    }

    flush(id) {
        const pending = this.timers[id];
        if (pending) {
            clearTimeout(pending.handle);
            delete this.timers[id];
            this.save(pending.req, pending.vals);
        }
    }

    flushAll() {
        Object.keys(this.timers).forEach((id) => this.flush(id));
    }

    // ------------------------------------------------------------ handlers
    selectModule(module) {
        this.load(module.code);
    }

    nextModule(step) {
        const mods = this.d.modules.filter((m) => (this.state.showAll ? m.total : m.applicable));
        const idx = mods.findIndex((m) => m.code === this.state.moduleCode) + step;
        if (idx >= 0 && idx < mods.length) {
            this.load(mods[idx].code);
        }
    }

    setState(req, key) {
        req.state = req.state === key ? false : key;
        this.save(req, { state: req.state });
    }

    toggleImpl(req, value) {
        const impl = new Set(req.impl);
        impl.has(value) ? impl.delete(value) : impl.add(value);
        req.impl = [...impl];
        this.save(req, { impl: req.impl });
    }

    // ---------------------------------------------------------------------
    // Questionnaire. The standard «الوضع الحالي» and «وسيلة التنفيذ» questions
    // keep their own controls above, so only the requirement-specific ones and
    // the two trailing scales are rendered here.
    // ---------------------------------------------------------------------
    questionsOf(req) {
        return (req.questions || []).filter((q) => !["state", "impl"].includes(q.role));
    }

    // Same split as the procurement workspace: the real answers are chips,
    // «لا أعرف» / «غير مدرج» / «لا يوجد» sit apart as soft chips.
    mainOptions(question) {
        return question.options.filter((o) => o.kind === "normal");
    }

    fallbackOptions(question) {
        return question.options.filter((o) => o.kind !== "normal");
    }

    isAnswered(question) {
        if (question.qtype === "multi") {
            return question.option_ids.length > 0;
        }
        if (question.qtype === "number") {
            return !!question.value_number;
        }
        if (question.qtype === "table") {
            return question.table.length > 0;
        }
        return !!question.option_id;
    }

    toggleHelp(question) {
        this.state.showHelp[question.line_id] = !this.state.showHelp[question.line_id];
    }

    pickQuestionSelect(req, question, ev) {
        const id = parseInt(ev.target.value, 10);
        this.answerQuestion(req, question, { option_id: id || false });
    }

    isPicked(question, option) {
        return question.qtype === "multi"
            ? question.option_ids.includes(option.id)
            : question.option_id === option.id;
    }

    async answerQuestion(req, question, vals) {
        if (this.readonly) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                MODEL, "workspace_answer_question",
                [[this.assessmentId], question.line_id, vals],
                { module_code: this.state.moduleCode, tab: this.state.tab, scope: this.state.scope },
            );
            // Answering may reveal or hide a follow-up, and the server decides
            // which, so the refreshed question list is taken wholesale.
            const fresh = result.requirements.find((r) => r.answer_id === req.answer_id);
            const target = this.d.requirements.find((r) => r.answer_id === req.answer_id);
            if (fresh && target) {
                for (const key of ["questions", "state", "impl", "current", "future", "done"]) {
                    target[key] = fresh[key];
                }
            }
            this.d.header = result.header;
            this.d.modules = result.modules;
            this.state.output = markup(result.output);
        } finally {
            this.state.saving = false;
        }
    }

    pickQuestionOption(req, question, option) {
        if (question.qtype !== "multi") {
            const same = question.option_id === option.id;
            const vals = { option_id: same ? false : option.id };
            if (question.qtype === "table" && !same) {
                // «لا يوجد» and the grid are mutually exclusive answers
                vals.table = [];
            }
            this.answerQuestion(req, question, vals);
            return;
        }
        const ids = new Set(question.option_ids);
        const exclusive = ["unknown", "not_listed", "none"];
        if (ids.has(option.id)) {
            ids.delete(option.id);
        } else if (exclusive.includes(option.kind)) {
            ids.clear();
            ids.add(option.id);
        } else {
            for (const other of question.options) {
                if (exclusive.includes(other.kind)) {
                    ids.delete(other.id);
                }
            }
            ids.add(option.id);
        }
        this.answerQuestion(req, question, { option_ids: [...ids] });
    }

    onQuestionNumber(req, question, ev) {
        this.answerQuestion(req, question, { value_number: parseFloat(ev.target.value) || 0 });
    }

    questionRows(question) {
        const width = question.columns.length;
        const rows = question.table.length ? question.table : [Array(width).fill("")];
        return rows.map((row) => Array.from({ length: width }, (_v, i) => row[i] || ""));
    }

    onQuestionCell(req, question, rowIndex, colIndex, ev) {
        const rows = this.questionRows(question);
        rows[rowIndex][colIndex] = ev.target.value;
        question.table = rows;
        this.answerQuestion(req, question, { table: rows, option_id: false });
    }

    addQuestionRow(req, question) {
        const rows = this.questionRows(question);
        rows.push(Array(question.columns.length).fill(""));
        this.answerQuestion(req, question, { table: rows });
    }

    removeQuestionRow(req, question, rowIndex) {
        const rows = this.questionRows(question).filter((_r, i) => i !== rowIndex);
        this.answerQuestion(req, question, { table: rows });
    }

    onText(req, key, ev) {
        req[key] = ev.target.value;
        this.debounce(req, key, { [key]: req[key] });
    }

    rows(req) {
        const cols = req.schema.columns.length;
        const rows = req.table.length ? req.table : [Array(cols).fill("")];
        return rows.map((row) => Array.from({ length: cols }, (_v, i) => row[i] || ""));
    }

    onCell(req, rowIndex, colIndex, ev) {
        const rows = this.rows(req);
        rows[rowIndex][colIndex] = ev.target.value;
        req.table = rows;
        ev.target.tagName === "SELECT" ? this.save(req, { table: rows }) : this.debounce(req, "table", { table: rows });
    }

    addRow(req) {
        req.table = [...this.rows(req), Array(req.schema.columns.length).fill("")];
        this.save(req, { table: req.table });
    }

    removeRow(req, rowIndex) {
        req.table = this.rows(req).filter((_r, i) => i !== rowIndex);
        this.save(req, { table: req.table });
    }

    onBranch(req, index, ev) {
        const branches = req.schema.branches.map((_b, i) => req.branches[i] || "");
        branches[index] = ev.target.value;
        req.branches = branches;
        this.save(req, { branches });
    }

    toggleTable(req) {
        this.state.openTables[req.answer_id] = !this.state.openTables[req.answer_id];
    }

    toggleQuestion(req) {
        this.state.showQuestion[req.answer_id] = !this.state.showQuestion[req.answer_id];
    }

    toggleDetails() {
        this.state.detailsOpen = !this.state.detailsOpen;
    }

    toggleShowAll() {
        this.state.showAll = !this.state.showAll;
        this.load();
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
    profileGroups() {
        const groups = [];
        for (const p of this.d.profiles) {
            const items = this.d.requirements.filter((r) => r.profile === p.key);
            if (items.length) {
                groups.push({ key: p.key, title: `${p.key} · ${p.name}`, desc: p.desc, items });
            }
        }
        return groups;
    }

    moduleStatus(module) {
        const total = this.state.showAll ? module.total : module.applicable;
        if (!total) {
            return "none";
        }
        if (module.done === total) {
            return "full";
        }
        return module.done ? "partial" : "unknown";
    }

    modulePercent(module) {
        const total = this.state.showAll ? module.total : module.applicable;
        return total ? Math.round((100 * module.done) / total) : 0;
    }

    isTextNeeded(req) {
        return { full: "current", partial: "gap", unavailable: "future", na: "reason" }[req.state];
    }

    detailShape(shape) {
        return (shape || "")
            .replace("multi:", "متعدد: ")
            .replace("select:", "اختيار: ")
            .replace("table:", "جدول: ")
            .replace("states", "الحالات الأربع")
            .replace("files", "رفع ملفات");
    }
}

registry.category("actions").add("azm_fin_workspace", AzmFinWorkspace);
