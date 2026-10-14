import logging
import os

from odoo import Command, SUPERUSER_ID
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# The entities of the group. Each one is an independent company: xml id,
# entity code, legal name, Arabic name.
#
# They are deliberately NOT branches of a parent company. A branch shares the
# chart of accounts of its root and its records show up when the root is
# selected, which is the opposite of what the group needs: every entity keeps
# its own books, and no entity reads another's data.
ENTITY_COMPANIES = [
    ('company_az_management', 'AZM', "AZ Management & Development", "AZ للإدارة والتطوير"),
    ('company_future_univ', 'FUE', "Future University in Egypt", "جامعة المستقبل – مصر"),
    ('company_malvern', 'MCE', "Malvern College Egypt", "مالفيرن كوليدج مصر"),
    ('company_alson_language', 'ALS', "Al Alson Language School", "الألسن للغات"),
    ('company_alson_tourism', 'AT3', "Al Alson Tourism School – 3-Year Program", "الألسن للسياحة – 3 سنوات"),
    ('company_alson_computer', 'ALC', "Al Alson Computer School", "الألسن للحاسبات"),
    ('company_alson_institute', 'AAI', "Al Alson Institute", "معهد الألسن"),
]

# Every entity runs on the Egyptian chart, loaded on the entity itself.
CHART_TEMPLATE = 'eg'

# The Arabic interface language of the group. Arabic ships inactive, and a
# language has to be active before a user can be set to it.
ARABIC_LANG = 'ar_001'

# The journals whose code carries the entity code, so that each entity numbers
# its documents under its own prefix. The chart template already creates these
# journals, so they are recoded rather than duplicated: type, the code the
# chart gives them, the suffix to use, and the name to fall back on when the
# chart did not create one.
JOURNAL_CODES = [
    ('sale', 'INV', 'IN', "Customer Invoices"),
    ('purchase', 'BILL', 'BL', "Vendor Bills"),
    ('general', 'MISC', 'MI', "Miscellaneous"),
    ('bank', 'BNK1', 'BN', "Bank"),
    ('cash', 'CSH1', 'CH', "Cash"),
]


# Demo staff of the group, created on development builds only. The passwords
# are throwaway and live in the repository, so these logins must never reach a
# staging or a production database: _load_dev_staff checks ODOO_STAGE first.
# login, display name, password, company xml ids (None means every entity),
# groups the module depends on, groups it only uses when they are installed.
DEV_STAFF = [
    ('fue.staff', "Mona Hassan (FUE Accountant)", 'FueStaff#2026',
     ['company_future_univ'],
     ['base.group_user', 'account.group_account_user'],
     ['azm_platform.group_azm_user', 'azm_operating_model.azm_group_user',
      'hr.group_hr_user']),
    ('mce.staff', "Omar Fathy (Malvern Accountant)", 'MceStaff#2026',
     ['company_malvern'],
     ['base.group_user', 'account.group_account_user'],
     ['azm_platform.group_azm_user', 'azm_operating_model.azm_group_user',
      'hr.group_hr_user']),
    ('fue.azm', "Sara Adel (FUE Preparer)", 'FueAzm#2026',
     ['company_future_univ'],
     ['base.group_user'],
     ['azm_platform.group_azm_user', 'azm_operating_model.azm_group_user',
      'hr.group_hr_user']),
    ('group.admin', "Khaled Nabil (Group Admin)", 'GroupAdmin#2026',
     None,
     ['base.group_user', 'account.group_account_manager'],
     ['azm_platform.group_azm_manager', 'azm_operating_model.azm_group_manager',
      'hr.group_hr_user']),
]

# Posted documents per entity, so that the separation between the entities is
# visible rather than theoretical and every entity has books of its own to
# look at: company xml id, partner, amount, line label.
DEV_INVOICES = [
    ('company_az_management', "Al Alson Holding Services", 180000.0, "Group shared services - Q1"),
    ('company_az_management', "Future University in Egypt", 240000.0, "Group shared services - Q1"),
    ('company_az_management', "Malvern College Egypt", 150000.0, "Group shared services - Q1"),
    ('company_future_univ', "Nour Ibrahim", 45000.0, "Tuition - Spring term"),
    ('company_future_univ', "Yassin Tarek", 38000.0, "Tuition - Spring term"),
    ('company_future_univ', "Hana Mostafa", 52000.0, "Tuition - Spring term"),
    ('company_future_univ', "Ministry of Higher Education", 310000.0, "Research grant instalment"),
    ('company_malvern', "Laila Samir", 92000.0, "Term fees - Spring"),
    ('company_malvern', "Adam Sherif", 88000.0, "Term fees - Spring"),
    ('company_malvern', "Karim Zaki", 95000.0, "Term fees - Spring"),
    ('company_alson_language', "Dalia Fouad", 7800.0, "General English - Level 4"),
    ('company_alson_language', "Ahmed Sobhy", 6400.0, "Business English - Evening"),
    ('company_alson_language', "Nile Trading Co.", 54000.0, "Corporate language programme"),
    ('company_alson_tourism', "Mariam Hosny", 12500.0, "Three-year programme - Year 1"),
    ('company_alson_tourism', "Youssef Rashad", 12500.0, "Three-year programme - Year 2"),
    ('company_alson_tourism', "Nile Ritz Hotels", 68000.0, "Staff training programme"),
    ('company_alson_computer', "Salma Gamal", 9800.0, "Diploma - Software track"),
    ('company_alson_computer', "Mahmoud Adel", 9800.0, "Diploma - Networks track"),
    ('company_alson_computer', "Delta Systems", 72000.0, "Corporate IT certification"),
    ('company_alson_institute', "Rana Ezzat", 14500.0, "Professional diploma"),
    ('company_alson_institute', "Tarek Mansour", 14500.0, "Professional diploma"),
    ('company_alson_institute', "Cairo Chamber of Commerce", 96000.0, "Executive training programme"),
]

# Vendor bills, so each entity has a purchase side and not only revenue.
DEV_BILLS = [
    ('company_az_management', "Orange Business Egypt", 42000.0, "Group network and telephony"),
    ('company_az_management', "PwC Egypt", 85000.0, "Advisory - operating model"),
    ('company_future_univ', "Elsevier", 120000.0, "Library subscriptions"),
    ('company_future_univ', "Cairo Facilities Co.", 76000.0, "Campus maintenance - Q1"),
    ('company_malvern', "Oxford University Press", 54000.0, "Course books"),
    ('company_malvern', "SafeBus Transport", 48000.0, "School transport - Q1"),
    ('company_alson_language', "Cambridge Assessment", 31000.0, "Examination fees"),
    ('company_alson_language', "Delta Print House", 9500.0, "Course material printing"),
    ('company_alson_tourism', "Hospitality Supplies Egypt", 27000.0, "Training kitchen supplies"),
    ('company_alson_tourism', "Nile Catering Services", 18500.0, "Practical sessions catering"),
    ('company_alson_computer', "TechGear Distribution", 143000.0, "Workstation refresh"),
    ('company_alson_computer', "Microsoft Egypt", 62000.0, "Software licences"),
    ('company_alson_institute', "Venue Partners Cairo", 36000.0, "Training venue hire"),
    ('company_alson_institute', "Expert Trainers Network", 58000.0, "External trainer fees"),
]


def post_init_hook(env):
    """Create the entity companies, each with its own chart and journals."""
    companies = env['res.company']
    for spec in ENTITY_COMPANIES:
        companies |= _ensure_company(env, spec)
    for company in companies:
        _load_chart_template(env, company)
        _code_entity_journals(env, company)
    _grant_entities(env, companies)
    _retire_main_company(env, companies)
    _activate_arabic(env)
    _load_dev_staff(env, companies)


def _ensure_company(env, spec):
    """Return the company of that xml id, creating it when it does not exist yet.

    No parent is ever set: res.company.write refuses vals holding parent_id,
    so a company created under a parent could never be detached afterwards.
    """
    xml_id, code, name, name_ar = spec
    company = env.ref(f'az_group_base.{xml_id}', raise_if_not_found=False)
    values = {'code': code, 'name_ar': name_ar}
    if company:
        company.write(values)
        return company
    values.update({
        'name': name,
        'country_id': env.ref('base.eg').id,
        'currency_id': env.ref('base.EGP').id,
    })
    company = env['res.company'].create(values)
    env['ir.model.data']._update_xmlids([{
        'xml_id': f'az_group_base.{xml_id}',
        'record': company,
        'noupdate': True,
    }])
    _logger.info("Created company %s", name)
    return company


def _load_chart_template(env, company):
    """Load the Egyptian chart on the entity, which owns it alone."""
    if company.chart_template:
        return
    env['account.chart.template'].try_loading(CHART_TEMPLATE, company=company, install_demo=False)
    _logger.info("Loaded the %s chart template on %s", CHART_TEMPLATE, company.name)


def _code_entity_journals(env, company):
    """Prefix the journals of the entity with its code.

    The sequence of a document is built from the code of its journal, so this
    is what makes an invoice of one entity read FUEIN/2026/00001 and never
    collide with another entity's numbering.
    """
    if not company.code:
        # Without a code there is no prefix to build the journals from,
        # and the entity would silently end up unable to invoice.
        raise UserError(env._(
            "Company %s has no entity code, so its journals cannot be coded.",
            company.name,
        ))
    Journal = env['account.journal'].with_company(company)
    for journal_type, chart_code, suffix, name in JOURNAL_CODES:
        code = f"{company.code}{suffix}"
        if Journal.search_count([('company_id', '=', company.id), ('code', '=', code)]):
            continue
        journal = Journal.search([
            ('company_id', '=', company.id),
            ('type', '=', journal_type),
            ('code', '=', chart_code),
        ], limit=1) or Journal.search([
            ('company_id', '=', company.id),
            ('type', '=', journal_type),
        ], order='sequence, id', limit=1)
        if journal:
            journal.code = code
        else:
            Journal.create({
                'name': f"{company.code} {name}",
                'code': code,
                'type': journal_type,
                'company_id': company.id,
            })
    _logger.info("Coded the journals of %s", company.name)


def _grant_entities(env, companies):
    """Give the administrator the entities, so the group can be set up.

    Only the administrator is granted. Every entity keeps its own data, so the
    other users are assigned to the entity they work for, one by one, instead
    of being handed the whole group: company_ids is what the company switcher
    offers, and a user who is not on an entity cannot read its records.

    The __system__ user is deliberately left alone. Once every module is
    loaded, account fires the chart template it guessed while l10n_eg was
    installing, and it fires it on env.company, which is the default company of
    __system__. Pointing that user at an entity makes account load a second
    chart over that entity's own: the codes differ, so account.chart.template
    ._load() treats it as a new chart and deletes the accounting records of the
    company first, taking its journals with them. Leaving __system__ on the
    database's main company keeps that load where it is harmless.
    """
    admin = env.ref('base.user_admin', raise_if_not_found=False)
    if not admin or admin.id == SUPERUSER_ID:
        return
    admin.write({'company_ids': [Command.link(company.id) for company in companies]})
    _logger.info("Granted %s entities to %s", len(companies), admin.login)


def _retire_main_company(env, companies):
    """Take the database's main company out of the way of the real users.

    The group runs on its own entities, so My Company has no place in the
    company switcher. Dropping it from the company_ids of the users is what
    removes it: the switcher and the company list only ever offer the
    companies a user is allowed on, so it stops existing as far as they are
    concerned.

    It is neither deleted nor archived. base.main_company is reached by ref=
    from the data files of base and of many other modules, so a database
    missing it breaks the next module install or update. And __system__ keeps
    it as its default company (see _grant_entities), so archiving it leaves
    that user pointing at an inactive company: every user then created in its
    name -- an invite, a signup, a test -- takes it as a default company_id
    that is missing from company_ids, and fails the constraint that the two
    agree.
    """
    main = env.ref('base.main_company', raise_if_not_found=False)
    if not main or not companies:
        return
    admin = env.ref('base.user_admin', raise_if_not_found=False)
    if admin and admin.id != SUPERUSER_ID:
        # Command.unlink drops the membership only; the company itself stays.
        admin.write({
            'company_id': companies[0].id,
            'company_ids': [Command.unlink(main.id)],
        })
        _logger.info("Took %s away from %s", main.name, admin.login)


def _load_dev_staff(env, companies):
    """Create the demo staff of the group, on development builds only.

    Odoo.sh sets ODOO_STAGE to dev, staging or production, and these logins
    carry throwaway passwords kept in the repository, so they have no business
    existing anywhere but a development build.

    Demo data would be the usual home for them, but demo files are loaded
    before post_init_hook runs, so the companies they belong to do not exist
    yet at that point, and a build created without demo data would skip them
    altogether.
    """
    stage = os.environ.get('ODOO_STAGE')
    if stage != 'dev':
        _logger.info("ODOO_STAGE is %s, not dev: skipping the demo staff", stage or "unset")
        return
    if not companies:
        return
    Users = env['res.users'].with_context(active_test=False, no_reset_password=True)
    by_xml_id = {xml_id: company for (xml_id, *_rest), company in zip(ENTITY_COMPANIES, companies)}
    for login, name, password, company_xml_ids, groups, optional_groups in DEV_STAFF:
        allowed = companies if company_xml_ids is None else env['res.company'].browse([
            by_xml_id[xml_id].id for xml_id in company_xml_ids if xml_id in by_xml_id
        ])
        if not allowed:
            continue
        group_ids = [env.ref(xml_id).id for xml_id in groups]
        for xml_id in optional_groups:
            group = env.ref(xml_id, raise_if_not_found=False)
            if group:
                group_ids.append(group.id)
        values = {
            'name': name,
            'login': login,
            'password': password,
            'company_id': allowed[0].id,
            'company_ids': [Command.set(allowed.ids)],
            'group_ids': [Command.set(group_ids)],
            'tour_enabled': False,
        }
        user = Users.search([('login', '=', login)], limit=1)
        if user:
            user.write(values)
        else:
            user = Users.create(values)
    _logger.info("Created %s demo users on this development build", len(DEV_STAFF))
    _load_dev_invoices(env, by_xml_id)
    finish_dev_staff(env)


def finish_dev_staff(env):
    """Finish wiring the development staff once the operating model is there.

    az_group_base installs before azm_operating_model and azm_platform: they
    depend on it, so it cannot depend on them, and neither the AZM groups nor
    the AZM entities exist yet while _load_dev_staff runs. The platform calls
    this from its own hook, by which time they do.
    """
    if os.environ.get('ODOO_STAGE') != 'dev':
        return
    Users = env['res.users'].with_context(active_test=False)
    Entity = env['azm.entity'].sudo() if 'azm.entity' in env else None
    for login, _name, _password, _company_xml_ids, _groups, optional_groups in DEV_STAFF:
        user = Users.search([('login', '=', login)], limit=1)
        if not user:
            continue
        groups = [
            group for group in (
                env.ref(xml_id, raise_if_not_found=False) for xml_id in optional_groups
            ) if group
        ]
        if groups:
            user.write({'group_ids': [Command.link(group.id) for group in groups]})
        if Entity is None:
            continue
        # The operating model assigns its work per entity, not per company.
        entities = Entity.search([('company_id', 'in', user.company_ids.ids)])
        if entities:
            entities.write({'user_ids': [Command.link(user.id)]})


def _load_dev_invoices(env, by_xml_id):
    """Post customer invoices and vendor bills in every entity."""
    for rows, move_type, journal_type, account_type, date in (
        (DEV_INVOICES, 'out_invoice', 'sale', 'income', '2026-03-01'),
        (DEV_BILLS, 'in_invoice', 'purchase', 'expense', '2026-03-10'),
    ):
        for company_xml_id, partner_name, amount, label in rows:
            company = by_xml_id.get(company_xml_id)
            if company:
                _post_move(env, company, move_type, journal_type, account_type,
                           date, partner_name, amount, label)


def _post_move(env, company, move_type, journal_type, account_type, date,
               partner_name, amount, label):
    """Post one document, unless that partner already has one in that company."""
    Move = env['account.move']
    partner = env['res.partner'].search([('name', '=', partner_name)], limit=1)
    if not partner:
        partner = env['res.partner'].create({'name': partner_name, 'company_id': False})
    if Move.search_count([
        ('company_id', '=', company.id),
        ('partner_id', '=', partner.id),
        ('move_type', '=', move_type),
    ]):
        return
    journal = env['account.journal'].search([
        ('company_id', '=', company.id), ('type', '=', journal_type),
    ], limit=1)
    account = env['account.account'].search([
        ('company_ids', 'in', company.id), ('account_type', '=', account_type),
    ], limit=1)
    if not journal or not account:
        return
    move = Move.with_company(company).create({
        'move_type': move_type,
        'partner_id': partner.id,
        'journal_id': journal.id,
        'invoice_date': date,
        'invoice_line_ids': [Command.create({
            'name': label,
            'quantity': 1,
            'price_unit': amount,
            'account_id': account.id,
        })],
    })
    move.action_post()


def _activate_arabic(env):
    """Activate Arabic so the users of the group can switch their interface to it."""
    lang = env['res.lang'].with_context(active_test=False).search([('code', '=', ARABIC_LANG)], limit=1)
    if not lang or lang.active:
        return
    env['base.language.install'].create({'lang_ids': [Command.set(lang.ids)]}).lang_install()
    _logger.info("Activated the %s language", ARABIC_LANG)
