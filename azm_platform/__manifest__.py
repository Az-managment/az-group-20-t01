{
    'name': 'AZM Enterprise Operating Model Platform',
    'version': '20.0.1.2.0',
    'summary': 'One Group. Unified Systems. Stronger Tomorrow.',
    'description': """
AZM Enterprise Operating Model Platform
=======================================
A read-only cockpit over the data you already have in Odoo:

* Entities = companies (res.company), with logo, country, cover and type
* People and teams from Employees / Departments (hr)
* Work and progress from Projects / Tasks (project)
* Files from Documents (when installed) or attachments
* Home dashboard, entity pages, AZM sidebar, branded login, AI assistant
* Operating models (from AZM Operating Model): procurement cycle and unified financial
  model as "files" with KPIs, unified Assessments and Risk Register pages, Home and
  entity-page sections; entities linked to companies (auto-matched by name on install)
* Every page follows the user's role, assigned entities and the company switcher
* Arabic (RTL) and English

No data is duplicated: every figure is computed live from the source apps.
""",
    'category': 'Services/AZM',
    'author': 'AZM Group',
    'license': 'LGPL-3',
    'depends': ['mail', 'hr', 'project', 'web_hierarchy', 'auth_oauth', 'azm_operating_model'],
    'data': [
        'security/azm_security.xml',
        'views/res_company_views.xml',
        'views/res_config_settings_views.xml',
        'views/azm_menus.xml',
        'views/azm_om_views.xml',
        'views/azm_om_menus.xml',
        'views/azm_fin_question_views.xml',
        'views/login_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'azm_platform/static/src/scss/azm_variables.scss',
            'azm_platform/static/src/scss/azm_backend.scss',
            'azm_platform/static/src/components/**/*',
            'azm_platform/static/src/dashboard/**/*',
            'azm_platform/static/src/sidebar/**/*',
            'azm_platform/static/src/entity/**/*',
            'azm_platform/static/src/operating_model/**/*',
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
