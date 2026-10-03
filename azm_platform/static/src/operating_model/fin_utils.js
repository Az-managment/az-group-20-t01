import { _t } from "@web/core/l10n/translation";

export const FIN_PAGE_ACTION = "azm_platform.action_azm_fin_dashboard";
export const FIN_ASSESSMENT_ACTION = "azm_operating_model.azm_fin_assessment_action";
export const FIN_GAP_ACTION = "azm_operating_model.azm_fin_gap_action";
export const FIN_STATE_COLORS = {
    full: "#16a34a", partial: "#f59e0b", unavailable: "#64748b", na: "#cbd5e1", open: "#e2e8f0",
};

export function finStateLabel(key) {
    return {
        full: _t("Fully applied"),
        partial: _t("Partially applied"),
        unavailable: _t("Not available yet"),
        na: _t("Not applicable"),
        open: _t("Not answered yet"),
    }[key] || key;
}

/** Open the financial inventory portal of an assessment, on a module / requirement when given. */
export function openFinWorkspace(actionService, assessmentId, moduleCode = false, name = "", requirementCode = false) {
    return actionService.doAction({
        type: "ir.actions.client",
        tag: "azm_fin_workspace",
        name: name || _t("Financial inventory"),
        params: { assessment_id: assessmentId, module_code: moduleCode || false, requirement_code: requirementCode || false },
    });
}

export function openFinPage(actionService, { companyId = false } = {}) {
    return actionService.doAction(FIN_PAGE_ACTION, { additionalContext: { azm_om_company_id: companyId } });
}

function pctLabel(value) {
    return value === null || value === undefined ? "—" : `${Math.round(value)}%`;
}

/** Tiles of the financial-model section on the Home and entity pages. */
export function finSummaryKpis(fin) {
    const k = fin.kpis;
    return [
        { key: "assessments", label: _t("Financial assessments"), value: k.assessments, sub: _t("%s approved", k.approved) },
        { key: "completion", label: _t("Inventory completion"), value: pctLabel(k.completion), meter: k.completion },
        { key: "maturity", label: _t("Maturity"), value: pctLabel(k.maturity), meter: k.maturity },
        { key: "requirements", label: _t("Requirements"), value: k.requirements, sub: _t("%s modules", k.modules) },
        { key: "gaps", label: _t("Gaps"), value: k.gaps, sub: _t("%s not available yet", k.unavailable) },
        { key: "entities", label: _t("Entities covered"), value: `${k.entities_covered}/${k.entities}`, sub: _t("%s approved", k.entities_approved) },
    ];
}
