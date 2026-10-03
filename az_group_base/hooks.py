import logging

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


def post_init_hook(env):
    """Create the entity companies, each with its own chart and journals."""
    companies = env['res.company']
    for spec in ENTITY_COMPANIES:
        companies |= _ensure_company(env, spec)
    for company in companies:
        _load_chart_template(env, company)
        _code_entity_journals(env, company)
    _grant_entities(env, companies)
    _activate_arabic(env)


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


def _activate_arabic(env):
    """Activate Arabic so the users of the group can switch their interface to it."""
    lang = env['res.lang'].with_context(active_test=False).search([('code', '=', ARABIC_LANG)], limit=1)
    if not lang or lang.active:
        return
    env['base.language.install'].create({'lang_ids': [Command.set(lang.ids)]}).lang_install()
    _logger.info("Activated the %s language", ARABIC_LANG)
