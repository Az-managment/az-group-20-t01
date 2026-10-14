import os
from unittest.mock import patch

from odoo.tests import TransactionCase

from odoo.addons.az_group_base.hooks import (
    CHART_TEMPLATE,
    DEV_BILLS,
    DEV_INVOICES,
    DEV_STAFF,
    ENTITY_COMPANIES,
    JOURNAL_CODES,
    _load_dev_staff,
    post_init_hook,
)


class TestAzGroupStructure(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.entities = cls.env['res.company'].browse([
            cls.env.ref(f'az_group_base.{xml_id}').id
            for xml_id, *_rest in ENTITY_COMPANIES
        ])

    def _journal(self, company, journal_type):
        return self.env['account.journal'].search([
            ('company_id', '=', company.id),
            ('type', '=', journal_type),
        ], limit=1)

    def _post_invoice(self, company, partner):
        account = self.env['account.account'].with_company(company).search([
            ('account_type', '=', 'income'),
        ], limit=1)
        invoice = self.env['account.move'].with_company(company).create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'journal_id': self.env['account.journal'].search([
                ('company_id', '=', company.id), ('type', '=', 'sale'),
            ], limit=1).id,
            'invoice_date': '2026-01-01',
            'invoice_line_ids': [(0, 0, {
                'name': "Tuition",
                'quantity': 1,
                'price_unit': 1000.0,
                'account_id': account.id,
            })],
        })
        invoice.action_post()
        return invoice

    def test_every_entity_stands_on_its_own(self):
        self.assertEqual(len(self.entities), len(ENTITY_COMPANIES))
        self.assertEqual(
            sorted(self.entities.mapped('code')),
            sorted(code for _xml_id, code, _name, _name_ar in ENTITY_COMPANIES),
        )
        for entity in self.entities:
            self.assertFalse(entity.parent_id, f"{entity.name} must not hang under a parent")
            self.assertEqual(entity.root_id, entity)

    def test_entity_code_and_arabic_name_are_set(self):
        for _xml_id, code, name, name_ar in ENTITY_COMPANIES:
            entity = self.entities.filtered(lambda company: company.code == code)
            self.assertEqual(entity.name, name)
            self.assertEqual(entity.name_ar, name_ar)

    def test_each_entity_owns_its_chart_of_accounts(self):
        """No entity reads the accounts of another one.

        Ownership is read from account.account.company_ids rather than from a
        search run with_company: with_company only picks the default company of
        the environment, it does not narrow the search, so an administrator
        allowed on every entity would get the same accounts every time.
        """
        Account = self.env['account.account']
        owned = {}
        for entity in self.entities:
            self.assertEqual(entity.chart_template, CHART_TEMPLATE)
            accounts = Account.search([('company_ids', 'in', entity.id)])
            self.assertTrue(accounts, f"{entity.name} has no accounts of its own")
            owned[entity.id] = accounts
        for entity in self.entities:
            for other in self.entities - entity:
                self.assertFalse(
                    owned[entity.id] & owned[other.id],
                    f"{entity.name} shares accounts with {other.name}",
                )

    def test_each_entity_codes_its_journals(self):
        for entity in self.entities:
            for journal_type, _chart_code, suffix, _name in JOURNAL_CODES:
                journal = self._journal(entity, journal_type)
                self.assertTrue(journal, f"{entity.name} has no {journal_type} journal")
                self.assertEqual(journal.code, f"{entity.code}{suffix}")

    def test_entity_invoice_sequences_are_independent(self):
        partner = self.env['res.partner'].create({'name': "Test Student", 'company_id': False})
        first, second = self.entities[:2]
        first_invoice = self._post_invoice(first, partner)
        second_invoice = self._post_invoice(second, partner)
        self.assertEqual(first_invoice.company_id, first)
        self.assertEqual(second_invoice.company_id, second)
        self.assertTrue(first_invoice.name.startswith(f"{first.code}IN"))
        self.assertTrue(second_invoice.name.startswith(f"{second.code}IN"))
        self.assertNotEqual(first_invoice.name, second_invoice.name)

    def test_the_group_company_is_gone(self):
        """AZ Group is not a company: the entities are the whole group."""
        self.assertFalse(self.env.ref('az_group_base.company_az_group', raise_if_not_found=False))
        self.assertFalse(self.env['res.company'].search([('name', '=', "AZ Group")]))

    def test_the_main_company_is_out_of_the_way_but_alive(self):
        """My Company leaves the switcher, stays in the database, stays active.

        base.main_company is reached by ref= from the data files of base and of
        many other modules, so a database missing it breaks the next module
        install or update. It also keeps account's late chart load harmless:
        account installs the chart it guessed while l10n_eg was loading on
        env.company, the default company of __system__, once every module is
        loaded. Should that be an entity, the load runs over that entity's own
        chart and deletes its accounting records.

        It stays active because __system__ sits on it: an inactive default
        company makes every user created in that user's name fail the
        constraint that company_id is one of company_ids.
        """
        main = self.env.ref('base.main_company')
        self.assertTrue(main.active, "__system__ would default to a dead company")
        self.assertEqual(self.env.ref('base.user_root').company_id, main)
        self.assertNotIn(main, self.env.ref('base.user_admin').company_ids)
        self.assertNotIn(main, self.entities)

    def test_a_user_can_be_created_in_the_name_of_system(self):
        """Regression: archiving My Company broke every superuser user create."""
        user = self.env['res.users'].with_user(self.env.ref('base.user_root')).create({
            'name': "Created By System",
            'login': 'created.by.system',
        })
        self.assertTrue(user.company_id.active)
        self.assertIn(user.company_id, user.company_ids)

    def test_the_administrator_works_in_an_entity(self):
        admin = self.env.ref('base.user_admin')
        self.assertIn(admin.company_id, self.entities)
        self.assertNotIn(self.env.ref('base.main_company'), admin.company_ids)

    def test_the_administrator_can_reach_every_entity(self):
        admin = self.env.ref('base.user_admin')
        for entity in self.entities:
            self.assertIn(entity, admin.company_ids)

    def test_dev_staff_is_scoped_to_its_entities(self):
        if os.environ.get('ODOO_STAGE') != 'dev':
            self.skipTest("the demo staff is only created on development builds")
        Users = self.env['res.users'].with_context(active_test=False)
        for login, _name, _password, company_xml_ids, *_groups in DEV_STAFF:
            user = Users.search([('login', '=', login)], limit=1)
            self.assertTrue(user, f"{login} was not created")
            if company_xml_ids is None:
                expected = set(self.entities.ids)
            else:
                expected = {
                    self.env.ref(f'az_group_base.{xml_id}').id
                    for xml_id in company_xml_ids
                }
            self.assertEqual(
                set(user.company_ids.ids), expected,
                f"{login} does not see exactly the entities it was given",
            )

    def test_demo_staff_never_leaves_a_development_build(self):
        """The throwaway logins must not be created on staging or production.

        Renaming a user and checking the rename survives proves the hook
        returned before writing anything, which a plain user count would not:
        the logins already exist here, so running the hook would quietly reset
        their passwords instead of adding a row.
        """
        Users = self.env['res.users'].with_context(active_test=False)
        user = Users.search([('login', '=', DEV_STAFF[0][0])], limit=1)
        if not user:
            self.skipTest("the demo staff is only created on development builds")
        user.name = "Renamed By Test"
        for stage in ('staging', 'production'):
            with patch.dict(os.environ, {'ODOO_STAGE': stage}):
                _load_dev_staff(self.env, self.entities)
            self.assertEqual(
                user.name, "Renamed By Test",
                f"a {stage} build must leave the demo logins alone",
            )

    def test_post_init_hook_is_idempotent(self):
        companies_before = self.env['res.company'].search_count([])
        journals_before = self.env['account.journal'].search_count([])
        accounts_before = self.env['account.account'].search_count([])
        post_init_hook(self.env)
        self.assertEqual(self.env['res.company'].search_count([]), companies_before)
        self.assertEqual(self.env['account.journal'].search_count([]), journals_before)
        self.assertEqual(self.env['account.account'].search_count([]), accounts_before)

    def test_every_entity_keeps_books_of_its_own(self):
        """Each entity has both sides of its ledger, and shares neither."""
        if os.environ.get('ODOO_STAGE') != 'dev':
            self.skipTest("the sample documents are only posted on development builds")
        Move = self.env['account.move']
        expected_invoices = {xml_id for xml_id, *_rest in DEV_INVOICES}
        expected_bills = {xml_id for xml_id, *_rest in DEV_BILLS}
        seen = {}
        for xml_id in expected_invoices | expected_bills:
            company = self.env.ref(f'az_group_base.{xml_id}', raise_if_not_found=False)
            if not company:
                continue
            for move_type, expected in (('out_invoice', expected_invoices),
                                        ('in_invoice', expected_bills)):
                moves = Move.search([
                    ('company_id', '=', company.id),
                    ('move_type', '=', move_type),
                    ('state', '=', 'posted'),
                ])
                if xml_id in expected:
                    self.assertTrue(
                        moves, f"{company.name} has no posted {move_type}")
                seen.setdefault(move_type, {})[company.id] = set(moves.ids)
        # No document is counted in two entities at once.
        for move_type, by_company in seen.items():
            for company_id, ids in by_company.items():
                for other_id, other_ids in by_company.items():
                    if other_id != company_id:
                        self.assertFalse(
                            ids & other_ids,
                            f"two entities share the same {move_type}",
                        )

    def test_the_entity_code_prefixes_both_sides(self):
        """Customer invoices and vendor bills both number under the entity."""
        if os.environ.get('ODOO_STAGE') != 'dev':
            self.skipTest("the sample documents are only posted on development builds")
        Move = self.env['account.move']
        for entity in self.entities:
            for move_type, suffix in (('out_invoice', 'IN'), ('in_invoice', 'BL')):
                move = Move.search([
                    ('company_id', '=', entity.id),
                    ('move_type', '=', move_type),
                    ('state', '=', 'posted'),
                ], limit=1)
                if not move:
                    continue
                self.assertTrue(
                    move.name.startswith(f"{entity.code}{suffix}"),
                    f"{move.name} does not carry the code of {entity.name}",
                )
