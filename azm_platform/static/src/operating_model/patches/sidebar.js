import { patch } from "@web/core/utils/patch";
import { AzmSidebar } from "@azm_platform/sidebar/azm_sidebar";

const OM_ICONS = {
    "azm_platform.menu_om_dashboard": "folder",
    "azm_platform.menu_om_assessments": "assignment",
    "azm_platform.menu_om_findings": "flag",
    "azm_platform.menu_om_questions": "list_alt",
    "azm_platform.menu_fin_dashboard": "payments",
    "azm_platform.menu_fin_assessments": "checklist",
    "azm_platform.menu_fin_gaps": "warning",
};
const DIVIDERS = new Set([
    "azm_platform.menu_om_dashboard",
]);

/** Icons for the Operating Model entries of the AZM sidebar, with a divider before them. */
patch(AzmSidebar.prototype, {
    get items() {
        return super.items.map((item) => ({
            ...item,
            icon: OM_ICONS[item.menu.xmlid] || item.icon,
            divider: item.divider || DIVIDERS.has(item.menu.xmlid),
        }));
    },
});
