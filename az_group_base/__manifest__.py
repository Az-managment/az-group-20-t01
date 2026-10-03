{
    'name': "AZ Group Companies",
    'version': '20.0.1.7.0',
    'author': "AZ Group",
    'summary': "AZ Group company structure, Egyptian localization and per-entity journals",
    'description': """
AZ Group company structure
==========================

Declares AZ Group and its subsidiaries as companies, each carrying an entity
code and an Arabic name. The subsidiaries are branches of AZ Group, so they
share the group chart of accounts while keeping their own journals and their
own document sequences.
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
