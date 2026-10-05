import { Component, onMounted, onWillStart, onWillUnmount, proxy, useListener } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { browser } from "@web/core/browser/browser";
import { rpc } from "@web/core/network/rpc";
import { render } from "@web/owl2/utils";

const ROOT_XMLID = "azm_platform.menu_root";

const ICONS = {
    "azm_platform.menu_my_work": "assignment_ind",
    "azm_platform.menu_home": "home",
    "azm_platform.menu_entities": "business",
    "azm_platform.menu_structure": "account_tree",
    "azm_platform.menu_employees": "group",
    "azm_platform.menu_departments": "badge",
    "azm_platform.menu_projects": "rocket_launch",
    "azm_platform.menu_tasks": "task",
    "azm_platform.menu_documents": "description",
    "azm_platform.menu_outputs_library": "inventory_2",
    "azm_platform.menu_settings": "settings",
};

// Entries whose icon is one of the group's own drawings rather than a glyph of the
// icon font. The value is the template that draws it.
const MARKS = {
    "azm_platform.menu_trees": "azm_platform.TreeMark",
};

// A divider is drawn before these entries (mirrors the design's sections).
const SECTION_STARTS = new Set(["azm_platform.menu_employees", "azm_platform.menu_settings"]);

// The two languages of the group, shown in the sidebar so that a person can
// switch without going through their preferences. Only the ones actually
// installed are offered: a code that is not installed cannot be written on a
// user, and the button would only ever fail.
const LANGUAGES = [
    { prefix: "en", label: "EN" },
    { prefix: "ar", label: "ع" },
];

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
        this.orm = useService("orm");
        this.languages = [];
        onWillStart(async () => {
            const installed = await this.orm.call("res.lang", "get_installed", []);
            this.languages = LANGUAGES.flatMap(({ prefix, label }) => {
                const found = installed.find(([code]) => code.startsWith(prefix));
                return found ? [{ code: found[0], name: found[1], label }] : [];
            });
        });
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
            mark: MARKS[menu.xmlid] || false,
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

    get currentLang() {
        return user.context.lang;
    }

    /**
     * Switch the language and reload. The interface, the menus and the
     * translated records are all rendered server side from the language, so
     * there is nothing to swap in place. The route also puts the running
     * session on it: writing res.users.lang alone leaves the session holding
     * the context it built at login, and the page would come back unchanged.
     */
    async setLanguage(code) {
        if (code === this.currentLang) {
            return;
        }
        await rpc("/azm/language", { lang: code });
        browser.location.reload();
    }
}

registry.category("main_components").add("azm_platform.Sidebar", { Component: AzmSidebar });
