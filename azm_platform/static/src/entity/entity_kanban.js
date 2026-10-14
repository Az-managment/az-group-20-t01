import { Component, onWillStart, proxy } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { formatPercent } from "@azm_platform/components/utils";

/** Header tiles displayed above the entity cards. */
export class AzmEntityStats extends Component {
    static template = "azm_platform.EntityStats";

    setup() {
        this.orm = useService("orm");
        this.state = proxy({ stats: null });
        onWillStart(async () => {
            this.state.stats = await this.orm.call("azm.dashboard", "get_entity_stats", []);
        });
    }

    get progressLabel() {
        const p = this.state.stats.progress;
        return formatPercent(p, p !== null);
    }

    get progressWidth() {
        return this.state.stats.progress || 0;
    }
}

export class AzmEntityKanbanRenderer extends KanbanRenderer {
    static template = "azm_platform.EntityKanbanRenderer";
    static components = { ...KanbanRenderer.components, AzmEntityStats };
}

export const azmEntityKanbanView = {
    ...kanbanView,
    Renderer: AzmEntityKanbanRenderer,
};

registry.category("views").add("azm_entity_kanban", azmEntityKanbanView);
