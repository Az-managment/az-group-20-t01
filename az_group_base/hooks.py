import logging

from odoo import Command, SUPERUSER_ID
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# The group parent. Its chart of accounts is shared by every branch below it.
ROOT_COMPANY = ('company_az_group', 'AZG', "AZ Group", "مجموعة AZ")

# Branches of the group: xml id, entity code, legal name, Arabic name.
BRANCH_COMPANIES = [
    ('company_az_management', 'AZM', "AZ Management & Development", "AZ للإدارة والتطوير"),
    ('company_future_univ', 'FUE', "Future University in Egypt", "جامعة المستقبل – مصر"),
    ('company_malvern', 'MCE', "Malvern College Egypt", "مالفيرن كوليدج مصر"),
    ('company_alson_language', 'ALS', "Al Alson Language School", "الألسن للغات"),
    ('company_alson_tourism', 'AT3', "Al Alson Tourism School – 3-Year Program", "الألسن للسياحة – 3 سنوات"),
    ('company_alson_computer', 'ALC', "Al Alson Computer School", "الألسن للحاسبات"),
    ('company_alson_institute', 'AAI', "Al Alson Institute", "معهد الألسن"),
]

# The Arabic interface language of the group. Arabic ships inactive, and a
# language has to be active before a user can be set to it.
ARABIC_LANG = 'ar_001'

# Journal skeleton created for every branch: type, name, code suffix. Each
# entity needs its own journals so that its documents get their own sequence,
# independent from the other entities of the group.
JOURNAL_TEMPLATES = [
    ('sale', "Customer Invoices", 'IN'),
    ('purchase', "Vendor Bills", 'BL'),
    ('general', "Miscellaneous", 'MI'),
    ('bank', "Bank", 'BN'),
    ('cash', "Cash", 'CH'),
]


def post_init_hook(env):
    """Create the group companies, their chart of accounts and their journals."""
    root = _ensure_company(env, ROOT_COMPANY)
    for spec in BRANCH_COMPANIES:
        _ensure_company(env, spec, parent=root)
    _load_chart_template(env, root)
    _create_branch_journals(env, root)
    _grant_group_companies(env, root)
    _activate_arabic(env)


def _ensure_company(env, spec, parent=None):
    """Return the company of that xml id, creating it when it does not exist yet.

    The hierarchy is only ever set at creation: res.company.write refuses any
    vals holding parent_id, so an existing company is never re-parented here.
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
    if parent:
        values['parent_id'] = parent.id
    company = env['res.company'].create(values)
    env['ir.model.data']._update_xmlids([{
        'xml_id': f'az_group_base.{xml_id}',
        'record': company,
        'noupdate': True,
    }])
    _logger.info("Created company %s", name)
    return company


def _load_chart_template(env, root):
    """Load the Egyptian chart on the group parent, which every branch shares."""
    if env['account.journal'].search_count([('company_id', '=', root.id)]):
        return
    env['account.chart.template'].try_loading('eg', company=root, install_demo=False)
    _logger.info("Loaded the eg chart template on %s", root.name)


def _create_branch_journals(env, root):
    """Create the missing journals of each branch, prefixed with its entity code."""
    Journal = env['account.journal']
    branches = env['res.company'].search([('parent_id', '=', root.id)])
    existing = {
        (journal.company_id.id, journal.code)
        for journal in Journal.search([('company_id', 'in', branches.ids)])
    }
    for branch in branches:
        if not branch.code:
            # Without a code there is no prefix to build the journals from,
            # and the branch would silently end up unable to invoice.
            raise UserError(env._(
                "Company %s has no entity code, so its journals cannot be created.",
                branch.name,
            ))
        vals_list = [
            {
                'name': f"{branch.code} {label}",
                'code': f"{branch.code}{suffix}",
                'type': journal_type,
                'company_id': branch.id,
            }
            for journal_type, label, suffix in JOURNAL_TEMPLATES
            if (branch.id, f"{branch.code}{suffix}") not in existing
        ]
        if vals_list:
            Journal.with_company(branch).create(vals_list)
            _logger.info("Created %s journals for %s", len(vals_list), branch.name)


def _grant_group_companies(env, root):
    """Give the internal users access to the group and to every branch under it.

    Each branch is granted explicitly. company_ids is the exact list the
    company switcher offers and it does not follow parent_id: granting only
    the root leaves every branch out of the switcher, so the users cannot
    reach the branches at all and the whole multi-entity setup is unusable.

    The __system__ user is deliberately left alone. Once every module is
    loaded, account fires the chart template it guessed while l10n_eg was
    installing, and it fires it on env.company, which is the default company of
    __system__. Pointing that user at the group makes account load a second
    chart over the group's own: the codes differ, so account.chart.template
    ._load() treats it as a new chart and deletes the accounting records of the
    company and of its children first, taking the branch journals with them.
    Leaving __system__ on the database's main company keeps that load where it
    is harmless.
    """
    companies = env['res.company'].search([('id', 'child_of', root.id)])
    users = env['res.users'].with_context(active_test=False).search([
        ('share', '=', False),
        ('id', '!=', SUPERUSER_ID),
    ])
    if not users:
        return
    users.write({
        'company_ids': [Command.link(company.id) for company in companies],
        'company_id': root.id,
    })
    _logger.info("Granted %s companies to %s internal users", len(companies), len(users))


def _activate_arabic(env):
    """Activate Arabic so the users of the group can switch their interface to it."""
    lang = env['res.lang'].with_context(active_test=False).search([('code', '=', ARABIC_LANG)], limit=1)
    if not lang or lang.active:
        return
    env['base.language.install'].create({'lang_ids': [Command.set(lang.ids)]}).lang_install()
    _logger.info("Activated the %s language", ARABIC_LANG)
