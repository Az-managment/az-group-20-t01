import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AzmDashboard } from "@azm_platform/dashboard/azm_dashboard";
import {
    OM_ASSESSMENT_ACTION,
    OM_HUB_ACTION,
    OM_PAGE_ACTION,
    bar,
    omSummaryDomains,
    omSummaryKpis,
    openFinding,
    openOmPage,
    openWorkspace,
    pct,
} from "../om_utils";
import { FIN_PAGE_ACTION, finSummaryKpis, openFinPage } from "../fin_utils";

/** AZM Home: Operating Model KPI, quick links and summary section. */
patch(AzmDashboard.prototype, {
    setup() {
        super.setup(...arguments);
        this.omPct = pct;
        this.omBar = bar;
        this.quickLinks.splice(0, 0,
            { label: _t("Operating Models"), icon: "folder", action: OM_HUB_ACTION },
            { label: _t("Assessments"), icon: "assignment", action: "azm_platform.action_azm_om_assessments" },
        );
    },

    canOpen(target) {
        if ([OM_PAGE_ACTION, OM_ASSESSMENT_ACTION].includes(target)) {
            return Boolean(this.om);
        }
        if (target === OM_HUB_ACTION || target === "azm_platform.action_azm_om_assessments") {
            return Boolean(this.om || this.fin);
        }
        if (target === FIN_PAGE_ACTION) {
            return Boolean(this.fin);
        }
        return super.canOpen(target);
    },

    get om() {
        return this.state.data?.om || false;
    },

    get kpis() {
        const kpis = super.kpis;
        const om = this.om;
        if (om) {
            kpis.push({
                key: "operating_model",
                label: _t("Operating Model"),
                value: pct(om.kpis.completion),
                sub: _t("%(n)s assessments · %(f)s open findings", { n: om.kpis.assessments, f: om.kpis.findings_open }),
                icon: "view_module",
                tone: "green",
                action: OM_PAGE_ACTION,
            });
        }
        const fin = this.fin;
        if (fin) {
            kpis.push({
                key: "financial_model",
                label: _t("Financial Model"),
                value: fin.kpis.completion === null ? "—" : `${Math.round(fin.kpis.completion)}%`,
                sub: _t("%(n)s assessments · %(g)s gaps", { n: fin.kpis.assessments, g: fin.kpis.gaps }),
                icon: "payments",
                tone: "orange",
                action: FIN_PAGE_ACTION,
            });
        }
        return kpis;
    },

    get fin() {
        return this.state.data?.fin || false;
    },

    get finKpis() {
        return finSummaryKpis(this.fin);
    },

    get finModules() {
        return this.fin.modules.filter((m) => m.requirements);
    },

    openFin() {
        openFinPage(this.action, { companyId: false });
    },

    get omKpis() {
        return omSummaryKpis(this.om);
    },

    get omDomains() {
        return omSummaryDomains(this.om);
    },

    openOm(domain = false) {
        openOmPage(this.action, { domain });
    },

    openOmAssessment(row) {
        openWorkspace(this.action, row.id, false, row.name);
    },

    openOmFinding(finding) {
        openFinding(this.action, finding.id);
    },
});
