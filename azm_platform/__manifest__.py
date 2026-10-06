{
    'name': 'AZM Enterprise Operating Model Platform',
    'version': '20.0.1.34.0',
    'summary': 'One Group. Unified Systems. Stronger Tomorrow.',
    'description': """
AZM Enterprise Operating Model Platform
=======================================
A read-only cockpit over the data you already have in Odoo:

* Entities = companies (res.company), with logo, country, cover and type
* People and teams from Employees / Departments (hr)
* Work and progress from Projects / Tasks (project)
* Files from Documents, one workspace per entity
* Home dashboard, entity pages, AZM sidebar, branded login, AI assistant
* Operating models (from AZM Operating Model): procurement cycle and unified financial
  model as "files" with KPIs, unified Assessments and Risk Register pages, Home and
  entity-page sections; entities linked to companies (auto-matched by name on install)
* Every page follows the user's role, assigned entities and the company switcher
* A document per requirement (FIN.PUR.03 …) and per module output (policies, SOPs, authority,
  KPIs …) for every entity, filed in its own Documents folders and kept in step with the answers
* Arabic (RTL) and English

No data is duplicated: every figure is computed live from the source apps.
""",
    'category': 'Services/AZM',
    'author': 'AZM Group',
    'license': 'LGPL-3',
    'depends': [
        'az_group_base',
        'mail', 'hr', 'project', 'documents', 'web_hierarchy', 'auth_oauth',
        'azm_operating_model',
    ],
    'data': [
        'security/azm_security.xml',
        'security/ir.access.csv',
        'views/res_company_views.xml',
        'views/res_config_settings_views.xml',
        'views/azm_menus.xml',
        'views/azm_om_views.xml',
        'views/azm_om_menus.xml',
        'views/login_templates.xml',
        'report/azm_doc_report.xml',
        'views/azm_doc_views.xml',
        'data/azm_doc_cron.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'azm_platform/static/src/scss/azm_variables.scss',
            'azm_platform/static/src/scss/azm_backend.scss',
            'azm_platform/static/src/components/**/*',
            'azm_platform/static/src/dashboard/**/*',
            'azm_platform/static/src/sidebar/**/*',
            'azm_platform/static/src/entity/**/*',
            'azm_platform/static/src/library/**/*',
            'azm_platform/static/src/my_work/**/*',
            'azm_platform/static/src/progress/**/*',
            'azm_platform/static/src/operating_model/**/*',
        ],
        'web.report_assets_common': [
            'azm_platform/static/src/report/azm_doc_report.scss',
        ],
        'web.assets_tests': [
            'azm_platform/static/tests/**/*',
        ],
        'web.assets_frontend': [
            'azm_platform/static/src/scss/azm_variables.scss',
            'azm_platform/static/src/login/**/*',
        ],
    },
    'post_init_hook': '_azm_post_init',
    'application': True,
    'installable': True,
}
