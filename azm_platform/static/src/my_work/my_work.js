import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { KeepLast } from "@web/core/utils/concurrency";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

/**
 * AZM Platform · مساحتي — one person's own work.
 *
 * The Home page is the group's cockpit: every entity, every model, the whole picture.
 * It is the right page for somebody who runs the group and the wrong one for somebody
 * whose job is to answer their own entity's questions. This is the other page: the
 * entities they are assigned to, how far each model has got, what is left, who has
 * their work now, what it has produced, and the projects and people around it.
 *
 * Everything it shows is already narrowed by the record rules, so a manager opening it
 * sees their own work rather than everybody's.
 */
export class AzmMyWork extends Component {
    static template = "azm_platform.MyWork";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.keepLoad = new KeepLast();
        this.state = proxy({ loaded: false, data: null, error: "",
                             sending: false, deciding: false, sent: null,
                             sendError: "",
                             // the review whose parts are being chosen, what is ticked,
                             // and the reason they are going back
                             picking: null, parts: [], chosen: {}, pickNote: "",
                             loadingParts: false });
        onWillStart(async () => {
            await this.load();
        });
    }

    async load() {
        this.state.loaded = false;
        this.state.error = "";
        try {
            this.state.data = await this.keepLoad.add(
                this.orm.call("azm.dashboard", "get_my_work", [], {})
            );
        } catch (error) {
            this.state.data = null;
            this.state.error = (error && error.data && error.data.message)
                || (error && error.message) || "تعذّر تحميل مساحتك.";
        } finally {
            this.state.loaded = true;
        }
    }

    get d() {
        return this.state.data;
    }

    /** The headline: what is still owed, across everything assigned to them. */
    get kpis() {
        const t = this.d.totals;
        const made = this.d.deliverables;
        return [
            { key: "left", label: "أسئلة متبقية", en: "Questions left", value: t.left,
                icon: "help", tone: t.left ? "orange" : "green",
                sub: t.left ? "عليك الإجابة عنها" : "لا شيء متبقٍ عليك" },
            { key: "progress", label: "نسبة الاكتمال", en: "Completion", value: `${t.progress}%`,
                icon: "donut_large", tone: "indigo", sub: "متوسط ما أنجزته" },
            { key: "ready", label: "مخرجات جاهزة", en: "Deliverables ready", value: made.ready,
                icon: "task_alt", tone: "green", sub: `من ${made.total} لدى كياناتك` },
        ];
    }

    /** Models grouped under the entity they belong to, so one entity reads as one block. */
    get byEntity() {
        const blocks = [];
        for (const entity of this.d.entities) {
            const rows = this.d.models.filter((m) => m.entity_id === entity.id);
            if (rows.length) {
                blocks.push({ entity, rows });
            }
        }
        return blocks;
    }

    // ---------------------------------------------------------------- handing it over
    /**
     * Whether this row can go for review now — worked out on the server, where the
     * whole assessment is in view.
     *
     * It used to be read off this person's own count, which is only their share once
     * the model has been divided: somebody who finished their three modules was offered
     * the button while sixteen others were untouched, and sending it would have taken
     * everybody else's unanswered work to the reviewer with it.
     */
    canSend(row) {
        return !!row.can_send;
    }

    /** Their share is done and the assessment is waiting on other people. */
    waitingOnOthers(row) {
        return !!(row.started && row.parts.length && row.left === 0 && row.whole_left
                  && row.standing && row.standing.state === "draft");
    }

    async sendForReview(row) {
        if (this.state.sending || !this.canSend(row)) {
            return;
        }
        this.state.sending = row.assessment_id;
        this.state.sendError = "";
        try {
            const out = await this.orm.call("azm.dashboard", "submit_my_work", [], {
                res_model: row.res_model,
                assessment_id: row.assessment_id,
            });
            // the page comes back with it, so the row re-reads as "with the reviewer"
            this.state.data = out.work;
            this.state.sent = { entity: row.entity, model: row.label,
                                reviewers: out.reviewers };
        } catch (error) {
            // said on the page, beside the work, rather than thrown as a dialog
            this.state.sendError = (error && error.data && error.data.message)
                || (error && error.message) || "تعذّر الإرسال للمراجعة.";
        } finally {
            this.state.sending = false;
        }
    }

    dismissSent() {
        this.state.sent = null;
        this.state.sendError = "";
    }

    // ---------------------------------------------------------------- going somewhere
    /**
     * Straight into the answering workspace, which is where the questions are.
     *
     * It used to open the assessment's form, from which the reader had to find and
     * press another button to get where they were going. Both models have their own
     * workspace and both open the same way.
     */
    // ------------------------------------------------------------ returning parts
    /** Offer the parts of one review to choose from, without opening the work first. */
    async openPicker(review) {
        if (this.state.picking && this.state.picking.id === review.id) {
            return this.closePicker();
        }
        this.state.picking = { id: review.id, res_model: review.res_model, entity: review.entity };
        this.state.parts = [];
        this.state.chosen = {};
        this.state.pickNote = "";
        this.state.loadingParts = true;
        try {
            const data = await this.orm.call("azm.dashboard", "review_parts", [], {
                res_model: review.res_model,
                assessment_id: review.id,
            });
            this.state.parts = data.parts;
        } finally {
            this.state.loadingParts = false;
        }
    }

    closePicker() {
        this.state.picking = null;
        this.state.parts = [];
        this.state.chosen = {};
        this.state.pickNote = "";
    }

    partKey(part) {
        return `${part.level}:${part.id}`;
    }

    isChosen(part) {
        return !!this.state.chosen[this.partKey(part)];
    }

    togglePart(part) {
        const key = this.partKey(part);
        if (this.state.chosen[key]) {
            delete this.state.chosen[key];
        } else {
            this.state.chosen[key] = part;
        }
    }

    chosenCount() {
        return Object.keys(this.state.chosen).length;
    }

    /** Send every chosen part back, each carrying the reason typed for them. */
    async confirmPicker() {
        const note = (this.state.pickNote || "").trim();
        const chosen = Object.values(this.state.chosen);
        if (!note || !chosen.length || !this.state.picking) {
            return;
        }
        this.state.deciding = this.state.picking.id;
        try {
            const result = await this.orm.call("azm.dashboard", "return_review_parts", [], {
                res_model: this.state.picking.res_model,
                assessment_id: this.state.picking.id,
                parts: chosen.map((part) => ({ level: part.level, id: part.id, note })),
            });
            this.closePicker();
            this.state.data = result.work;
        } finally {
            this.state.deciding = false;
        }
    }

    /** Open the assessment a returned part belongs to, so it can be dealt with. */
    openReturned(item) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            res_model: item.res_model,
            res_id: item.res_id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async openAssessment(row) {
        if (!row.assessment_id) {
            this.action.doAction(row.action);
            return;
        }
        const action = await this.orm.call("azm.dashboard", "open_my_workspace", [], {
            res_model: row.res_model,
            assessment_id: row.assessment_id,
        });
        await this.action.doAction(action);
    }

    // ---------------------------------------------------------------- reviewing
    /** Accept the answers, or send them back for more work. */
    async decide(review, accept) {
        if (this.state.deciding) {
            return;
        }
        this.state.deciding = review.id;
        this.state.sendError = "";
        try {
            const out = await this.orm.call(
                "azm.dashboard", accept ? "accept_my_review" : "return_my_review", [], {
                    res_model: review.res_model,
                    assessment_id: review.id,
                });
            this.state.data = out.work;
            this.state.sent = {
                entity: review.entity, model: review.model_label, reviewers: [],
                note: accept ? "قُبلت الإجابات واعتُمدت." : "أُعيدت للمُعد لاستكمالها.",
            };
        } catch (error) {
            this.state.sendError = (error && error.data && error.data.message)
                || (error && error.message) || "تعذّر إتمام المراجعة.";
        } finally {
            this.state.deciding = false;
        }
    }

    /** Read the answers being reviewed, in the workspace they were written in. */
    async openReviewWorkspace(review) {
        const action = await this.orm.call("azm.dashboard", "open_my_workspace", [], {
            res_model: review.res_model,
            assessment_id: review.id,
        });
        await this.action.doAction(action);
    }

    openDeliverables() {
        this.action.doAction("azm_platform.action_azm_outputs_library");
    }

    openTree(row) {
        this.action.doAction(
            row.key === "procurement" ? "azm_platform.action_azm_proc_tree"
                                      : "azm_platform.action_azm_fin_tree",
            { additionalContext: { azm_company_id: this.companyOf(row) } }
        );
    }

    companyOf(row) {
        const entity = this.d.entities.find((e) => e.id === row.entity_id);
        return (entity && entity.company_id) || undefined;
    }

    openRecord(model, id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: model,
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("azm_my_work", AzmMyWork);
