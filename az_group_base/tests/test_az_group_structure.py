from odoo.tests import TransactionCase

from odoo.addons.az_group_base.hooks import BRANCH_COMPANIES, JOURNAL_TEMPLATES, post_init_hook


class TestAzGroupStructure(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root = cls.env.ref('az_group_base.company_az_group')
        cls.branches = cls.env['res.company'].search([('parent_id', '=', cls.root.id)])

    def _sale_journal(self, company):
        return self.env['account.journal'].search([
            ('company_id', '=', company.id),
            ('type', '=', 'sale'),
        ], limit=1)

    def _post_invoice(self, company, partner):
        account = self.env['account.account'].with_company(company).search([
            ('account_type', '=', 'income'),
        ], limit=1)
        invoice = self.env['account.move'].with_company(company).create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'journal_id': self._sale_journal(company).id,
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

    def test_every_branch_hangs_under_the_group(self):
        self.assertEqual(len(self.branches), len(BRANCH_COMPANIES))
        self.assertEqual(
            sorted(self.branches.mapped('code')),
            sorted(code for _xml_id, code, _name, _name_ar in BRANCH_COMPANIES),
        )
        for branch in self.branches:
            self.assertEqual(branch.parent_id, self.root)
            self.assertEqual(branch.root_id, self.root)

    def test_entity_code_and_arabic_name_are_set(self):
        for _xml_id, code, name, name_ar in BRANCH_COMPANIES:
            branch = self.branches.filtered(lambda company: company.code == code)
            self.assertEqual(branch.name, name)
            self.assertEqual(branch.name_ar, name_ar)

    def test_branches_share_the_group_chart_of_accounts(self):
        group_accounts = self.env['account.account'].with_company(self.root).search([])
        self.assertTrue(group_accounts)
        for branch in self.branches:
            branch_accounts = self.env['account.account'].with_company(branch).search([])
            self.assertTrue(group_accounts <= branch_accounts)

    def test_each_branch_owns_its_journals(self):
        for branch in self.branches:
            journals = self.env['account.journal'].search([('company_id', '=', branch.id)])
            self.assertEqual(len(journals), len(JOURNAL_TEMPLATES))
            self.assertEqual(
                sorted(journals.mapped('code')),
                sorted(f"{branch.code}{suffix}" for _type, _label, suffix in JOURNAL_TEMPLATES),
            )

    def test_branch_invoice_sequences_are_independent(self):
        partner = self.env['res.partner'].create({'name': "Test Student", 'company_id': False})
        first, second = self.branches[:2]
        first_invoice = self._post_invoice(first, partner)
        second_invoice = self._post_invoice(second, partner)
        self.assertEqual(first_invoice.company_id, first)
        self.assertEqual(second_invoice.company_id, second)
        self.assertTrue(first_invoice.name.startswith(f"{first.code}IN"))
        self.assertTrue(second_invoice.name.startswith(f"{second.code}IN"))
        self.assertNotEqual(first_invoice.name, second_invoice.name)

    def test_the_group_runs_on_the_egyptian_chart(self):
        self.assertEqual(self.root.chart_template, 'eg')
        for branch in self.branches:
            self.assertEqual(branch.chart_template, 'eg')

    def test_the_main_company_is_left_alone(self):
        """The main company is what keeps account's late chart load harmless.

        account installs the chart it guessed while l10n_eg was loading on
        env.company, the default company of __system__, once every module is
        loaded. Should that be the group, the load runs over the group's own
        chart and deletes the accounting records of the group and its branches.
        """
        main = self.env.ref('base.main_company')
        self.assertTrue(main.active)
        self.assertNotEqual(self.env.ref('base.user_root').company_id, self.root)

    def test_internal_users_work_in_the_group(self):
        admin = self.env.ref('base.user_admin')
        self.assertIn(self.root, admin.company_ids)
        self.assertEqual(admin.company_id, self.root)

    def test_post_init_hook_is_idempotent(self):
        companies_before = self.env['res.company'].search_count([])
        journals_before = self.env['account.journal'].search_count([])
        post_init_hook(self.env)
        self.assertEqual(self.env['res.company'].search_count([]), companies_before)
        self.assertEqual(self.env['account.journal'].search_count([]), journals_before)
