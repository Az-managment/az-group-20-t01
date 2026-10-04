from unittest.mock import patch

from odoo import fields
from odoo.addons.azm_platform.models.azm_documents import RETRY_BACKOFF
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestOperatingModelDocuments(TransactionCase):
    """A document per requirement (FIN.PUR.03 …) in each entity's own Documents folders."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({'name': 'AZM Docs Campus'})
        cls.other_company = cls.env['res.company'].create({'name': 'AZM Docs Other'})
        cls.env.user.company_ids = [(4, cls.company.id), (4, cls.other_company.id)]
        cls.entity = cls.company.azm_entity_ids
        cls.Pub = cls.env['azm.doc.publication']
        cls.pur = cls.env['azm.fin.module'].search([('code', '=', 'PUR')], limit=1)
        cls.requirement = cls.env['azm.fin.requirement'].search(
            [('module_id', '=', cls.pur.id)], order='sequence', limit=1)
        cls.user = new_test_user(
            cls.env, 'azm_docs_reader', company_id=cls.company.id, company_ids=[(6, 0, [cls.company.id])],
            groups='azm_platform.group_azm_user,azm_operating_model.azm_group_user')
        cls.entity.user_ids = [(4, cls.user.id)]
        cls.assessment = cls.env['azm.fin.assessment'].create({'entity_id': cls.entity.id, 'user_id': cls.user.id})
        cls.assessment.action_fill_demo()
        cls.outsider = new_test_user(
            cls.env, 'azm_docs_outsider', company_id=cls.other_company.id,
            company_ids=[(6, 0, [cls.other_company.id])],
            groups='azm_platform.group_azm_user,azm_operating_model.azm_group_user')

    def test_tree_reference(self):
        topic = self.requirement.topic_id
        self.assertTrue(self.requirement.tree_ref.startswith(f"{topic.code}."))
        refs = self.env['azm.fin.requirement'].search([]).mapped('tree_ref')
        self.assertEqual(len(refs), len(set(refs)), "every requirement has its own tree reference")
        self.assertTrue(self.requirement.display_name.startswith(self.requirement.tree_ref))

    def test_company_folders(self):
        """Model › module folders for the requirements, one folder per output type, never twice."""
        Folder = self.env['azm.doc.folder']
        Folder._ensure_all(self.company)
        count = Folder.search_count([('company_id', '=', self.company.id)])
        Folder._ensure_all(self.company)
        self.assertEqual(Folder.search_count([('company_id', '=', self.company.id)]), count)
        root = Folder._folder(self.company)
        self.assertEqual(root.name, self.company.name)
        fin = Folder._folder(self.company, 'FIN')
        self.assertEqual(fin.folder_id, root)
        pur = Folder._folder(self.company, 'FIN', (self.pur.code, f'FIN.{self.pur.code} · {self.pur.name}'))
        self.assertEqual(pur.folder_id, fin)
        self.assertEqual(Folder._folder(self.company, 'SOP').folder_id, root)
        for folder in (root, fin, pur):
            self.assertEqual(folder.company_id, self.company)

    def test_requirement_document(self):
        pub = self.Pub._get(self.company, 'requirement', requirement=self.requirement)
        pub._generate()
        self.assertEqual(pub.state, 'done')
        self.assertTrue(pub.document_id.name.startswith(self.requirement.tree_ref))
        self.assertEqual(pub.document_id.company_id, self.company)
        self.assertEqual(pub.document_id.folder_id, self.env['azm.doc.folder']._folder(
            self.company, 'FIN', (self.pur.code, f'FIN.{self.pur.code} · {self.pur.name}')))
        self.assertEqual(pub.assessment_id, self.assessment)
        self.assertFalse(pub.outdated)
        # model › module › topic › requirement, then the questions
        payload = pub._azm_payload()
        self.assertEqual([step[1] for step in payload['path']][:2], ['FIN', 'FIN.PUR'])
        self.assertEqual(payload['path'][-1][1], self.requirement.tree_ref)
        self.assertEqual(payload['items'][0]['tree_ref'], self.requirement.tree_ref)

    def test_read_and_download(self):
        line = self.assessment.answer_ids.filtered(lambda a: a.requirement_id == self.requirement)
        action = line.with_user(self.user).action_azm_doc_read()
        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertIn('download=false', action['url'])
        action = line.with_user(self.user).action_azm_doc_download()
        self.assertIn('download=true', action['url'])

    def test_document_follows_the_answers(self):
        pub = self.Pub._get(self.company, 'requirement', requirement=self.requirement)
        pub._generate()
        line = self.assessment.answer_ids.filtered(lambda a: a.requirement_id == self.requirement)
        line.write({'na': True, 'reason': 'تجربة'})
        pub.invalidate_recordset(['outdated'])
        self.assertTrue(pub.outdated)
        self.Pub._enqueue(self.company)
        self.assertEqual(pub.state, 'pending')
        pub._generate_safe()
        self.assertEqual(pub.state, 'done')
        self.assertEqual(pub._azm_payload()['items'][0]['status']['key'], 'na')
        self.assertFalse(pub.outdated)

    def test_failed_documents_retry_then_give_up(self):
        """A failure is retried on a widening backoff, and stops asking after the last one."""
        pub = self.Pub._get(self.company, 'requirement', requirement=self.requirement)
        boom = patch.object(type(pub), '_generate', side_effect=RuntimeError('renderer down'))

        with boom:
            for attempt, delay in enumerate(RETRY_BACKOFF, start=1):
                pub.write({'attempts': attempt - 1, 'retry_after': False})
                pub._generate_safe()
                self.assertEqual(pub.state, 'error')
                self.assertEqual(pub.attempts, attempt)
                self.assertTrue(pub.retry_after, "a document with retries left asks to come back")
                minutes = (pub.retry_after - fields.Datetime.now()).total_seconds() / 60
                self.assertAlmostEqual(minutes, delay, delta=1, msg=f"attempt {attempt} waits {delay} min")
                # it is not due yet, so the queue leaves it alone
                self.assertNotIn(pub, self.Pub.search(self.Pub._due_domain()))
                # once the backoff has elapsed the queue picks it up again
                self.assertIn(pub, self.Pub.search(self.Pub._due_domain(pub.retry_after)))

            # one failure past the last backoff: it stops asking
            pub._generate_safe()
            self.assertEqual(pub.attempts, len(RETRY_BACKOFF) + 1)
            self.assertFalse(pub.retry_after)
            self.assertNotIn(pub, self.Pub.search(self.Pub._due_domain(fields.Datetime.now())))

        # a human pressing Refresh hands the budget back, and a render clears the slate
        pub.action_refresh()
        self.assertEqual(pub.state, 'done')
        self.assertEqual(pub.attempts, 0)
        self.assertFalse(pub.retry_after)
        self.assertFalse(pub.error)

    def test_a_failure_from_before_the_backoff_existed_is_due_at_once(self):
        pub = self.Pub._get(self.company, 'requirement', requirement=self.requirement)
        pub.write({'state': 'error', 'error': 'old', 'attempts': 0, 'retry_after': False})
        self.assertIn(pub, self.Pub.search(self.Pub._due_domain()))

    def test_other_entities_cannot_read(self):
        pub = self.Pub._get(self.company, 'requirement', requirement=self.requirement)
        pub._generate()
        with self.assertRaises(AccessError):
            pub.with_user(self.outsider).action_read()

    def test_module_outputs_and_summary(self):
        pubs = self.Pub._ensure_company(self.company)
        self.assertEqual(len(pubs.filtered(lambda p: p.kind == 'requirement')),
                         self.env['azm.fin.requirement'].search_count([]))
        summary = pubs.filtered(lambda p: p.kind == 'summary')
        summary._generate()
        self.assertEqual(summary.state, 'done')
        outputs = pubs.filtered(lambda p: p.kind == 'module' and p.module_id == self.pur)
        outputs._generate_safe()
        self.assertFalse(outputs.filtered(lambda p: p.state == 'error'), outputs.mapped('error'))
        for pub in outputs.filtered(lambda p: p.state == 'done'):
            payload = pub._azm_payload()
            # grouped under their topic, in tree order
            self.assertTrue(payload['groups'])
            self.assertTrue(all(group['items'] for group in payload['groups']))

    def test_company_without_assessment_gets_a_blank_sheet(self):
        pub = self.Pub._get(self.other_company, 'requirement', requirement=self.requirement)
        pub._generate()
        self.assertEqual(pub.state, 'done')
        item = pub._azm_payload()['items'][0]
        self.assertEqual(item['status']['key'], 'open')
        self.assertTrue(item['pending'], "the blank sheet lists the questions to answer")
