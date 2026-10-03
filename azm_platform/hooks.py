import logging
import os

from odoo import Command

_logger = logging.getLogger(__name__)

# What each entity is. This is master data, not a demo: the platform shows the
# type and the sector on every entity card and groups the entities by them.
# xml id -> (entity type, sector, tagline)
ENTITY_PROFILES = {
    'az_group_base.company_az_management': (
        'holding', 'investment', "One Group. Unified Systems. Stronger Tomorrow."),
    'az_group_base.company_future_univ': (
        'university', 'higher_education', "Shaping the professionals of tomorrow."),
    'az_group_base.company_malvern': (
        'school', 'k12', "A British education, rooted in Egypt."),
    'az_group_base.company_alson_language': (
        'school', 'training', "Languages that open doors."),
    'az_group_base.company_alson_tourism': (
        'institute', 'tourism', "Hospitality taught by the industry."),
    'az_group_base.company_alson_computer': (
        'school', 'training', "Practical computing, from day one."),
    'az_group_base.company_alson_institute': (
        'institute', 'training', "Professional training for working adults."),
}

# The working data each entity gets on a development build, so that its
# dashboard reads from the source apps instead of showing zeros:
# xml id -> (departments, project, [(task, done)])
DEV_ENTITY_DATA = {
    'az_group_base.company_az_management': (
        ["Group Finance", "Shared Services"], "Group ERP Rollout",
        [("Chart of accounts per entity", True), ("Approval matrix", True),
         ("Consolidation pack", False), ("Entity KPI dashboards", False)]),
    'az_group_base.company_future_univ': (
        ["Academic Affairs", "Student Services"], "Student Lifecycle Programme",
        [("Admissions intake 2026", True), ("Tuition plan automation", False),
         ("Alumni register", False), ("Campus asset survey", False)]),
    'az_group_base.company_malvern': (
        ["Academic Affairs", "Admissions"], "Campus Operations 2026",
        [("Term fee schedule", True), ("Boarding house audit", True),
         ("Transport routes review", False)]),
    'az_group_base.company_alson_language': (
        ["Teaching", "Registration"], "Course Catalogue Refresh",
        [("Level descriptors", True), ("Teacher certification log", False),
         ("Evening cohort plan", False)]),
    'az_group_base.company_alson_tourism': (
        ["Training", "Industry Placement"], "Placement Partnerships",
        [("Hotel partner agreements", True), ("Placement tracker", False),
         ("Graduate survey", False)]),
    'az_group_base.company_alson_computer': (
        ["Training", "Labs"], "Lab Modernisation",
        [("Workstation inventory", True), ("Curriculum mapping", False),
         ("Certification pathway", False)]),
    'az_group_base.company_alson_institute': (
        ["Training", "Corporate Programmes"], "Corporate Training Pipeline",
        [("Client needs analysis", True), ("Trainer pool", False),
         ("Course costing model", False)]),
}

# Who sits in each entity, and which demo login is that person.
DEV_EMPLOYEES = {
    'az_group_base.company_future_univ': [
        ("Mona Hassan", 0, 'fue.staff'), ("Sara Adel", 0, 'fue.azm'), ("Hani Lotfy", 1, None)],
    'az_group_base.company_malvern': [
        ("Omar Fathy", 0, 'mce.staff'), ("Dina Raafat", 1, None)],
}
# Everyone else gets a couple of unnamed-but-real employees per department.
DEFAULT_EMPLOYEES = [("Operations Lead", 0, None), ("Coordinator", 1, None)]


def describe_entities(env):
    """Give each entity its type, sector and tagline.

    The platform groups and labels the entity cards by these, so an entity
    without them shows as an untyped card with an empty subtitle.
    """
    for xml_id, (entity_type, sector, tagline) in ENTITY_PROFILES.items():
        company = env.ref(xml_id, raise_if_not_found=False)
        if not company:
            continue
        company.write({
            'azm_entity_type': entity_type,
            'azm_sector': sector,
            'azm_tagline': company.azm_tagline or tagline,
        })
    _logger.info("Described %s entities", len(ENTITY_PROFILES))


def load_dev_entity_data(env):
    """Fill each entity with the HR and project data its dashboard reads.

    The dashboard counts employees, departments, projects and tasks straight
    from the source apps, so without them every entity card reads zero and the
    whole platform looks broken on a fresh build. Development builds only: this
    is sample data, and ODOO_STAGE says whether we are on one.
    """
    stage = os.environ.get('ODOO_STAGE')
    if stage != 'dev':
        _logger.info("ODOO_STAGE is %s, not dev: skipping the entity sample data", stage or "unset")
        return
    if 'hr.employee' not in env or 'project.project' not in env:
        return
    Users = env['res.users'].with_context(active_test=False)
    for xml_id, (department_names, project_name, tasks) in DEV_ENTITY_DATA.items():
        company = env.ref(xml_id, raise_if_not_found=False)
        if not company:
            continue
        departments = _ensure_departments(env, company, department_names)
        _ensure_employees(env, company, departments, Users, xml_id)
        _ensure_project(env, company, project_name, tasks)
    _logger.info("Filled %s entities with sample HR and project data", len(DEV_ENTITY_DATA))


def _ensure_departments(env, company, names):
    Department = env['hr.department'].with_company(company)
    departments = env['hr.department']
    for name in names:
        existing = Department.search([('company_id', '=', company.id), ('name', '=', name)], limit=1)
        departments |= existing or Department.create({'name': name, 'company_id': company.id})
    return departments


def _ensure_employees(env, company, departments, Users, xml_id):
    Employee = env['hr.employee'].with_company(company)
    if Employee.search_count([('company_id', '=', company.id)]):
        return
    people = DEV_EMPLOYEES.get(xml_id) or [
        (f"{company.code} {role}", index, None) for role, index, _login in DEFAULT_EMPLOYEES
    ]
    for name, department_index, login in people:
        values = {
            'name': name,
            'company_id': company.id,
            'department_id': departments[min(department_index, len(departments) - 1)].id,
        }
        if login:
            user = Users.search([('login', '=', login)], limit=1)
            if user:
                values['user_id'] = user.id
        Employee.create(values)


def _ensure_project(env, company, project_name, tasks):
    Project = env['project.project'].with_company(company)
    project = Project.search([('company_id', '=', company.id), ('name', '=', project_name)], limit=1)
    if not project:
        project = Project.create({'name': project_name, 'company_id': company.id})
    Task = env['project.task'].with_company(company)
    for title, done in tasks:
        if Task.search_count([('project_id', '=', project.id), ('name', '=', title)]):
            continue
        Task.create({
            'name': title,
            'project_id': project.id,
            'company_id': company.id,
            'state': '1_done' if done else '01_in_progress',
        })
