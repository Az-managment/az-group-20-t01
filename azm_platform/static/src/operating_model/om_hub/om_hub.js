import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { entityImageUrl } from "@azm_platform/components/utils";
import { bar, pct } from "../om_utils";

/**
 * AZM Platform · Operating Models (landing page).
 * Each operating model is shown as a file: its KPIs on the cover, click to open its data.
 */
export class AzmOmHub extends Component {
    static template = "azm_platform.OmHub";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ loaded: false, data: null });
        this.pct = pct;
        this.bar = bar;
        onWillStart(async () => {
            this.state.data = await this.orm.call("azm.dashboard", "get_operating_models_hub", []);
            this.state.loaded = true;
        });
    }

    get d() {
        return this.state.data;
    }

    get totals() {
        const t = this.d.totals;
        return [
            { key: "models", label: _t("Operating models"), value: t.models, icon: "folder", tone: "indigo",
                sub: _t("%(u)s stages / modules · %(i)s questions", { u: t.units, i: t.items }) },
            { key: "assessments", label: _t("Assessments"), value: t.assessments, icon: "assignment", tone: "blue",
                sub: _t("%s approved", t.approved) },
            { key: "completion", label: _t("Overall completion"), value: pct(t.completion), icon: "pie_chart", tone: "teal",
                meter: t.completion, sub: _t("weighted by assessments") },
            { key: "issues", label: _t("Open findings & gaps"), value: t.issues, icon: "warning", tone: "orange",
                sub: _t("risks of the procurement cycle + financial gaps") },
            { key: "entities", label: _t("Entities covered"), value: `${t.entities_covered}/${t.entities}`, icon: "business", tone: "slate",
                sub: _t("with at least one assessment") },
        ];
    }

    get models() {
        return this.d.models.map((m) => ({
            ...m,
            label: m.key === "procurement" ? _t("Procurement cycle") : _t("Unified financial model"),
            desc: m.key === "procurement"
                ? _t("From the purchase request to closing: policy, procedure, authority and risks.")
                : _t("Inventory of the financial requirements of each entity and design of the target model."),
            structure: m.key === "procurement"
                ? _t("%(u)s stages · %(i)s questions", { u: m.units, i: m.items })
                : _t("%(u)s modules · %(i)s questions", { u: m.units, i: m.items }),
            qualityLabel: m.key === "procurement" ? _t("Answer certainty") : _t("Maturity"),
            issuesLabel: m.key === "procurement" ? _t("Open findings") : _t("Gaps"),
            issuesSub: m.key === "procurement" ? _t("%s high", m.issues_sub) : _t("%s not applicable", m.issues_sub),
            partsLabel: m.key === "procurement" ? _t("Completion by domain") : _t("Requirements by source"),
        }));
    }

    partLabel(model, part) {
        const labels = {
            governance: _t("Governance"), procurement: _t("Procurement Operations"), financial: _t("Financial"),
            FIN: _t("Finance (FIN)"), HRF: _t("HR finance (HRF)"),
        };
        return labels[part.code] || part.label;
    }

    get entities() {
        return this.d.entities.map((e) => ({
            ...e,
            logoUrl: e.company && e.company.has_logo ? entityImageUrl(e.company.id, "logo", "64x64", e.company.unique) : false,
        }));
    }

    statusLabel(status) {
        return { approved: _t("Approved"), in_progress: _t("In progress"), not_started: _t("Not started") }[status] || "";
    }
    statusClass(status) {
        return { approved: "active", in_progress: "in_progress", not_started: "not_started" }[status] || "not_started";
    }

    /** What lives inside each model: its assessments and its register. */
    links(m) {
        if (m.key === "procurement") {
            return [
                { key: "assessments", icon: "assignment", label: _t("Assessments"), count: m.assessments,
                    action: "azm_platform.action_azm_om_assessments" },
                { key: "register", icon: "flag", label: _t("Risk Register"), count: m.issues,
                    action: "azm_platform.action_azm_om_register" },
            ];
        }
        return [
            { key: "assessments", icon: "checklist", label: _t("Financial Assessments"), count: m.assessments,
                action: "azm_platform.action_azm_om_assessments" },
            { key: "gaps", icon: "warning", label: _t("Financial Gaps"), count: m.issues,
                action: "azm_platform.action_azm_om_register" },
        ];
    }

    openLink(link, model) {
        this.action.doAction(link.action, { additionalContext: { azm_model: model.key } });
    }

    open(model) {
        this.action.doAction(model.action);
    }

    /** A header given a button's role has to answer a button's keys. */
    openOnKey(ev, model) {
        if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            this.open(model);
        }
    }

    openByKey(key) {
        const model = this.d.models.find((m) => m.key === key);
        if (model) {
            this.open(model);
        }
    }
}

registry.category("actions").add("azm_om_hub", AzmOmHub);
