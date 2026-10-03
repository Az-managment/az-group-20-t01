import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { KeepLast } from "@web/core/utils/concurrency";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { AzmDonutChart } from "@azm_platform/components/donut_chart";
import { entityImageUrl } from "@azm_platform/components/utils";
import {
    DOMAIN_ICONS,
    DOMAIN_KEYS,
    DOMAIN_TONES,
    OM_ASSESSMENT_ACTION,
    bar,
    domainHint,
    domainLabel,
    openFinding as openFindingRecord,
    openWorkspace,
    pct,
    qtypeLabel,
    stageStatusLabel,
} from "../om_utils";

const STATUS_COLORS = { full: "#16a34a", partial: "#f59e0b", none: "#ef4444", unknown: "#cbd5e1" };
const GROUP_COLORS = ["#2563eb", "#7c3aed", "#0d9488"];

/**
 * AZM Platform · Operating Model page.
 * KPIs, domain summaries (Governance / Procurement / Financial), one card per
 * question area (stage), entities, assessments and the risk register.
 * Every figure comes from azm.dashboard.get_operating_model_data().
 */
export class AzmOmDashboard extends Component {
    static template = "azm_platform.OmDashboard";
    static components = { AzmDonutChart };
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
            domain: ctx.azm_om_domain || false,
            companyId: ctx.azm_om_company_id || false,
            entityId: false,
            assessmentId: false,
            search: "",
            sort: "sequence",
        });
        this.pct = pct;
        this.bar = bar;
        onWillStart(() => this.load());
    }

    async load() {
        this.state.busy = true;
        try {
            const data = await this.keepLast.add(
                this.orm.call("azm.dashboard", "get_operating_model_data", [], {
                    entity_id: this.state.entityId || false,
                    assessment_id: this.state.assessmentId || false,
                    domain: this.state.domain || false,
                    company_id: this.state.companyId || false,
                })
            );
            this.state.data = data;
            this.state.assessmentId = data.filters?.assessment_id || false;
        } finally {
            this.state.busy = false;
            this.state.loaded = true;
        }
    }

    // ------------------------------------------------------------------ getters
    get d() {
        return this.state.data;
    }
    get k() {
        return this.d.kpis;
    }
    get scopeLabel() {
        if (this.state.assessmentId) {
            const a = this.d.assessment_options.find((o) => o.id === this.state.assessmentId);
            return a ? a.name : "";
        }
        if (this.state.entityId) {
            const e = this.d.entity_options.find((o) => o.id === this.state.entityId);
            return e ? _t("All current assessments of %s", e.name) : "";
        }
        return _t("All current assessments of the group");
    }
    get domainName() {
        return domainLabel(this.state.domain);
    }
    get companyName() {
        const row = this.d.entities.find((e) => e.company && e.company.id === this.state.companyId);
        return row ? row.company.name : _t("Selected company");
    }

    get kpis() {
        const k = this.k;
        return [
            {
                key: "assessments", label: _t("Assessments"), value: k.assessments, icon: "assignment", tone: "blue",
                sub: _t("%(approved)s approved · %(review)s in review · %(draft)s draft",
                    { approved: k.approved, review: k.review, draft: k.draft }),
                onClick: () => this.openAssessments(),
            },
            {
                key: "completion", label: _t("Answer completion"), value: pct(k.completion), icon: "pie_chart", tone: "teal",
                sub: _t("%(answered)s of %(visible)s applicable questions", { answered: k.answered, visible: k.visible }),
                meter: k.completion,
            },
            {
                key: "certainty", label: _t("Answer certainty"), value: pct(k.certainty), icon: "verified", tone: "purple",
                sub: _t("%s answers are “don't know / not listed”", k.answered - k.known),
                meter: k.certainty,
            },
            {
                key: "questions", label: _t("Questions in catalogue"), value: k.questions, icon: "list_alt", tone: "indigo",
                sub: _t("%(stages)s question areas · %(common)s common", { stages: k.stages, common: k.common_questions }),
                onClick: () => this.openQuestions(false),
            },
            {
                key: "risks", label: _t("Risks triggered"), value: k.risks, icon: "warning", tone: "orange",
                sub: _t("by %s risk rules on the answers", k.rules),
            },
            {
                key: "findings", label: _t("Open findings"), value: k.findings_open, icon: "flag", tone: "red",
                sub: _t("%s high (score ≥ 15)", k.findings_high),
                onClick: () => this.openFindings({ open: true }),
            },
            {
                key: "treatment", label: _t("Treatment rate"), value: pct(k.treatment_rate), icon: "check_circle", tone: "green",
                sub: _t("%(closed)s of %(total)s findings closed with evidence", { closed: k.findings_closed, total: k.findings }),
                meter: k.treatment_rate,
            },
            {
                key: "entities", label: _t("Entities covered"), value: `${k.entities_covered}/${k.entities}`, icon: "business", tone: "slate",
                sub: _t("%(approved)s approved · %(linked)s linked to companies", { approved: k.entities_approved, linked: k.entities_linked }),
            },
        ];
    }

    get domainTabs() {
        const all = { key: false, label: _t("All domains"), icon: "apps", tone: "slate", count: this.d.domains.reduce((s, x) => s + x.stages, 0) };
        return [all, ...this.d.domains.map((x) => ({ key: x.key, label: domainLabel(x.key), icon: DOMAIN_ICONS[x.key], tone: DOMAIN_TONES[x.key], count: x.stages }))];
    }

    get domains() {
        return this.d.domains.map((x) => ({ ...x, label: domainLabel(x.key), hint: domainHint(x.key) }));
    }

    get stages() {
        const term = this.state.search.trim().toLowerCase();
        let cards = this.d.stages.map((s) => ({
            ...s,
            domainLabel: domainLabel(s.domain),
            statusLabel: stageStatusLabel(s.status),
            groupBars: this.groupBars(s),
            statusBars: this.statusBars(s.status_counts),
            typeChips: ["select", "multi", "number"].filter((t) => s.types[t]).map((t) => ({ key: t, label: qtypeLabel(t), count: s.types[t] })),
        }));
        if (term) {
            cards = cards.filter((s) => `${s.code} ${s.name} ${s.owner}`.toLowerCase().includes(term));
        }
        const sorters = {
            sequence: () => 0,
            risks: (a, b) => b.risks + b.findings_open - (a.risks + a.findings_open),
            completion: (a, b) => (a.completion ?? -1) - (b.completion ?? -1),
            questions: (a, b) => b.questions - a.questions,
        };
        return cards.sort(sorters[this.state.sort] || sorters.sequence);
    }

    groupBars(stage) {
        const total = stage.questions || 1;
        return Object.values(stage.groups).map((n, i) => ({
            key: i, width: (100 * n) / total, color: GROUP_COLORS[i], count: n,
        }));
    }

    statusBars(counts) {
        const total = Object.values(counts).reduce((s, n) => s + n, 0) || 1;
        return Object.entries(counts).filter(([, n]) => n).map(([key, n]) => ({
            key, width: (100 * n) / total, color: STATUS_COLORS[key], count: n, label: stageStatusLabel(key),
        }));
    }

    get statusLegend() {
        const mix = this.d.charts.status;
        return Object.keys(STATUS_COLORS).map((key) => ({ key, label: stageStatusLabel(key), color: STATUS_COLORS[key], count: mix[key] }));
    }
    get statusTotal() {
        return Object.values(this.d.charts.status).reduce((s, n) => s + n, 0);
    }
    get typeRows() {
        const t = this.d.charts.types;
        const max = Math.max(1, ...Object.values(t));
        return Object.entries(t).map(([key, n]) => ({ key, label: qtypeLabel(key), count: n, width: (100 * n) / max }));
    }
    get groupRows() {
        const g = this.d.charts.groups;
        const max = Math.max(1, ...Object.values(g));
        return Object.entries(g).map(([label, n], i) => ({ key: label, label, count: n, width: (100 * n) / max, color: GROUP_COLORS[i] }));
    }

    get entities() {
        return this.d.entities.map((e) => ({
            ...e,
            logoUrl: e.company && e.company.has_logo ? entityImageUrl(e.company.id, "logo", "64x64", e.company.unique) : false,
            statusLabel: { approved: _t("Approved"), in_progress: _t("In progress"), not_started: _t("Not started") }[e.status],
            statusClass: { approved: "active", in_progress: "in_progress", not_started: "not_started" }[e.status],
        }));
    }

    get donutFindingsLabel() {
        return _t("Findings");
    }
    get donutAssessmentsLabel() {
        return _t("Assessments");
    }
    get donutEmpty() {
        return _t("No data yet");
    }

    // ------------------------------------------------------------------ filters
    setDomain(domain) {
        this.state.domain = domain;
        this.load();
    }
    onEntityChange(ev) {
        this.state.entityId = parseInt(ev.target.value) || false;
        this.state.assessmentId = false;
        this.load();
    }
    onAssessmentChange(ev) {
        this.state.assessmentId = parseInt(ev.target.value) || false;
        this.load();
    }
    onSearch(ev) {
        this.state.search = ev.target.value;
    }
    onSort(ev) {
        this.state.sort = ev.target.value;
    }
    clearCompany() {
        this.state.companyId = false;
        this.state.entityId = false;
        this.state.assessmentId = false;
        this.load();
    }

    // ------------------------------------------------------------------ navigation
    get scopeAssessmentIds() {
        return this.d.assessments.map((a) => a.id);
    }

    openHub() {
        this.action.doAction("azm_platform.action_azm_om_hub");
    }

    get currentModel() {
        return "procurement";
    }

    openOperatingModel() {}

    openFinancialModel() {
        this.action.doAction("azm_platform.action_azm_fin_dashboard");
    }

    openAssessments(entityId = false) {
        const context = { search_default_current: 1 };
        if (entityId) {
            context.search_default_entity_id = entityId;
        }
        this.action.doAction(OM_ASSESSMENT_ACTION, { additionalContext: context });
    }

    openAssessment(row) {
        openWorkspace(this.action, row.id, false, row.name);
    }

    openEntity(entity) {
        if (entity.assessment_id) {
            openWorkspace(this.action, entity.assessment_id, false, entity.name);
        } else {
            this.openAssessments(entity.id);
        }
    }

    openStage(stage) {
        if (this.state.assessmentId) {
            const a = this.d.assessments.find((x) => x.id === this.state.assessmentId);
            openWorkspace(this.action, this.state.assessmentId, stage.id, a ? a.name : stage.name);
        } else {
            this.openQuestions(stage);
        }
    }

    openQuestions(stage) {
        const domain = stage
            ? [["stage_id", "=", stage.id]]
            : this.state.domain ? [["azm_domain", "=", this.state.domain]] : [];
        this.action.doAction({
            type: "ir.actions.act_window",
            name: stage ? `${_t("Questions")} · ${stage.name}` : _t("Question Catalogue"),
            res_model: "azm.question",
            views: [[false, "list"], [false, "form"]],
            domain,
            context: stage ? {} : { search_default_by_stage: 1 },
        });
    }

    openFindings({ stage = false, open = false } = {}) {
        const domain = [["assessment_id", "in", this.scopeAssessmentIds]];
        if (stage) {
            domain.push(["stage_id", "=", stage.id]);
        } else if (this.state.domain) {
            domain.push(["azm_domain", "=", this.state.domain]);
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: stage ? `${_t("Risk Register")} · ${stage.name}` : _t("Risk Register"),
            res_model: "azm.finding",
            views: [[false, "kanban"], [false, "list"], [false, "form"]],
            domain,
            context: open ? { search_default_open: 1 } : {},
        });
    }

    openFinding(finding) {
        openFindingRecord(this.action, finding.id);
    }

    newAssessment() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "azm.assessment",
            views: [[false, "form"]],
            context: this.state.entityId ? { default_entity_id: this.state.entityId } : {},
        });
    }
}

registry.category("actions").add("azm_om_dashboard", AzmOmDashboard);
