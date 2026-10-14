import { rpc } from "@web/core/network/rpc";
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
        // Asked of the models rather than of the groups. Access comes from whatever
        // groups and rules a deployment uses, so "is this user in project's user
        // group" answers a different question from "may this user read projects" —
        // and answered it wrongly for anybody who reaches Projects some other way.
        rightsPromise = rpc("/web/dataset/call_kw", {
            model: "azm.dashboard",
            method: "azm_rights",
            args: [],
            kwargs: {},
        }).catch(() => ({ hr: false, project: false, tasks: false, documents: true,
                          editCompany: false, settings: false }));
    }
    return rightsPromise;
}

/** Right needed to open a given AZM target (action xml id or entity method). */
const NEEDS = {
    "hr.open_view_employee_list_my": "hr",
    "hr.hr_department_kanban_action": "hr",
    "project.open_view_project_all": "project",
    "project.action_view_all_task": "tasks",
    action_azm_employees: "hr",
    action_azm_departments: "hr",
    action_azm_projects: "project",
    action_azm_tasks: "tasks",
    action_azm_edit_company: "editCompany",
};

export function canOpen(rights, target) {
    const need = NEEDS[target];
    return !target ? false : !need || Boolean(rights && rights[need]);
}
