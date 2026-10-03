import os

from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.azm_platform.hooks import DEV_ENTITY_DATA, ENTITY_PROFILES


@tagged('post_install', '-at_install')
class TestEntityWiring(TransactionCase):
    """The entity cards read from the source apps, so the wiring has to hold."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.entities = cls.env['res.company'].browse([
            cls.env.ref(xml_id).id for xml_id in ENTITY_PROFILES
            if cls.env.ref(xml_id, raise_if_not_found=False)
        ])

    def test_every_entity_is_described(self):
        """An entity without a type shows as an untyped card with no subtitle."""
        if not self.entities:
            self.skipTest("az_group_base is not installed")
        for xml_id, (entity_type, sector, _tagline) in ENTITY_PROFILES.items():
            company = self.env.ref(xml_id, raise_if_not_found=False)
            if not company:
                continue
            self.assertEqual(company.azm_entity_type, entity_type)
            self.assertEqual(company.azm_sector, sector)
            self.assertTrue(company.azm_tagline, f"{company.name} has no tagline")

    def test_every_entity_has_a_live_dashboard(self):
        if os.environ.get('ODOO_STAGE') != 'dev':
            self.skipTest("the entity sample data is only loaded on development builds")
        for xml_id in DEV_ENTITY_DATA:
            company = self.env.ref(xml_id, raise_if_not_found=False)
            if not company:
                continue
            self.assertTrue(company.azm_department_count, f"{company.name} has no departments")
            self.assertTrue(company.azm_employee_count, f"{company.name} has no employees")
            self.assertTrue(company.azm_project_count, f"{company.name} has no projects")
            self.assertTrue(company.azm_task_count, f"{company.name} has no tasks")
            self.assertTrue(company.azm_has_data)
            self.assertEqual(
                company.azm_status, 'active',
                f"{company.name} is not active: its card would read as unstarted",
            )

    def test_the_demo_staff_can_read_their_own_headcount(self):
        """The entity card links to hr.employee, so the count needs the role.

        The count deliberately follows access rights, so a user with no HR role
        reads zero people rather than a number whose card they cannot open
        (see test_platform_counts_follow_access). The demo staff are given the
        HR role instead, so their own entity reports its real headcount.
        """
        if os.environ.get('ODOO_STAGE') != 'dev':
            self.skipTest("the demo staff only exist on development builds")
        user = self.env['res.users'].with_context(active_test=False).search(
            [('login', '=', 'fue.staff')], limit=1)
        if not user:
            self.skipTest("the demo staff only exist on development builds")
        company = user.company_ids[0]
        scoped = company.with_user(user).with_context(allowed_company_ids=[company.id])
        self.assertTrue(
            self.env['hr.employee'].with_user(user).has_access('read'),
            "the demo staff need the HR role for the headcount to mean anything",
        )
        self.assertTrue(scoped.azm_employee_count, "the entity card reports no people")
        self.assertEqual(
            scoped.azm_employee_count,
            self.env['hr.employee'].with_user(user).search_count(
                [('company_id', '=', company.id)]),
            "the card and the list behind it disagree",
        )
