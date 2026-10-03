import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { canOpen, entityImageUrl, formatPercent, loadAzmRights } from "@azm_platform/components/utils";

export function selectionLabel(record, fieldName) {
    const value = record.data[fieldName];
    const selection = record.fields[fieldName]?.selection || [];
    return (selection.find(([key]) => key === value) || [value, value || ""])[1];
}

/** Hero banner + live KPI cards at the top of the entity (company) page. */
export class AzmEntityHeader extends Component {
    static template = "azm_platform.EntityHeader";
    props = useProps(standardWidgetProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.rights = proxy({ value: null });
        onWillStart(async () => {
            this.rights.value = await loadAzmRights();
        });
    }

    get canEdit() {
        return canOpen(this.rights.value, "action_azm_edit_company");
    }

    canOpen(method) {
        return canOpen(this.rights.value, method);
    }

    get record() {
        return this.props.record;
    }
    get data() {
        return this.record.data;
    }
    get unique() {
        const wd = this.data.write_date;
        return wd && wd.toISO ? wd.toISO() : String(wd || "");
    }
    get logoUrl() {
        return this.data.logo && !this.data.uses_default_logo ? entityImageUrl(this.record.resId, "logo", "256x256", this.unique) : false;
    }
    get coverUrl() {
        return this.data.azm_cover_image ? entityImageUrl(this.record.resId, "azm_cover_image", "", this.unique) : false;
    }
    get typeLabel() {
        return selectionLabel(this.record, "azm_entity_type");
    }
    get sectorLabel() {
        return selectionLabel(this.record, "azm_sector");
    }
    get statusLabel() {
        return selectionLabel(this.record, "azm_status");
    }
    get websiteHost() {
        return (this.data.website || "").replace(/^https?:\/\//, "").replace(/\/$/, "");
    }
    get cards() {
        const d = this.data;
        return [
            { key: "progress", label: _t("Task Completion"), value: formatPercent(d.azm_progress, d.azm_has_data),
                icon: "bar_chart", tone: "orange", method: "action_azm_projects" },
            { key: "employees", label: _t("Employees"), value: d.azm_employee_count || "—",
                icon: "group", tone: "teal", method: "action_azm_employees" },
            { key: "departments", label: _t("Departments"), value: d.azm_department_count || "—",
                icon: "account_tree", tone: "purple", method: "action_azm_departments" },
            { key: "projects", label: _t("Projects"), value: d.azm_project_count || "—",
                icon: "rocket_launch", tone: "blue", method: "action_azm_projects" },
            { key: "tasks", label: _t("Open Tasks"), value: d.azm_open_task_count || "—",
                icon: "task", tone: "indigo", method: "action_azm_tasks" },
            { key: "documents", label: _t("Documents"), value: d.azm_document_count || "—",
                icon: "description", tone: "green", method: "action_azm_documents" },
        ];
    }

    async callAction(method) {
        const action = await this.orm.call("res.company", method, [[this.record.resId]]);
        this.action.doAction(action);
    }

    onCard(card) {
        if (card.method && this.record.resId && this.canOpen(card.method)) {
            this.callAction(card.method);
        }
    }
}

registry.category("view_widgets").add("azm_entity_header", { component: AzmEntityHeader });
