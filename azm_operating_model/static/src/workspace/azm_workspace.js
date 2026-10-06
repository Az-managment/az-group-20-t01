import { Component, markup, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { KeepLast } from "@web/core/utils/concurrency";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const MODEL = "azm.assessment";

/**
 * AZM answer workspace: stage rail · questions as answer chips · live document.
 * All rendering logic lives server side (azm.assessment.workspace_*); this
 * component only displays the payload and sends one answer at a time.
 */
export class AzmWorkspace extends Component {
    static template = "azm_operating_model.AzmWorkspace";

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
        this.keepLast = new KeepLast();
        const action = this.props.action;
        this.assessmentId = action.params?.assessment_id || action.context?.active_id;
        this.state = proxy({
            data: null,
            stageId: null,
            tab: "book",
            scope: "stage",
            output: markup(""),
            busy: false,
            showHelp: {},
            // the part a reviewer is sending back, and the reason being typed for it
            returning: null,
            returnNote: "",
        });
        onWillStart(() => this.load());
    }

    // ------------------------------------------------------------ review
    /** Start sending a part back: this stage, or one question of it. */
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
            await this.orm.call(MODEL, "action_submit", [[this.assessmentId]]);
            await this.load();
        } finally {
            this.state.busy = false;
        }
    }

    apply(data) {
        this.state.data = data;
        this.state.stageId = data.stage.id;
        this.state.output = markup(data.output);
    }

    async load(stageId = this.state.stageId) {
        const data = await this.keepLast.add(
            this.orm.call(MODEL, "workspace_data", [[this.assessmentId]], {
                stage_id: stageId,
                tab: this.state.tab,
                scope: this.state.scope,
            })
        );
        this.apply(data);
    }

    async refreshOutput() {
        const html = await this.keepLast.add(
            this.orm.call(MODEL, "workspace_output", [[this.assessmentId]], {
                stage_id: this.state.stageId,
                tab: this.state.tab,
                scope: this.state.scope,
            })
        );
        this.state.output = markup(html);
    }

    async answer(question, values) {
        if (this.state.data.header.readonly) {
            return;
        }
        this.state.busy = true;
        try {
            const data = await this.keepLast.add(
                this.orm.call(MODEL, "workspace_answer", [[this.assessmentId], question.id], {
                    ...values,
                    stage_id: this.state.stageId,
                    tab: this.state.tab,
                    scope: this.state.scope,
                })
            );
            this.apply(data);
        } finally {
            this.state.busy = false;
        }
    }

    // ------------------------------------------------------------ handlers
    selectStage(stage) {
        this.load(stage.id);
    }

    /** Still owed answers: a stage is finished when every question it shows is answered. */
    unfinished(stage) {
        return (stage.answered || 0) < (stage.total || 0);
    }

    get missing() {
        return this.state.data.stages.filter((s) => this.unfinished(s));
    }

    get atLastStage() {
        const stages = this.state.data.stages;
        return !!stages.length && stages[stages.length - 1].id === this.state.stageId;
    }

    /** Whether the assessment can go for review — the server's answer, not ours. */
    get canSend() {
        const header = this.state.data && this.state.data.header;
        return !!(header && header.can_send);
    }

    /**
     * What the forward button says.
     *
     * At the end of the cycle it stops being "next" and becomes whatever is actually
     * left to do: the first stage still missing answers, or — when there is nothing
     * missing — sending the whole thing for review, which is what somebody who has just
     * finished came here to do. The financial workspace does the same.
     */
    get nextLabel() {
        if (!this.atLastStage) {
            return "المرحلة التالية";
        }
        const left = this.missing.length;
        if (left) {
            return `أكمل الناقص (${left})`;
        }
        return this.canSend ? "أرسل للمراجعة" : "عُد إلى البداية";
    }

    get nextIsSend() {
        return this.atLastStage && !this.missing.length && this.canSend;
    }

    async onNext() {
        if (this.nextIsSend) {
            await this.sendForReview();
            return;
        }
        this.nextStage(1);
    }

    /** Hand it to whoever reviews it, through the one guarded way in. */
    async sendForReview() {
        if (this.sending) {
            return;
        }
        this.sending = true;
        try {
            await this.orm.call("azm.dashboard", "submit_my_work", [], {
                res_model: "azm.assessment",
                assessment_id: this.state.data.header.id,
            });
            await this.load();
        } finally {
            this.sending = false;
        }
    }

    /**
     * Step through the stages, wrapping round at the ends.
     *
     * The last stage's "next" used to do nothing — the reader reached the end of the
     * cycle and the button stopped answering. It wraps now, to the first stage still
     * missing answers rather than to the top: at the end of a pass what is left to do
     * is behind you. The financial workspace does the same with its modules.
     */
    nextStage(step) {
        const stages = this.state.data.stages;
        const at = stages.findIndex((s) => s.id === this.state.stageId);
        const to = at + step;
        if (to >= 0 && to < stages.length) {
            this.load(stages.at(to).id);
            return;
        }
        const rest = step > 0
            ? [...stages.slice(0, at), ...stages.slice(at + 1)]
            : [...stages.slice(at + 1), ...stages.slice(0, at)].reverse();
        const target = rest.find((s) => this.unfinished(s)) || rest[0];
        if (target) {
            this.load(target.id);
        }
    }

    pick(question, option) {
        if (question.qtype === "multi") {
            const ids = new Set(question.option_ids);
            const special = ["unknown", "not_listed", "none"];
            if (ids.has(option.id)) {
                ids.delete(option.id);
            } else if (special.includes(option.kind)) {
                ids.clear();
                ids.add(option.id);
            } else {
                for (const o of question.options) {
                    if (special.includes(o.kind)) {
                        ids.delete(o.id);
                    }
                }
                ids.add(option.id);
            }
            this.answer(question, { option_ids: [...ids] });
        } else {
            const same = question.option_id === option.id;
            this.answer(question, { option_id: same ? false : option.id });
        }
    }

    pickSelect(question, ev) {
        const id = parseInt(ev.target.value, 10);
        this.answer(question, { option_id: Number.isNaN(id) ? false : id });
    }

    setNumber(question, ev) {
        const value = parseFloat(ev.target.value);
        this.answer(question, { value_number: Number.isNaN(value) ? 0 : value });
    }

    setNote(question, ev) {
        if (ev.target.value !== question.note) {
            this.answer(question, { note: ev.target.value });
        }
    }

    toggleHelp(question) {
        this.state.showHelp[question.id] = !this.state.showHelp[question.id];
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
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: MODEL,
            res_id: this.assessmentId,
            views: [[false, "form"]],
        });
    }

    // ------------------------------------------------------------ view helpers
    questionsOf(group) {
        return this.state.data.questions.filter((q) => q.group === group);
    }

    isChosen(question, option) {
        return question.qtype === "multi"
            ? question.option_ids.includes(option.id)
            : question.option_id === option.id;
    }

    isAnswered(question) {
        if (question.qtype === "multi") {
            return question.option_ids.length > 0;
        }
        if (question.qtype === "number") {
            return Boolean(question.value_number);
        }
        return Boolean(question.option_id);
    }

    mainOptions(question) {
        return question.options.filter((o) => !["unknown", "not_listed"].includes(o.kind));
    }

    fallbackOptions(question) {
        return question.options.filter((o) => ["unknown", "not_listed"].includes(o.kind));
    }

    stagePercent(stage) {
        return stage.total ? Math.round((100 * stage.answered) / stage.total) : 0;
    }
}

registry.category("actions").add("azm_workspace", AzmWorkspace);
