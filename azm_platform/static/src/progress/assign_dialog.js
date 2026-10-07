import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";

/**
 * توزيع الأجزاء · Assign parts — who answers which part of one model.
 *
 * This used to be a jump to the backend list of azm.assignment, which asked somebody
 * who was looking at a model on التقدّم to rebuild from scratch the thing they had in
 * front of them: which entity, which model, which parts are already in somebody's
 * hands. The form opens over the page instead, already knowing all three.
 *
 * It saves one part at a time rather than collecting a whole form and writing it at
 * the end. Handing a part over is a decision in itself and it is made part by part;
 * one save per decision also means a refused one — somebody taken off the entity, a
 * part that is not this model's — costs only that part rather than the lot.
 */
export class AzmAssignDialog extends Component {
    static template = "azm_platform.AssignDialog";
    static components = { Dialog };
    // Owl 3 takes the schema here, not through a static field, which it ignores
    props = useProps({
        rows: t.array(),
        // the model to go straight into; without one the form asks which
        row: t.any().optional(null),
        onChanged: t.function().optional(),
        close: t.function(),
    });

    setup() {
        this.orm = useService("orm");
        this.state = proxy({
            // the model being divided; null while one is being chosen
            model: null,
            parts: [],
            candidates: [],
            canWrite: false,
            loading: false,
            busy: false,
            error: "",
            // the part whose people are being changed, and what is ticked for it
            editing: null,
            chosen: {},
        });
        onWillStart(async () => {
            if (this.props.row) {
                await this.pick(this.props.row);
            }
        });
    }

    /** The models this reader could divide, grouped the way the page groups them. */
    get groups() {
        const groups = [];
        for (const row of this.props.rows) {
            let group = groups.find((g) => g.id === row.entity_id);
            if (!group) {
                group = { id: row.entity_id, name: row.entity, rows: [] };
                groups.push(group);
            }
            group.rows.push(row);
        }
        return groups;
    }

    async pick(row) {
        this.state.model = { ...row };
        this.state.editing = null;
        this.state.loading = true;
        this.state.error = "";
        try {
            const out = await this.orm.call("azm.dashboard", "assignable_parts", [], {
                res_model: row.res_model,
                assessment_id: row.id,
            });
            this.state.parts = out.parts;
            this.state.candidates = out.candidates;
            this.state.canWrite = out.can_write;
        } catch (error) {
            this.state.error = this.messageOf(error);
        } finally {
            this.state.loading = false;
        }
    }

    /** Back to the list of models, so one dialog can divide more than one of them. */
    backToModels() {
        this.state.model = null;
        this.state.parts = [];
        this.state.editing = null;
        this.state.error = "";
    }

    partKey(part) {
        return `${part.level}:${part.id}`;
    }

    isEditing(part) {
        return this.state.editing === this.partKey(part);
    }

    editPart(part) {
        if (this.isEditing(part)) {
            this.state.editing = null;
            return;
        }
        this.state.editing = this.partKey(part);
        this.state.chosen = Object.fromEntries(part.user_ids.map((id) => [id, true]));
    }

    isPicked(user) {
        return !!this.state.chosen[user.id];
    }

    togglePerson(user) {
        if (this.state.chosen[user.id]) {
            delete this.state.chosen[user.id];
        } else {
            this.state.chosen[user.id] = true;
        }
    }

    pickedCount() {
        return Object.keys(this.state.chosen).length;
    }

    /** Save one part. Saving nobody takes the part back — which is what the rest of
     * the system reads as "this stays with whoever prepares the assessment", so it is
     * offered plainly rather than hidden behind an unticked box. */
    async savePart(part) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        this.state.error = "";
        try {
            const out = await this.orm.call("azm.dashboard", "set_part_assignment", [], {
                res_model: this.state.model.res_model,
                assessment_id: this.state.model.id,
                level: part.level,
                part_id: part.id,
                user_ids: Object.keys(this.state.chosen).map(Number),
            });
            if (this.props.onChanged) {
                this.props.onChanged(out.progress);
            }
            this.state.editing = null;
            await this.pick(this.state.model);
        } catch (error) {
            this.state.error = this.messageOf(error);
        } finally {
            this.state.busy = false;
        }
    }

    messageOf(error) {
        return (error && error.data && error.data.message)
            || (error && error.message) || "تعذّر حفظ التوزيع.";
    }
}
