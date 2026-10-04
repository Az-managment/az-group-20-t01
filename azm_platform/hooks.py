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
        ["Group Finance", "Shared Services", "Internal Audit"],
        [("Group ERP Rollout",
          [("Chart of accounts per entity", True), ("Approval matrix", True),
           ("Consolidation pack", False), ("Entity KPI dashboards", False)]),
         ("Group Policy Library",
          [("Procurement policy", True), ("Delegation of authority", False),
           ("Travel and expense policy", False)])]),
    'az_group_base.company_future_univ': (
        ["Academic Affairs", "Student Services", "Finance"],
        [("Student Lifecycle Programme",
          [("Admissions intake 2026", True), ("Tuition plan automation", False),
           ("Alumni register", False), ("Campus asset survey", False)]),
         ("Accreditation 2026",
          [("Self-study report", True), ("Programme mapping", True),
           ("Evidence portfolio", False)])]),
    'az_group_base.company_malvern': (
        ["Academic Affairs", "Admissions", "Operations"],
        [("Campus Operations 2026",
          [("Term fee schedule", True), ("Boarding house audit", True),
           ("Transport routes review", False)]),
         ("Safeguarding Programme",
          [("Staff training round", True), ("Policy refresh", False),
           ("Incident register", False)])]),
    'az_group_base.company_alson_language': (
        ["Teaching", "Registration", "Quality"],
        [("Course Catalogue Refresh",
          [("Level descriptors", True), ("Teacher certification log", False),
           ("Evening cohort plan", False)]),
         ("Corporate Programmes",
          [("Client needs analysis", True), ("Pricing model", False),
           ("Trainer roster", False)])]),
    'az_group_base.company_alson_tourism': (
        ["Training", "Industry Placement", "Quality"],
        [("Placement Partnerships",
          [("Hotel partner agreements", True), ("Placement tracker", False),
           ("Graduate survey", False)]),
         ("Practical Training Kitchen",
          [("Equipment list", True), ("Safety certification", True),
           ("Session timetable", False)])]),
    'az_group_base.company_alson_computer': (
        ["Training", "Labs", "Certification"],
        [("Lab Modernisation",
          [("Workstation inventory", True), ("Curriculum mapping", False),
           ("Certification pathway", False)]),
         ("Vendor Certification Centre",
          [("Accreditation application", True), ("Exam scheduling", False),
           ("Trainer certification", False)])]),
    'az_group_base.company_alson_institute': (
        ["Training", "Corporate Programmes", "Finance"],
        [("Corporate Training Pipeline",
          [("Client needs analysis", True), ("Trainer pool", False),
           ("Course costing model", False)]),
         ("Executive Education",
          [("Programme design", True), ("Venue contracts", True),
           ("Marketing plan", False)])]),
}

# Who sits in each entity, and which demo login is that person.
DEV_EMPLOYEES = {
    'az_group_base.company_az_management': [
        ("Khaled Nabil", 0, 'group.admin'), ("Hoda Selim", 0, None),
        ("Amr Bassiouny", 1, None), ("Nadia Fahmy", 2, None)],
    'az_group_base.company_future_univ': [
        ("Mona Hassan", 2, 'fue.staff'), ("Sara Adel", 0, 'fue.azm'),
        ("Hani Lotfy", 1, None), ("Dalia Shawky", 0, None),
        ("Tamer Riad", 1, None), ("Injy Kamal", 2, None)],
    'az_group_base.company_malvern': [
        ("Omar Fathy", 2, 'mce.staff'), ("Dina Raafat", 1, None),
        ("Peter Grant", 0, None), ("Mai Soliman", 0, None),
        ("Hesham Nour", 2, None)],
    'az_group_base.company_alson_language': [
        ("Rasha Deeb", 0, None), ("Mostafa Helmy", 1, None),
        ("Yara Nabil", 0, None), ("Sherif Zaki", 2, None)],
    'az_group_base.company_alson_tourism': [
        ("Nermine Saad", 0, None), ("Wael Abdel Aziz", 1, None),
        ("Heba Farouk", 0, None), ("Ziad Mansour", 2, None)],
    'az_group_base.company_alson_computer': [
        ("Ayman Shoukry", 0, None), ("Lina Gaber", 1, None),
        ("Fady Wassef", 0, None), ("Nourhan Said", 2, None)],
    'az_group_base.company_alson_institute': [
        ("Ehab Darwish", 0, None), ("Mirna Atef", 1, None),
        ("Sameh Labib", 0, None), ("Rana Hegazy", 2, None)],
}
# Everyone else gets a couple of unnamed-but-real employees per department.
DEFAULT_EMPLOYEES = [("Operations Lead", 0, None), ("Coordinator", 1, None)]

# A small file set per entity, so the Documents card on the entity page has
# something to count and to open. Kept as plain text on purpose: this is
# sample data and it has to stay small.
DEV_DOCUMENTS = {
    'az_group_base.company_az_management': [
        ("Group Governance Charter", "Roles, delegations and approval thresholds across the group."),
        ("Shared Services Catalogue", "What AZ Management runs centrally for the other entities."),
        ("Entity Reporting Calendar", "When each entity reports, and to whom."),
    ],
    'az_group_base.company_future_univ': [
        ("Academic Calendar 2026", "Terms, examination windows and graduation dates."),
        ("Tuition and Fees Policy", "Fee structure, instalment plans and refund rules."),
        ("Accreditation Checklist", "Evidence required for the next accreditation visit."),
    ],
    'az_group_base.company_malvern': [
        ("Admissions Handbook", "Entry requirements, assessment and offer process."),
        ("Safeguarding Policy", "Duties, reporting lines and training requirements."),
    ],
    'az_group_base.company_alson_language': [
        ("Course Catalogue", "Levels, hours and certification for each language track."),
        ("Teacher Handbook", "Lesson standards, assessment and record keeping."),
    ],
    'az_group_base.company_alson_tourism': [
        ("Placement Agreement Template", "Standard terms for hotel and operator placements."),
        ("Training Programme Outline", "The three-year programme, term by term."),
    ],
    'az_group_base.company_alson_computer': [
        ("Lab Equipment Register", "Workstations, software licences and renewal dates."),
        ("Certification Pathways", "Vendor certifications mapped to the course plan."),
    ],
    'az_group_base.company_alson_institute': [
        ("Corporate Training Catalogue", "Short courses offered to corporate clients."),
        ("Trainer Engagement Terms", "Rates, scheduling and evaluation of external trainers."),
    ],
}

# Who prepares the assessment of each entity. A preparer only sees their own
# work, so this decides whose dashboard the operating model shows up on.
ASSESSMENT_OWNERS = {
    'az_group_base.company_future_univ': 'fue.azm',
    'az_group_base.company_malvern': 'mce.staff',
}


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
    for xml_id, (department_names, projects) in DEV_ENTITY_DATA.items():
        company = env.ref(xml_id, raise_if_not_found=False)
        if not company:
            continue
        departments = _ensure_departments(env, company, department_names)
        _ensure_employees(env, company, departments, Users, xml_id)
        for project_name, tasks in projects:
            _ensure_project(env, company, project_name, tasks)
        _ensure_documents(env, company, DEV_DOCUMENTS.get(xml_id, []))
        _ensure_assessments(env, company)
        _ensure_assessment_book(env, company)
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
    people = DEV_EMPLOYEES.get(xml_id) or [
        (f"{company.code} {role}", index, None) for role, index, _login in DEFAULT_EMPLOYEES
    ]
    for name, department_index, login in people:
        # Checked per person, not "does this company have anybody": the roster
        # grows, and a blanket guard would freeze it at whoever came first.
        if Employee.search_count([('company_id', '=', company.id), ('name', '=', name)]):
            continue
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


def _ensure_documents(env, company, files):
    """Put a folder of small files in the entity's own Documents workspace.

    The platform reads documents.document when Documents is installed and
    falls back to plain attachments when it is not, so this only runs when the
    model is there.
    """
    if not files or 'documents.document' not in env:
        return
    Document = env['documents.document'].with_company(company)
    folder = Document.search([
        ('type', '=', 'folder'),
        ('name', '=', company.name),
        ('company_id', '=', company.id),
    ], limit=1)
    if not folder:
        folder = Document.create({
            'name': company.name,
            'type': 'folder',
            'company_id': company.id,
            # Documents default to access_internal 'none', which hides them
            # from every internal user and leaves the entity card at zero.
            'access_internal': 'view',
        })
    for title, summary in files:
        if Document.search_count([
            ('name', '=', title), ('company_id', '=', company.id), ('type', '!=', 'folder'),
        ]):
            continue
        Document.create({
            'name': title,
            'type': 'binary',
            'raw': f"{title}\n\n{summary}\n".encode(),
            'mimetype': 'text/plain',
            'folder_id': folder.id,
            'company_id': company.id,
            'access_internal': 'view',
        })


def _ensure_assessments(env, company):
    """Fill one procurement and one financial assessment for the entity.

    Both models ship their own deterministic demo filler, so the answers are
    the module's own idea of a realistic mix of good and weak practice rather
    than anything invented here. Without them every operating model KPI on the
    entity page reads zero and the register pages are empty.
    """
    entity = env['azm.entity'].sudo().search([('company_id', '=', company.id)], limit=1)
    if not entity:
        return
    # A preparer only ever sees the assessments they own, so an assessment
    # created in the name of the system is invisible to the entity's own staff.
    # Prefer somebody who works in this entity alone over a group-wide manager,
    # who is on every entity and would otherwise own all of them.
    owner = env['res.users']
    login = ASSESSMENT_OWNERS.get(_company_xml_id(env, company))
    if login:
        owner = env['res.users'].with_context(active_test=False).search(
            [('login', '=', login)], limit=1)
    owner = owner or entity.user_ids.filtered(
        lambda user: user.company_ids == company)[:1] or entity.user_ids[:1]
    if 'azm.assessment' in env and not env['azm.assessment'].sudo().search_count(
            [('entity_id', '=', entity.id)]):
        from odoo.addons.azm_operating_model.models.azm_assessment import (
            PURCHASE_KINDS, SCENARIOS,
        )
        assessment = env['azm.assessment'].sudo().with_company(company).create({
            'entity_id': entity.id,
            'purchase_kind': PURCHASE_KINDS[0][0],
            'scenario': SCENARIOS[0][0],
            'user_id': owner.id or env.uid,
        })
        assessment.action_fill_demo()
    if 'azm.fin.assessment' in env and not env['azm.fin.assessment'].sudo().search_count(
            [('entity_id', '=', entity.id)]):
        financial = env['azm.fin.assessment'].sudo().with_company(company).create({
            'entity_id': entity.id,
            'user_id': owner.id or env.uid,
        })
        financial.action_fill_demo()


def _company_xml_id(env, company):
    """The az_group_base xml id of a company, or None when it has none."""
    data = env['ir.model.data'].sudo().search([
        ('model', '=', 'res.company'), ('res_id', '=', company.id),
    ], limit=1)
    return f"{data.module}.{data.name}" if data else None


def _ensure_assessment_book(env, company):
    """File the generated cycle book of the entity in its own workspace.

    The operating model turns the answers into a book -- policy, procedure,
    the flow, the authority matrix, the gaps and the candidate risks -- and
    that book is the point of filling an assessment. Rendering it into the
    entity's Documents folder is what makes it a document people can open and
    share rather than a screen inside the app.
    """
    if 'documents.document' not in env or 'azm.assessment' not in env:
        return
    assessment = env['azm.assessment'].sudo().search([('company_id', '=', company.id)], limit=1)
    report = env.ref('azm_operating_model.azm_assessment_report_book', raise_if_not_found=False)
    if not assessment or not report:
        return
    title = f"{company.code or company.name} Operating Model Book"
    Document = env['documents.document'].sudo().with_company(company)
    if Document.search_count([
        ('name', '=like', f"{title}%"), ('company_id', '=', company.id),
    ]):
        return
    folder = Document.search([
        ('type', '=', 'folder'), ('name', '=', company.name), ('company_id', '=', company.id),
    ], limit=1)
    try:
        # force_report_rendering: a build installed with --test-enable renders reports as
        # HTML (ir_actions_report._pre_render_qweb_pdf falls back), and the book was filed
        # as a .pdf holding "<!DOCTYPE html>".
        content, content_type = report.with_context(force_report_rendering=True)._render(
            report.report_name, assessment.ids)
    except Exception:  # noqa: BLE001 - a missing pdf renderer must not fail the install
        _logger.warning("Could not render the operating model book of %s", company.name, exc_info=True)
        return
    if content_type != 'pdf':
        # better no book than one that opens as garbage
        _logger.warning("The operating model book of %s rendered as %s, not a PDF; not filing it.",
                        company.name, content_type)
        return
    Document.create({
        'name': f"{title}.pdf",
        'type': 'binary',
        'raw': content,
        'mimetype': 'application/pdf',
        'folder_id': folder.id if folder else False,
        'company_id': company.id,
        'access_internal': 'view',
    })
    _logger.info("Filed the operating model book of %s", company.name)
