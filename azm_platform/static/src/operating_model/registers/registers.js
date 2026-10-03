import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { relativeTime } from "@azm_platform/components/utils";
import { openWorkspace } from "../om_utils";
import { openFinWorkspace } from "../fin_utils";

const NATIVE = {
    assessments: { procurement: "azm_operating_model.azm_assessment_action", financial: "azm_operating_model.azm_fin_assessment_action" },
    register: { procurement: "azm_operating_model.azm_finding_action", financial: "azm_operating_model.azm_fin_gap_action" },
};

/**
 * Assessments and Risk Register of every operating model in one list
 * (procurement cycle + unified financial model). Follows each user's access rights.
 */
export class AzmUnifiedList extends Component {
    static template = "azm_platform.UnifiedList";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.kind = this.props.action.tag === "azm_om_register" ? "register" : "assessments";
        const ctx = this.props.action.context || {};
        this.state = proxy({
            loaded: false, data: null, model: ctx.azm_model || false, entityId: false, status: "",
            search: "", all: false,
        });
        onWillStart(() => this.load());
    }

    async load() {
        const method = this.kind === "register" ? "get_unified_register" : "get_unified_assessments";
        const kwargs = this.kind === "register" ? { include_closed: this.state.all } : { include_archived: this.state.all };
        this.state.data = await this.orm.call("azm.dashboard", method, [], kwargs);
        this.state.loaded = true;
    }

    get d() {
        return this.state.data;
    }
    get isRegister() {
        return this.kind === "register";
    }
    get title() {
        return this.isRegister ? _t("Risk Register") : _t("Assessments");
    }
    get subtitle() {
        return this.isRegister
            ? _t("Procurement risk findings and financial gaps of every entity, in one register")
            : _t("Procurement and financial assessments of every entity, in one list");
    }
    modelLabel(model) {
        return model === "procurement" ? _t("Procurement cycle") : _t("Unified financial model");
    }

    get modelTabs() {
        const rows = this.d.rows;
        const tabs = [{ key: false, label: _t("All operating models"), icon: "folder", count: rows.length }];
        if (this.d.models.procurement) {
            tabs.push({ key: "procurement", label: this.modelLabel("procurement"), icon: "shopping_cart",
                count: rows.filter((r) => r.model === "procurement").length });
        }
        if (this.d.models.financial) {
            tabs.push({ key: "financial", label: this.modelLabel("financial"), icon: "payments",
                count: rows.filter((r) => r.model === "financial").length });
        }
        return tabs;
    }

    get statuses() {
        const seen = new Map();
        for (const r of this.d.rows) {
            if (!this.state.model || r.model === this.state.model) {
                seen.set(r.state, r.state_label);
            }
        }
        return [...seen].map(([key, label]) => ({ key, label }));
    }

    get rows() {
        const term = this.state.search.trim().toLowerCase();
        return this.d.rows.filter((r) =>
            (!this.state.model || r.model === this.state.model) &&
            (!this.state.entityId || r.entity_id === this.state.entityId) &&
            (!this.state.status || r.state === this.state.status) &&
            (!term || JSON.stringify([r.name, r.code, r.title, r.detail, r.entity, r.area]).toLowerCase().includes(term))
        ).map((r) => ({ ...r, when: r.updated ? relativeTime(r.updated) : "" }));
    }

    get kpis() {
        const rows = this.rows;
        const proc = rows.filter((r) => r.model === "procurement");
        const fin = rows.filter((r) => r.model === "financial");
        if (this.isRegister) {
            return [
                { key: "all", label: _t("Items in the register"), value: rows.length, icon: "flag", tone: "slate" },
                { key: "risks", label: _t("Procurement risk findings"), value: proc.length, icon: "shopping_cart", tone: "blue",
                    sub: _t("%s high (score ≥ 15)", proc.filter((r) => r.score >= 15).length) },
                { key: "gaps", label: _t("Financial gaps"), value: fin.filter((r) => r.state === "partial").length, icon: "payments", tone: "green",
                    sub: _t("partially applied requirements") },
                { key: "future", label: _t("Not implemented"), value: fin.filter((r) => r.state === "unavailable").length, icon: "warning", tone: "orange",
                    sub: _t("financial requirements to design") },
            ];
        }
        const avg = rows.length ? Math.round(rows.reduce((s, r) => s + r.progress, 0) / rows.length) : null;
        return [
            { key: "all", label: _t("Assessments"), value: rows.length, icon: "assignment", tone: "slate",
                sub: _t("%s approved", rows.filter((r) => r.state === "approved").length) },
            { key: "proc", label: this.modelLabel("procurement"), value: proc.length, icon: "shopping_cart", tone: "blue",
                sub: _t("%s risk indicators", proc.reduce((s, r) => s + r.issues, 0)) },
            { key: "fin", label: this.modelLabel("financial"), value: fin.length, icon: "payments", tone: "green",
                sub: _t("%s gaps", fin.reduce((s, r) => s + r.issues, 0)) },
            { key: "progress", label: _t("Average completion"), value: avg === null ? "—" : `${avg}%`, icon: "pie_chart", tone: "teal",
                meter: avg },
        ];
    }

    // ------------------------------------------------------------ filters
    setModel(model) {
        this.state.model = model;
        this.state.status = "";
    }
    onEntity(ev) {
        this.state.entityId = parseInt(ev.target.value) || false;
    }
    onStatus(ev) {
        this.state.status = ev.target.value;
    }
    onSearch(ev) {
        this.state.search = ev.target.value;
    }
    toggleAll() {
        this.state.all = !this.state.all;
        this.load();
    }

    // ------------------------------------------------------------ navigation
    openRow(row) {
        if (this.isRegister && row.model === "financial") {
            return openFinWorkspace(this.action, row.assessment_id, row.area_code, row.entity, row.code);
        }
        this.action.doAction({ type: "ir.actions.act_window", res_model: row.res_model, res_id: row.id, views: [[false, "form"]] });
    }
    openWorkspace(row) {
        if (row.model === "financial") {
            return openFinWorkspace(this.action, row.id, false, row.name);
        }
        openWorkspace(this.action, row.id, false, row.name);
    }
    openNative(model) {
        this.action.doAction(NATIVE[this.kind][model]);
    }
    newAssessment(model) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: model === "financial" ? "azm.fin.assessment" : "azm.assessment",
            views: [[false, "form"]],
            context: this.state.entityId ? { default_entity_id: this.state.entityId } : {},
        });
    }
    scoreClass(score) {
        return score >= 15 ? "o_high" : score >= 8 ? "o_mid" : score ? "o_low" : "";
    }
}

registry.category("actions").add("azm_om_assessments", AzmUnifiedList);
registry.category("actions").add("azm_om_register", AzmUnifiedList);
