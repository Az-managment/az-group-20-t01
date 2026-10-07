import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { AzmDonutChart } from "@azm_platform/components/donut_chart";
import { canOpen, entityImageUrl, formatPercent, loadAzmRights, relativeTime } from "@azm_platform/components/utils";

const ACTIONS = {
    entities: "azm_platform.action_azm_entity",
    structure: "azm_platform.action_azm_entity_hierarchy",
    employees: "hr.open_view_employee_list_my",
    departments: "hr.hr_department_kanban_action",
    projects: "project.open_view_project_all",
    tasks: "project.action_view_all_task",
    documents: "azm_platform.action_azm_documents",
};

export class AzmDashboard extends Component {
    static template = "azm_platform.Dashboard";
    static components = { AzmDonutChart };
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = proxy({
            loaded: false,
            data: null,
            // what is waiting for this reader, fetched beside the figures
            attention: null,
            taskFilter: "all",
            question: "",
            answer: "",
            answerOk: true,
            asking: false,
            rights: null,
        });
        this.suggestions = [
            _t("Compare two entities"),
            _t("Explain the current state"),
            _t("Which entity needs attention?"),
            _t("Summarize overdue work"),
        ];
        this.quickLinks = [
            { label: _t("Employees"), icon: "group", action: ACTIONS.employees },
            { label: _t("Departments & Teams"), icon: "account_tree", action: ACTIONS.departments },
            { label: _t("Projects"), icon: "rocket_launch", action: ACTIONS.projects },
            { label: _t("Tasks"), icon: "task", action: ACTIONS.tasks },
            { label: _t("Documents"), icon: "description", action: ACTIONS.documents },
            { label: _t("Group Structure"), icon: "business", action: ACTIONS.structure },
        ];
        onWillStart(() => this.load());
    }

    async load() {
        const [data, attention, rights] = await Promise.all([
            this.orm.call("azm.dashboard", "get_dashboard_data", []),
            this.orm.call("azm.dashboard", "home_attention", []),
            loadAzmRights(),
        ]);
        this.state.attention = attention;
        this.state.rights = rights;
        this.state.data = data;
        this.state.loaded = true;
    }

    /** Whether the current user may open a target (hides links to apps they have no rights on). */
    canOpen(target) {
        return canOpen(this.state.rights, target);
    }

    // ---------------------------------------------------------------- the header
    /** The time of day, so the page opens by speaking to the person reading it. */
    get greeting() {
        const hour = new Date().getHours();
        if (hour < 12) {
            return _t("Good morning");
        }
        return hour < 18 ? _t("Good afternoon") : _t("Good evening");
    }

    get userName() {
        return (this.state.data && this.state.data.user && this.state.data.user.name) || "";
    }

    /** What the figures on this page are counted over, said rather than assumed. */
    get scopeLabel() {
        const scope = this.state.attention && this.state.attention.scope;
        if (!scope) {
            return "";
        }
        return scope.entities === 1 && scope.label
            ? scope.label
            : _t("%s entities in scope", scope.entities);
    }

    // ------------------------------------------------- what is waiting, in order
    /** The lists that actually have something in them, each with where it is acted on.
     * A reader with nothing waiting sees that said plainly rather than three empty
     * headings. */
    get attentionGroups() {
        const a = this.state.attention;
        if (!a) {
            return [];
        }
        const groups = [
            { key: "returned", label: _t("Sent back to you"), icon: "undo", tone: "orange",
                hint: _t("Answer these before the rest of the assessment reopens"),
                ...a.returned, action: "azm_platform.action_azm_my_work" },
            { key: "reviews", label: _t("Waiting for your review"), icon: "fact_check", tone: "blue",
                hint: _t("Sent to you by whoever prepared them"),
                ...a.reviews, action: "azm_platform.action_azm_my_work" },
            { key: "overdue", label: _t("Overdue tasks"), icon: "schedule", tone: "red",
                hint: _t("Assigned to you, past their deadline"),
                ...a.overdue, action: ACTIONS.tasks },
        ];
        return groups.filter((group) => group.count > 0);
    }

    get nothingWaiting() {
        return !!this.state.attention && this.attentionGroups.length === 0;
    }

    // -------------------------------------------------------- where the work lives
    /** The product grouped by what somebody came to do, rather than one flat row of
     * every destination the platform has. */
    get workspaces() {
        const groups = [
            {
                key: "organisation", label: _t("Organization"), icon: "business",
                links: [
                    { label: _t("Entities"), hint: _t("Every entity of the group"), action: ACTIONS.entities },
                    { label: _t("Group Structure"), hint: _t("How the entities relate"), action: ACTIONS.structure },
                    { label: _t("Employees"), hint: _t("People across the group"), action: ACTIONS.employees },
                    { label: _t("Departments & Teams"), hint: _t("How people are organised"), action: ACTIONS.departments },
                ],
            },
            {
                key: "models", label: _t("Operating models"), icon: "view_module",
                links: [
                    { label: _t("Operating Models"), hint: _t("Procurement and financial models"), action: "azm_platform.action_azm_om_hub" },
                    { label: _t("Assessments"), hint: _t("What each entity has answered"), action: "azm_platform.action_azm_om_assessments" },
                    { label: _t("Risk Register"), hint: _t("Findings and financial gaps"), action: "azm_platform.action_azm_om_register" },
                    { label: _t("Progress"), hint: _t("Who is doing what, and how far"), action: "azm_platform.action_azm_progress" },
                ],
            },
            {
                key: "execution", label: _t("Execution"), icon: "rocket_launch",
                links: [
                    { label: _t("Projects"), hint: _t("Initiatives in progress"), action: ACTIONS.projects },
                    { label: _t("Tasks"), hint: _t("Work to be delivered"), action: ACTIONS.tasks },
                ],
            },
            {
                key: "knowledge", label: _t("Knowledge"), icon: "menu_book",
                links: [
                    { label: _t("Documents"), hint: _t("What the group has on file"), action: ACTIONS.documents },
                    { label: _t("Outputs Library"), hint: _t("Every deliverable produced"), action: "azm_platform.action_azm_library" },
                    { label: _t("Trees"), hint: _t("The models read as a tree"), action: "azm_platform.action_azm_trees" },
                ],
            },
        ];
        // a group whose every destination is closed to this reader is not shown empty
        return groups
            .map((group) => ({ ...group, links: group.links.filter((l) => this.canOpen(l.action)) }))
            .filter((group) => group.links.length);
    }

    get visibleQuickLinks() {
        return this.quickLinks.filter((link) => this.canOpen(link.action));
    }

    get k() {
        return this.state.data.kpis;
    }

    get steps() {
        const k = this.k;
        return [
            { key: "entities", label: _t("Entities"), hint: _t("Companies of the group"), value: k.entities,
                icon: "business", color: "blue", action: ACTIONS.entities },
            { key: "people", label: _t("People"), hint: _t("Employees in HR"), value: k.employees,
                icon: "group", color: "teal", action: ACTIONS.employees },
            { key: "teams", label: _t("Teams"), hint: _t("Departments & managers"), value: k.departments,
                icon: "account_tree", color: "purple", action: ACTIONS.departments },
            { key: "projects", label: _t("Projects"), hint: _t("Initiatives in progress"), value: k.projects,
                icon: "rocket_launch", color: "orange", action: ACTIONS.projects },
            { key: "tasks", label: _t("Open Tasks"), hint: _t("Work to be delivered"), value: k.open_tasks,
                icon: "task", color: "green", action: ACTIONS.tasks },
            { key: "documents", label: _t("Documents"), hint: _t("Files & evidence"), value: k.documents,
                icon: "description", color: "indigo", action: ACTIONS.documents },
            { key: "progress", label: _t("Completion"), hint: _t("Closed tasks / all tasks"),
                value: formatPercent(k.completion, k.completion !== null),
                icon: "bar_chart", color: "slate", action: ACTIONS.entities },
        ].map((step, index) => ({ ...step, index: index + 1 }));
    }

    get kpis() {
        const k = this.k;
        return [
            { key: "entities", label: _t("Total Entities"), value: k.entities,
                sub: _t("%s active on the platform", k.active), icon: "business", tone: "blue", action: ACTIONS.entities },
            { key: "employees", label: _t("Employees"), value: k.employees,
                sub: _t("%s departments", k.departments), icon: "group", tone: "teal", action: ACTIONS.employees },
            { key: "projects", label: _t("Projects"), value: k.projects,
                sub: "", icon: "rocket_launch", tone: "purple", action: ACTIONS.projects },
            { key: "tasks", label: _t("Open Tasks"), value: k.open_tasks,
                sub: k.overdue_tasks ? _t("%s overdue", k.overdue_tasks) : "", icon: "task", tone: "indigo", action: ACTIONS.tasks },
            { key: "completion", label: _t("Overall Completion"), value: formatPercent(k.completion, k.completion !== null),
                sub: "", icon: "bar_chart", tone: "orange", action: ACTIONS.entities },
        ];
    }

    get infoCards() {
        const k = this.k;
        return [
            { key: "org", icon: "account_tree", tone: "blue", title: _t("Organization"),
                subtitle: _t("Companies, departments and people"), action: ACTIONS.structure,
                items: [_t("%s entities", k.entities), _t("%s departments", k.departments), _t("%s employees", k.employees)] },
            { key: "work", icon: "rocket_launch", tone: "purple", title: _t("Execution"),
                subtitle: _t("Projects and tasks across the group"), action: ACTIONS.tasks,
                items: [_t("%s projects", k.projects), _t("%s open tasks", k.open_tasks), _t("%s overdue tasks", k.overdue_tasks)] },
            { key: "knowledge", icon: "description", tone: "green", title: _t("Knowledge"),
                subtitle: _t("Documents and evidence"), action: ACTIONS.documents,
                items: [_t("%s documents", k.documents), _t("Linked to records and companies"), _t("Searchable from one place")] },
        ];
    }

    get entities() {
        return this.state.data.entities.map((e) => ({
            ...e,
            logoUrl: e.has_logo ? entityImageUrl(e.id, "logo", "64x64", e.unique) : false,
            progressLabel: formatPercent(e.progress, e.has_data),
        }));
    }

    get donutLabel() {
        return _t("Employees");
    }

    get donutEmptyLabel() {
        return _t("No data yet");
    }

    get tasks() {
        const filter = this.state.taskFilter;
        return this.state.data.tasks.filter((task) =>
            filter === "all" || (filter === "overdue" ? task.overdue : task.priority === filter)
        );
    }

    get activities() {
        return this.state.data.activities.map((a) => ({ ...a, when: relativeTime(a.date) }));
    }

    openAction(xmlid) {
        if (!xmlid) {
            return;
        }
        if (!this.canOpen(xmlid)) {
            // it used to do nothing at all, which from the outside is the same as a
            // broken tile: the figure is there, the card takes the click, nothing
            // happens and nothing says why
            this.notification.add(
                _t("You do not have access to open this from here."),
                { type: "warning" });
            return;
        }
        this.action.doAction(xmlid);
    }

    openEntity(id) {
        this.action.doAction("azm_platform.action_azm_entity", {
            props: { resId: id },
            viewType: "form",
        });
    }

    openRecord(model, resId) {
        if (model === "res.company") {
            return this.openEntity(resId);
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: model,
            res_id: resId,
            views: [[false, "form"]],
        });
    }

    setTaskFilter(filter) {
        this.state.taskFilter = filter;
    }

    onQuestionInput(ev) {
        this.state.question = ev.target.value;
    }

    onQuestionKeydown(ev) {
        if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
            this.ask();
        }
    }

    useSuggestion(text) {
        this.state.question = text;
        this.ask();
    }

    async ask() {
        if (!this.state.question.trim() || this.state.asking) {
            return;
        }
        this.state.asking = true;
        this.state.answer = "";
        try {
            const result = await this.orm.call("azm.dashboard", "ai_ask", [this.state.question]);
            this.state.answer = result.answer;
            this.state.answerOk = result.ok;
        } finally {
            this.state.asking = false;
        }
    }
}

registry.category("actions").add("azm_dashboard", AzmDashboard);
