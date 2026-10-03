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
        });
        onWillStart(() => this.load());
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

    nextStage(step) {
        const stages = this.state.data.stages;
        const idx = stages.findIndex((s) => s.id === this.state.stageId) + step;
        if (idx >= 0 && idx < stages.length) {
            this.load(stages.at(idx).id);
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
