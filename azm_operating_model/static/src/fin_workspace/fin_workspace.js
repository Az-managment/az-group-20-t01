import { Component, markup, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { KeepLast } from "@web/core/utils/concurrency";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const MODEL = "azm.fin.assessment";
// An option with a kind is a fallback — «لا أعرف», «غير مدرج», «لا يوجد» —
// and is mutually exclusive with the real answers.
const FALLBACK = ["unknown", "not_listed", "none"];
const OTHER = "أخرى";
// Typing into a textarea saves on a pause rather than on every keystroke.
const TYPING_PAUSE = 700;

export class AzmFinWorkspace extends Component {
    static template = "azm_operating_model.FinWorkspace";

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.keepLast = new KeepLast();
        const params = this.props.action.params || {};
        this.assessmentId = params.assessment_id || this.props.action.context?.active_id;
        this.state = proxy({
            data: null,
            moduleCode: params.module_code || null,
            tab: "book",
            scope: "module",
            output: markup(""),
            showAll: false,
            busy: false,
            saving: false,
            openPrompts: {},
            openTables: {},
        });
        this.timers = {};
        onWillStart(() => this.load());
    }

    get d() {
        return this.state.data;
    }

    get readonly() {
        return !this.d || this.d.header.readonly;
    }

    // ----------------------------------------------------------------- load
    async load(moduleCode = this.state.moduleCode) {
        this.state.busy = true;
        try {
            const data = await this.keepLast.add(
                this.orm.call(MODEL, "workspace_data", [[this.assessmentId]], {
                    module_code: moduleCode,
                    tab: this.state.tab,
                    scope: this.state.scope,
                    show_all: this.state.showAll,
                }),
            );
            this.state.data = data;
            this.state.moduleCode = data.module.code;
            this.state.output = markup(data.output);
        } finally {
            this.state.busy = false;
        }
    }

    async selectModule(code) {
        await this.flush();
        this.load(code);
    }

    async selectTab(key) {
        this.state.tab = key;
        this.state.output = markup(
            await this.orm.call(MODEL, "workspace_output", [[this.assessmentId]], {
                module_code: this.state.moduleCode, tab: key, scope: this.state.scope,
            }),
        );
    }

    async setScope(scope) {
        this.state.scope = scope;
        await this.selectTab(this.state.tab);
    }

    async toggleShowAll() {
        this.state.showAll = !this.state.showAll;
        await this.load();
    }

    togglePrompts(topic) {
        this.state.openPrompts[topic.id] = !this.state.openPrompts[topic.id];
    }

    toggleTable(question) {
        this.state.openTables[question.id] = !this.state.openTables[question.id];
    }

    // ----------------------------------------------------------------- save
    /** Apply a server result in place, so answering does not reset the page. */
    _apply(result) {
        for (const topic of this.d.topics) {
            const at = topic.requirements.findIndex(
                (r) => r.answer_id === result.requirement.answer_id);
            if (at !== -1) {
                topic.requirements[at] = result.requirement;
                break;
            }
        }
        this.d.header = result.header;
        this.d.modules = result.modules;
        this.state.output = markup(result.output);
    }

    async answer(req, question, vals) {
        if (this.readonly) {
            return;
        }
        this.state.saving = true;
        try {
            // The whole requirement comes back: answering may reveal or hide a
            // follow-up, and the server decides which.
            this._apply(await this.orm.call(
                MODEL, "workspace_answer",
                [[this.assessmentId], req.answer_id, question.id, vals],
                { module_code: this.state.moduleCode, tab: this.state.tab, scope: this.state.scope },
            ));
        } finally {
            this.state.saving = false;
        }
    }

    async setRequirement(req, vals) {
        if (this.readonly) {
            return;
        }
        this.state.saving = true;
        try {
            this._apply(await this.orm.call(
                MODEL, "workspace_requirement", [[this.assessmentId], req.answer_id, vals],
                { module_code: this.state.moduleCode, tab: this.state.tab, scope: this.state.scope },
            ));
        } finally {
            this.state.saving = false;
        }
    }

    /** Hold a text edit briefly so a sentence is one save, not thirty. */
    debounce(key, run) {
        clearTimeout(this.timers[key]);
        this.timers[key] = setTimeout(run, TYPING_PAUSE);
    }

    async flush() {
        const pending = Object.values(this.timers).filter(Boolean);
        if (!pending.length) {
            return;
        }
        for (const [key, timer] of Object.entries(this.timers)) {
            clearTimeout(timer);
            delete this.timers[key];
        }
        await this.load();
    }

    // ------------------------------------------------------------ questions
    questionsOf(req) {
        return (req.questions || []).filter((q) => q.visible);
    }

    mainOptions(question) {
        return question.options.filter((o) => !FALLBACK.includes(o.kind));
    }

    fallbackOptions(question) {
        return question.options.filter((o) => FALLBACK.includes(o.kind));
    }

    isPicked(question, option) {
        return question.qtype === "multi"
            ? question.value.option_ids.includes(option.id)
            : question.value.option_id === option.id;
    }

    pick(req, question, option) {
        if (question.qtype !== "multi") {
            const same = question.value.option_id === option.id;
            this.answer(req, question, { option_id: same ? false : option.id });
            return;
        }
        const ids = new Set(question.value.option_ids);
        if (ids.has(option.id)) {
            ids.delete(option.id);
        } else if (FALLBACK.includes(option.kind)) {
            ids.clear();
            ids.add(option.id);
        } else {
            for (const other of question.options) {
                if (FALLBACK.includes(other.kind)) {
                    ids.delete(other.id);
                }
            }
            ids.add(option.id);
        }
        this.answer(req, question, { option_ids: [...ids] });
    }

    pickFromSelect(req, question, ev) {
        const id = parseInt(ev.target.value, 10);
        this.answer(req, question, { option_id: id || false });
    }

    setNumber(req, question, ev) {
        const raw = ev.target.value;
        this.answer(req, question, { number: raw === "" ? null : parseFloat(raw) });
    }

    // ---------------------------------------------------------------- table
    rows(question) {
        const width = question.columns.length;
        const rows = question.value.table.length ? question.value.table : [Array(width).fill("")];
        return rows.map((row) => Array.from({ length: width }, (_v, i) => row[i] || ""));
    }

    /** A column says what it holds, so a date gets a picker and not a text box. */
    cellType(col) {
        return col.type === "date" || col.type === "number" ? col.type : "text";
    }

    onCell(req, question, rowIndex, colIndex, ev) {
        const rows = this.rows(question);
        rows[rowIndex][colIndex] = ev.target.value;
        question.value.table = rows;
        if (ev.target.tagName === "SELECT") {
            this.answer(req, question, { table: rows });
        } else {
            this.debounce(`t${question.id}`, () => this.answer(req, question, { table: rows }));
        }
    }

    addRow(req, question) {
        const rows = this.rows(question);
        rows.push(Array(question.columns.length).fill(""));
        this.answer(req, question, { table: rows });
    }

    removeRow(req, question, rowIndex) {
        const rows = this.rows(question).filter((_r, i) => i !== rowIndex);
        this.answer(req, question, { table: rows });
    }

    // ----------------------------------------------------------------- note
    hasTag(question, tag) {
        return question.value.note_tags.includes(tag);
    }

    /** «أخرى» is what opens the free-text box, so it is kept visible. */
    wantsFreeText(question) {
        return this.hasTag(question, OTHER);
    }

    toggleTag(req, question, tag) {
        const tags = new Set(question.value.note_tags);
        tags.has(tag) ? tags.delete(tag) : tags.add(tag);
        this.answer(req, question, { note_tags: [...tags] });
    }

    onNote(req, question, ev) {
        const note = ev.target.value;
        question.value.note = note;
        this.debounce(`n${question.id}`, () => this.answer(req, question, { note }));
    }

    setPriority(req, question, key) {
        const same = question.value.priority === key;
        this.answer(req, question, { priority: same ? false : key });
    }

    // ---------------------------------------------------------- requirement
    toggleNa(req) {
        this.setRequirement(req, { na: !req.na, reason: req.na ? false : req.reason });
    }

    setReason(req, reason) {
        this.setRequirement(req, { reason });
    }

    progressOf(req) {
        return req.q_total ? Math.round((100 * req.q_answered) / req.q_total) : 0;
    }
}

registry.category("actions").add("azm_fin_workspace", AzmFinWorkspace);
