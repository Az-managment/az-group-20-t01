import { Component, onWillStart, proxy, useOnChange, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { KeepLast } from "@web/core/utils/concurrency";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { AzmDonutChart } from "@azm_platform/components/donut_chart";
import { canOpen, loadAzmRights, relativeTime } from "@azm_platform/components/utils";
import { selectionLabel } from "./entity_header";

function docIcon(mimetype) {
    if (!mimetype) {
        return "description";
    }
    if (mimetype.includes("pdf")) {
        return "picture_as_pdf";
    }
    if (mimetype.startsWith("image")) {
        return "image";
    }
    if (mimetype.includes("sheet") || mimetype.includes("excel") || mimetype.includes("csv")) {
        return "table_chart";
    }
    return "description";
}

/** Body of the entity page: info, people by department, documents, teams, projects, activity. */
export class AzmEntityOverview extends Component {
    static template = "azm_platform.EntityOverview";
    static components = { AzmDonutChart };
    props = useProps(standardWidgetProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ data: null, rights: null });
        // Paging the entity form reloads this on every record. Without keeping only
        // the last answer, a slow response for the record just left can land after a
        // fast one for the record now shown, and the page describes the wrong entity
        // under the right header. Every sibling page already does this.
        this.keepLoad = new KeepLast();
        onWillStart(async () => {
            this.state.rights = await loadAzmRights();
            await this.load(this.props.record.resId);
        });
        useOnChange(() => [this.props.record.resId], (resId) => this.load(resId), { initialRun: false });
    }

    async load(resId) {
        // an entity outside the active companies answers {} — truthy, but with none of
        // the keys this page reads, which blanks the whole form instead of saying so
        const found = resId
            ? await this.keepLoad.add(
                this.orm.call("azm.dashboard", "get_company_overview", [resId]))
            : null;
        this.state.data = found && found.documents_model ? found : null;
    }

    get record() {
        return this.props.record;
    }
    get infoRows() {
        const d = this.record.data;
        return [
            { label: _t("Name"), value: d.name },
            { label: _t("Name (other language)"), value: d.azm_name_alt },
            { label: _t("Type"), value: selectionLabel(this.record, "azm_entity_type") },
            { label: _t("Sector"), value: selectionLabel(this.record, "azm_sector") },
            { label: _t("Country"), value: [d.city, d.country_id && d.country_id.display_name].filter(Boolean).join(", ") },
            { label: _t("Website"), value: d.website, link: d.website },
            { label: _t("Email"), value: d.email },
            { label: _t("Phone"), value: d.phone },
            { label: _t("Short Description"), value: d.azm_description },
        ];
    }
    get documents() {
        return this.state.data.documents.map((doc) => ({ ...doc, icon: docIcon(doc.type) }));
    }
    get activities() {
        return this.state.data.activities.map((a) => ({ ...a, when: relativeTime(a.date) }));
    }
    get donutLabel() {
        return _t("Employees");
    }
    get donutEmptyLabel() {
        return _t("No employees yet");
    }

    canOpen(method) {
        return canOpen(this.state.rights, method);
    }

    async open(method) {
        if (!this.canOpen(method)) {
            return;
        }
        const action = await this.orm.call("res.company", method, [[this.record.resId]]);
        this.action.doAction(action);
    }

    openRecord(model, resId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: model,
            res_id: resId,
            views: [[false, "form"]],
        });
    }
}

registry.category("view_widgets").add("azm_entity_overview", { component: AzmEntityOverview });
