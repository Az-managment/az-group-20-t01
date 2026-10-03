{
    'name': "AZ Group Companies",
    'version': '20.0.2.2.0',
    'author': "AZ Group",
    'summary': "AZ Group entities as independent companies, Egyptian localization and per-entity journals",
    'description': """
AZ Group company structure
==========================

Declares the entities of the group as companies, each carrying an entity code
and an Arabic name. Every entity is an independent company: it owns its
Egyptian chart of accounts, its journals and its document sequences, and it
reads no data from any other entity.

The entities are deliberately not branches of a holding company. A branch
shares the chart of accounts of its root and its records are visible whenever
the root is selected, which is the opposite of what the group needs.
""",
    'category': 'Accounting/Accounting',
    'license': 'LGPL-3',
    'depends': [
        'accountant',
        'l10n_eg',
        'l10n_eg_edi_eta',
    ],
    'data': [
        'data/res_currency_data.xml',
        'views/res_company_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
}
