{
    "name": "AZM Operating Model",
    "summary": "توثيق نموذج التشغيل بالأسئلة: من الإجابة إلى السياسة والإجراء والرسم والمخاطر",
    "description": """
AZM – Enterprise Operating Model
================================
يحوّل إجابات اختيار من متعدد إلى وثائق تشغيلية لكل كيان:
السياسة، الإجراء، رسم الدورة، مصفوفة الصلاحيات، النواقص،
سجل المخاطر المرشحة، الضوابط المقترحة، متطلبات النظام واختبارات القبول، ومؤشرات المتابعة.

يغطي نموذجين للتشغيل في نفس الموديول:
* دورة المشتريات كاملة (الحوكمة + 12 مرحلة تشغيلية، 396 سؤال)
* النموذج المالي الموحد (19 موديول، 215 موضوع فرعي، 167 متطلب، 1136 سؤال: اختيار واحد، اختيار متعدد، رقم، جدول؛ بشروط ظهور وأسئلة افتتاحية مقترحة لكل موضوع)
""",
    "version": "20.0.1.21.0",
    "category": "Productivity",
    "author": "Fue-Team",
    "license": "LGPL-3",
    "depends": ["mail"],
    "data": [
        "security/azm_security.xml",
        "security/ir.access.csv",
        "data/azm_sequence_data.xml",
        "data/azm_fin_sequence_data.xml",
        "views/azm_entity_views.xml",
        "views/azm_stage_views.xml",
        "views/azm_question_views.xml",
        "views/azm_risk_rule_views.xml",
        "views/azm_finding_views.xml",
        "views/azm_assessment_views.xml",
        "views/azm_fin_catalogue_views.xml",
        "views/azm_fin_assessment_views.xml",
        "views/azm_menus.xml",
        # after the menus: its menuitem hangs off azm_menu_root, and a data file may
        # only point at an external ID that an earlier file has already created. This
        # sat before them and so could never be installed from scratch -- an update
        # found the root already in ir_model_data and passed, which is why it broke
        # only on a fresh database.
        "views/azm_assignment_views.xml",
        "views/azm_fin_menus.xml",
        "report/azm_assessment_reports.xml",
        "report/azm_assessment_templates.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "azm_operating_model/static/src/**/*",
        ],
        "web.report_assets_common": [
            "azm_operating_model/static/src/workspace/azm_output.scss",
        ],
    },
    "post_init_hook": "_azm_post_init",
    "application": True,
}
