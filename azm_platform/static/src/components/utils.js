import { user } from "@web/core/user";
const { DateTime } = luxon;

/** "2 hours ago" style label from a UTC SQL datetime string. */
export function relativeTime(sqlDate) {
    if (!sqlDate) {
        return "";
    }
    const dt = DateTime.fromSQL(sqlDate, { zone: "utc" });
    return dt.isValid ? dt.toRelative() : "";
}

export function formatPercent(value, hasData = true) {
    if (!hasData || value === null || value === undefined) {
        return "—";
    }
    return `${Math.round(value)}%`;
}

export function entityImageUrl(id, field, size, unique) {
    return `/web/image/res.company/${id}/${field}${size ? "/" + size : ""}?unique=${encodeURIComponent(unique || "")}`;
}

// ---------------------------------------------------------------------------
// Permissions & company scope shared by every AZM screen
// ---------------------------------------------------------------------------

let rightsPromise = null;

/**
 * What the current user may open from the AZM screens. Links and buttons to an
 * app the user has no rights on are hidden instead of ending on an access error.
 */
export function loadAzmRights() {
    if (!rightsPromise) {
        rightsPromise = Promise.all([
            user.hasGroup("hr.group_hr_user"),
            user.hasGroup("project.group_project_user"),
            user.hasGroup("base.group_erp_manager"),
            user.hasGroup("base.group_system"),
        ]).then(([hr, project, editCompany, settings]) => ({ hr, project, editCompany, settings, documents: true }));
    }
    return rightsPromise;
}

/** Right needed to open a given AZM target (action xml id or entity method). */
const NEEDS = {
    "hr.open_view_employee_list_my": "hr",
    "hr.hr_department_kanban_action": "hr",
    "project.open_view_project_all": "project",
    "project.action_view_all_task": "project",
    action_azm_employees: "hr",
    action_azm_departments: "hr",
    action_azm_projects: "project",
    action_azm_tasks: "project",
    action_azm_edit_company: "editCompany",
};

export function canOpen(rights, target) {
    const need = NEEDS[target];
    return !target ? false : !need || Boolean(rights && rights[need]);
}
