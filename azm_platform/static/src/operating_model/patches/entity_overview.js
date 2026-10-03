import { patch } from "@web/core/utils/patch";
import { AzmEntityOverview } from "@azm_platform/entity/entity_overview";
import {
    bar,
    omSummaryDomains,
    omSummaryKpis,
    openFinding,
    openOmPage,
    openWorkspace,
    pct,
} from "../om_utils";
import { finSummaryKpis, openFinPage } from "../fin_utils";

/** Entity (company) page: Operating Model section for the entities linked to this company. */
patch(AzmEntityOverview.prototype, {
    setup() {
        super.setup(...arguments);
        this.omPct = pct;
        this.omBar = bar;
    },

    get om() {
        return this.state.data?.om || false;
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
        openFinPage(this.action, { companyId: this.props.record.resId });
    },

    get omKpis() {
        return omSummaryKpis(this.om);
    },

    get omDomains() {
        return omSummaryDomains(this.om);
    },

    openOm(domain = false) {
        openOmPage(this.action, { domain, companyId: this.props.record.resId });
    },

    openOmAssessment(row) {
        openWorkspace(this.action, row.id, false, row.name);
    },

    openOmFinding(finding) {
        openFinding(this.action, finding.id);
    },

    openOmEntities() {
        this.action.doAction("azm_operating_model.azm_entity_action");
    },
});
