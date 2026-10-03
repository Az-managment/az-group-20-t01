import { Component, onMounted, onWillUnmount, proxy, useListener } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { render } from "@web/owl2/utils";

const ROOT_XMLID = "azm_platform.menu_root";

const ICONS = {
    "azm_platform.menu_home": "home",
    "azm_platform.menu_entities": "business",
    "azm_platform.menu_structure": "account_tree",
    "azm_platform.menu_employees": "group",
    "azm_platform.menu_departments": "badge",
    "azm_platform.menu_projects": "rocket_launch",
    "azm_platform.menu_tasks": "task",
    "azm_platform.menu_documents": "description",
    "azm_platform.menu_settings": "settings",
};

// A divider is drawn before these entries (mirrors the design's sections).
const SECTION_STARTS = new Set(["azm_platform.menu_employees", "azm_platform.menu_settings"]);

/**
 * Left sidebar shown only while the AZM app is open. It is rendered from the
 * app's ir.ui.menu entries, so access rights and new menus are respected.
 */
export class AzmSidebar extends Component {
    static template = "azm_platform.Sidebar";

    setup() {
        this.menuService = useService("menu");
        this.actionService = useService("action");
        this.state = proxy({ activeMenuId: null, collapsed: false });
        const refresh = () => {
            this.syncBodyClass();
            this.syncActiveMenu();
            render(this);
        };
        useListener(this.env.bus, "MENUS:APP-CHANGED", refresh);
        useListener(this.env.bus, "ACTION_MANAGER:UI-UPDATED", refresh);
        onMounted(refresh);
        onWillUnmount(() => document.body.classList.remove("o_azm_mode"));
    }

    get app() {
        const app = this.menuService.getCurrentApp();
        return app && app.xmlid === ROOT_XMLID ? app : null;
    }

    get items() {
        if (!this.app) {
            return [];
        }
        const tree = this.menuService.getMenuAsTree(this.app.id);
        return (tree.childrenTree || []).map((menu) => ({
            id: menu.id,
            name: menu.name,
            menu,
            icon: ICONS[menu.xmlid] || "chevron_right",
            divider: SECTION_STARTS.has(menu.xmlid),
        }));
    }

    syncBodyClass() {
        document.body.classList.toggle("o_azm_mode", Boolean(this.app));
        document.body.classList.toggle("o_azm_sidebar_collapsed", this.state.collapsed);
    }

    syncActiveMenu() {
        const actionId = this.actionService.currentAction?.id;
        const item = this.items.find((i) => i.menu.actionID === actionId);
        if (item) {
            this.state.activeMenuId = item.id;
        }
    }

    onClick(item) {
        this.state.activeMenuId = item.id;
        this.menuService.selectMenu(item.menu);
    }

    toggle() {
        this.state.collapsed = !this.state.collapsed;
        this.syncBodyClass();
    }
}

registry.category("main_components").add("azm_platform.Sidebar", { Component: AzmSidebar });
