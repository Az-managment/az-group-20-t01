import { _t } from "@web/core/l10n/translation";


export const OM_PAGE_ACTION = "azm_platform.action_azm_om_dashboard";
export const OM_HUB_ACTION = "azm_platform.action_azm_om_hub";
export const OM_ASSESSMENT_ACTION = "azm_operating_model.azm_assessment_action";
export const OM_FINDING_ACTION = "azm_operating_model.azm_finding_action";
export const OM_QUESTION_ACTION = "azm_operating_model.azm_question_action";

export const DOMAIN_KEYS = ["governance", "procurement", "financial"];
export const DOMAIN_TONES = { governance: "purple", procurement: "blue", financial: "green" };
export const DOMAIN_ICONS = { governance: "account_balance", procurement: "shopping_cart", financial: "payments" };

export function domainLabel(key) {
    return {
        governance: _t("Governance"),
        procurement: _t("Procurement Operations"),
        financial: _t("Financial"),
    }[key] || _t("All domains");
}

export function domainHint(key) {
    return {
        governance: _t("Ownership, policy, segregation of duties, delegation"),
        procurement: _t("Request, stock, vendors, quotations, award, order, receipt"),
        financial: _t("Budget, invoices, advances, payment and closing"),
    }[key] || "";
}

export function stageStatusLabel(status) {
    return {
        full: _t("Fully applied"),
        partial: _t("Partially applied"),
        none: _t("Not applied"),
        unknown: _t("Not answered yet"),
    }[status] || "";
}

export function qtypeLabel(qtype) {
    return { select: _t("Single choice"), multi: _t("Multiple choice"), number: _t("Number") }[qtype] || qtype;
}

export function pct(value) {
    return value === null || value === undefined || value === false ? "—" : `${Math.round(value)}%`;
}

export function bar(value) {
    return Math.max(0, Math.min(100, Math.round(value || 0)));
}

/** Open the Operating Model page, optionally narrowed on a domain / company. */
export function openOmPage(actionService, { domain = false, companyId = false } = {}) {
    return actionService.doAction(OM_PAGE_ACTION, {
        additionalContext: { azm_om_domain: domain, azm_om_company_id: companyId },
    });
}

/** Open the answer workspace of an assessment, on a given stage when provided. */
export function openWorkspace(actionService, assessmentId, stageId = false, name = "") {
    return actionService.doAction({
        type: "ir.actions.client",
        tag: "azm_workspace",
        name: name || _t("Answer workspace"),
        params: { assessment_id: assessmentId, stage_id: stageId || false },
    });
}

export function openFinding(actionService, findingId) {
    return actionService.doAction({
        type: "ir.actions.act_window",
        res_model: "azm.finding",
        res_id: findingId,
        views: [[false, "form"]],
    });
}

/** Small KPI tiles used by the Home page and entity page sections. */
export function omSummaryKpis(om) {
    const k = om.kpis;
    return [
        { key: "assessments", label: _t("Assessments"), value: k.assessments, sub: _t("%s approved", k.approved) },
        { key: "completion", label: _t("Answer completion"), value: pct(k.completion), meter: k.completion },
        { key: "certainty", label: _t("Answer certainty"), value: pct(k.certainty), meter: k.certainty },
        { key: "questions", label: _t("Questions"), value: k.questions, sub: _t("%s question areas", k.stages) },
        { key: "risks", label: _t("Risks triggered"), value: k.risks, sub: _t("%s risk rules", k.rules) },
        { key: "findings", label: _t("Open findings"), value: k.findings_open, sub: _t("%s high", k.findings_high) },
        { key: "entities", label: _t("Entities covered"), value: `${k.entities_covered}/${k.entities}`, sub: _t("%s approved", k.entities_approved) },
    ];
}

export function omSummaryDomains(om) {
    return om.domains.map((d) => ({
        ...d,
        label: domainLabel(d.key),
        tone: DOMAIN_TONES[d.key],
        icon: DOMAIN_ICONS[d.key],
    }));
}
