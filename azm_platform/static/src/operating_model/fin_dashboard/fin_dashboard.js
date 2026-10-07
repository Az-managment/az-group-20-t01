import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { KeepLast } from "@web/core/utils/concurrency";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { AzmDonutChart } from "@azm_platform/components/donut_chart";
import { entityImageUrl } from "@azm_platform/components/utils";
import { bar, pct } from "../om_utils";
import { FIN_ASSESSMENT_ACTION, FIN_STATE_COLORS, finStateLabel, openFinWorkspace } from "../fin_utils";
import { AzmOmDetail } from "../detail/om_detail";

/**
 * AZM Platform · Unified Financial Model page (النموذج المالي الموحد).
 * KPIs, one card per financial module, answer templates, applicability, entities and gaps.
 * Data: azm.dashboard.get_financial_model_data() — follows the user's access rights.
 */
export class AzmFinDashboard extends Component {
    static template = "azm_platform.FinDashboard";
    static components = { AzmDonutChart, AzmOmDetail };
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.keepLast = new KeepLast();
        const ctx = this.props.action?.context || {};
        this.state = proxy({
            loaded: false,
            busy: false,
            data: null,
            source: false,
            profile: false,
            entityId: false,
            assessmentId: false,
            companyId: ctx.azm_om_company_id || false,
            search: "",
            // what is behind a figure, shown beside the page
            detail: null,
        });
        this.pct = pct;
        this.bar = bar;
        onWillStart(() => this.load());
    }

    async load() {
        this.state.busy = true;
        try {
            const data = await this.keepLast.add(
                this.orm.call("azm.dashboard", "get_financial_model_data", [], {
                    entity_id: this.state.entityId || false,
                    assessment_id: this.state.assessmentId || false,
                    company_id: this.state.companyId || false,
                    source: this.state.source || false,
                    profile: this.state.profile || false,
                })
            );
            this.state.data = data;
            this.state.assessmentId = data.filters?.assessment_id || false;
        } finally {
            this.state.busy = false;
            this.state.loaded = true;
        }
    }

    get d() {
        return this.state.data;
    }
    get k() {
        return this.d.kpis;
    }

    get sourceTabs() {
        const k = this.k;
        return [
            { key: false, label: _t("All requirements"), icon: "apps", count: this.state.source ? null : k.requirements },
            { key: "FIN", label: _t("Finance (FIN)"), icon: "payments", count: this.state.source === "FIN" ? k.requirements : null },
            { key: "HRF", label: _t("HR finance (HRF)"), icon: "group", count: this.state.source === "HRF" ? k.requirements : null },
        ];
    }

    get kpis() {
        const k = this.k;
        return [
            { key: "assessments", label: _t("Financial assessments"), value: k.assessments, icon: "assignment", tone: "blue",
                sub: _t("%(approved)s approved · %(review)s in review · %(draft)s draft", { approved: k.approved, review: k.review, draft: k.draft }),
                onClick: () => this.openAssessments() },
            { key: "completion", label: _t("Inventory completion"), value: pct(k.completion), icon: "pie_chart", tone: "teal", meter: k.completion,
                sub: _t("%(done)s of %(applicable)s applicable requirements", { done: k.done, applicable: k.applicable }) },
            { key: "maturity", label: _t("Maturity"), value: pct(k.maturity), icon: "verified", tone: "green", meter: k.maturity,
                sub: _t("%(full)s fully applied out of %(n)s existing practices", { full: k.full, n: k.full + k.partial + k.unavailable }) },
            { key: "questions", label: _t("Questions answered"), value: `${k.answered_questions}/${k.questions}`, icon: "checklist", tone: "teal",
                meter: k.question_completion,
                sub: _t("%s visible questions of the applicable requirements", k.questions) },
            { key: "requirements", label: _t("Requirements in the model"), value: k.requirements, icon: "list_alt", tone: "indigo",
                sub: _t("%(m)s modules · %(t)s topics · %(q)s questions · %(fin)s FIN · %(hrf)s HRF", { m: k.modules, t: k.topics, q: k.catalogue_questions, fin: k.fin_requirements, hrf: k.hrf_requirements }),
                onClick: () => this.openRequirements(false) },
            { key: "gaps", label: _t("Gaps"), value: k.gaps, icon: "warning", tone: "orange",
                sub: _t("%(p)s partially applied · %(u)s not implemented · %(k)s unknown", { p: k.partial, u: k.unavailable, k: k.unknown }),
                onClick: () => this.openGaps(false) },
            { key: "na", label: _t("Not applicable"), value: k.na, icon: "flag", tone: "slate",
                sub: _t("each one needs a reason and a review") },
            { key: "open", label: _t("Not answered yet"), value: k.open, icon: "question_mark", tone: "purple",
                sub: _t("%s answers with evidence attached", k.evidence) },
            { key: "entities", label: _t("Entities covered"), value: `${k.entities_covered}/${k.entities}`, icon: "business", tone: "slate",
                sub: _t("%s with an approved assessment", k.entities_approved) },
        ];
    }

    get stateBar() {
        const items = this.d.charts.states;
        const total = items.reduce((s, x) => s + x.count, 0) || 1;
        return items.map((x) => ({ ...x, width: (100 * x.count) / total, label: finStateLabel(x.id) }));
    }

    get modules() {
        const term = this.state.search.trim().toLowerCase();
        return this.d.modules
            .filter((m) => m.requirements)
            .filter((m) => !term || `${m.code} ${m.name}`.toLowerCase().includes(term))
            .map((m) => {
                const total = m.applicable || 1;
                return {
                    ...m,
                    statusLabel: {
                        complete: _t("Complete"), in_progress: _t("In progress"),
                        not_started: _t("Not started"), not_applicable: _t("Not applicable to the entity"),
                    }[m.status],
                    stack: ["full", "partial", "unavailable", "unknown", "na", "open"].filter((s) => m[s]).map((s) => ({
                        key: s, width: (100 * m[s]) / total, color: FIN_STATE_COLORS[s], count: m[s], label: finStateLabel(s),
                    })),
                };
            });
    }

    get profileRows() {
        const max = Math.max(1, ...this.d.profiles.map((p) => p.requirements));
        return this.d.profiles.map((p) => ({ ...p, width: (100 * p.requirements) / max, gapWidth: (100 * p.gaps) / max }));
    }
    get scopeRows() {
        const max = Math.max(1, ...this.d.scopes.map((s) => s.requirements));
        return this.d.scopes.map((s) => ({ ...s, width: (100 * s.requirements) / max }));
    }
    get entities() {
        return this.d.entities.map((e) => ({
            ...e,
            logoUrl: e.company && e.company.has_logo ? entityImageUrl(e.company.id, "logo", "64x64", e.company.unique) : false,
            statusLabel: { approved: _t("Approved"), in_progress: _t("In progress"), not_started: _t("Not started") }[e.status],
            statusClass: { approved: "active", in_progress: "in_progress", not_started: "not_started" }[e.status],
        }));
    }
    get donutStates() {
        return _t("Requirements");
    }
    get donutAssessments() {
        return _t("Assessments");
    }
    get donutEmpty() {
        return _t("No data yet");
    }
    get companyName() {
        const row = this.d.entities.find((e) => e.company && e.company.id === this.state.companyId);
        return row ? row.company.name : _t("Selected company");
    }

    // ------------------------------------------------------------ filters
    setSource(source) {
        this.state.source = source;
        this.load();
    }
    onProfile(ev) {
        this.state.profile = ev.target.value || false;
        this.load();
    }
    onEntity(ev) {
        this.state.entityId = parseInt(ev.target.value) || false;
        this.state.assessmentId = false;
        this.load();
    }
    onAssessment(ev) {
        this.state.assessmentId = parseInt(ev.target.value) || false;
        this.load();
    }
    onSearch(ev) {
        this.state.search = ev.target.value;
    }
    clearCompany() {
        this.state.companyId = false;
        this.state.entityId = false;
        this.state.assessmentId = false;
        this.load();
    }

    // ------------------------------------------------------------ navigation
    get scopeAssessmentIds() {
        return this.d.assessments.map((a) => a.id);
    }
    openUnified(kind) {
        const xmlid = kind === "register" ? "azm_platform.action_azm_om_register"
            : "azm_platform.action_azm_om_assessments";
        this.action.doAction(xmlid, { additionalContext: { azm_model: "financial" } });
    }

    openHub() {
        this.action.doAction("azm_platform.action_azm_om_hub");
    }

    get currentModel() {
        return "financial";
    }
    openFinancialModel() {}
    openOperatingModel() {
        this.action.doAction("azm_platform.action_azm_om_dashboard");
    }
    openAssessments(entityId = false) {
        const context = { search_default_current: 1 };
        if (entityId) {
            context.search_default_entity_id = entityId;
        }
        this.action.doAction(FIN_ASSESSMENT_ACTION, { additionalContext: context });
    }
    openAssessment(row) {
        openFinWorkspace(this.action, row.id, false, row.name);
    }
    openEntity(entity) {
        if (entity.assessment_id) {
            openFinWorkspace(this.action, entity.assessment_id, false, entity.name);
        } else {
            this.openAssessments(entity.id);
        }
    }
    openModule(module) {
        if (this.state.assessmentId) {
            const a = this.d.assessments.find((x) => x.id === this.state.assessmentId);
            openFinWorkspace(this.action, this.state.assessmentId, module.code, a ? a.name : module.name);
        } else {
            this.openRequirements(module);
        }
    }
    // ------------------------------------------------- what is behind a figure
    /** Show rows beside the page rather than swapping the page for a list view. */
    showDetail(kind, scope, heading) {
        this.state.detail = { kind, scope, heading };
    }

    closeDetail() {
        this.state.detail = null;
    }

    openRequirements(module) {
        this.showDetail("requirements", {
            module_code: module ? module.code : false,
            source: this.state.source || false,
            profile: this.state.profile || false,
        }, module ? `${_t("Requirements")} · ${module.name}` : _t("Financial requirements"));
    }
    openGaps(module) {
        this.showDetail("gaps", {
            assessment_ids: this.scopeAssessmentIds,
            module_code: module ? module.code : false,
        }, module ? `${_t("Gaps")} · ${module.name}` : _t("Financial gaps"));
    }
    openGap(gap) {
        openFinWorkspace(this.action, gap.assessment_id, gap.module_code, gap.entity, gap.code);
    }
    newAssessment() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "azm.fin.assessment",
            views: [[false, "form"]],
            context: this.state.entityId ? { default_entity_id: this.state.entityId } : {},
        });
    }
}

registry.category("actions").add("azm_fin_dashboard", AzmFinDashboard);
