from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.azm_platform.models.azm_proc_documents import PROC_OUTPUTS, PROC_TAB_ORDER


@tagged('post_install', '-at_install')
class TestProcDocuments(TransactionCase):
    """The cycle's documents: same record, same report, same folders as the financial ones."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({'name': 'AZM Docs Campus'})
        cls.env.user.company_ids = [(4, cls.company.id)]
        cls.entity = cls.company.azm_entity_ids
        cls.assessment = cls.env['azm.assessment'].create({
            'entity_id': cls.entity.id, 'purchase_kind': 'subscriptions', 'scenario': 'petty_cash',
        })
        cls.assessment.action_fill_demo()
        cls.Pub = cls.env['azm.doc.publication']
        cls.question = cls.env['azm.question'].search([], limit=1)
        cls.stage = cls.question.stage_id

    def test_the_cycle_gets_a_document_for_every_node(self):
        """A sheet per question, every output of every stage, and one cycle summary."""
        pubs = self.Pub.sudo()._ensure_company(self.company)
        mine = pubs.filtered(lambda p: p.kind in ('question', 'stage', 'cycle'))
        self.assertEqual(len(mine.filtered(lambda p: p.kind == 'question')),
                         self.env['azm.question'].search_count([]))
        self.assertEqual(len(mine.filtered(lambda p: p.kind == 'stage')),
                         self.env['azm.stage'].search_count([]) * len(PROC_TAB_ORDER),
                         "every stage carries every output the engine writes")
        self.assertEqual(len(mine.filtered(lambda p: p.kind == 'cycle')), 1)
        self.assertEqual(set(mine.mapped('build')), {'on_open'},
                         "the cycle's documents are built when first read, not all at once")

    def test_the_queue_leaves_the_on_open_documents_alone(self):
        """They would be hundreds of megabytes of PDFs nobody asked to read."""
        self.Pub.sudo()._enqueue(self.company, force=True)
        queued = self.Pub.sudo().search(
            [('company_id', '=', self.company.id)] + self.Pub._due_domain())
        self.assertTrue(queued, "the financial documents are still queued")
        self.assertFalse(queued.filtered(lambda p: p.build == 'on_open'))
        self.assertFalse(queued.filtered(lambda p: p.kind in ('question', 'stage', 'cycle')))

    def test_a_question_sheet_says_what_a_requirement_sheet_says(self):
        """Same payload, so the report draws both the same way."""
        question = self.Pub.sudo()._get(self.company, 'question', question=self.question)._azm_payload()
        requirement = self.Pub.sudo()._get(
            self.company, 'requirement',
            requirement=self.env['azm.fin.requirement'].search([], limit=1))._azm_payload()
        self.assertEqual(set(question), set(requirement),
                         "every document of the group is the same kind of object")
        self.assertTrue(question['single'])
        self.assertEqual(len(question['items']), 1)
        self.assertEqual([step[0] for step in question['path']],
                         ['الدورة', 'المرحلة', 'المجموعة', 'السؤال'])
        self.assertIn(question['items'][0]['status']['key'],
                      ('full', 'partial', 'unavailable', 'unknown', 'na', 'open'),
                      "a question's answer is said in the vocabulary the documents already use")

    def test_an_output_is_filed_where_that_kind_of_output_belongs(self):
        for tab in PROC_TAB_ORDER:
            pub = self.Pub.sudo()._get(self.company, 'stage', stage=self.stage, tab=tab)
            self.assertEqual(pub._folder_key()[0], PROC_OUTPUTS[tab][0])
        policy = self.Pub.sudo()._get(self.company, 'stage', stage=self.stage, tab='pur_policy')
        payload = policy._azm_payload()
        self.assertTrue(payload['html'], "the engine writes the body of an output; the document wraps it")
        self.assertTrue(payload['code'].startswith('AZM-PUR-POL-'),
                        "an output is coded the way the registry codes it")

    def test_a_document_is_built_the_first_time_it_is_opened(self):
        pub = self.Pub.sudo()._get(self.company, 'question', question=self.question)
        self.assertEqual(pub.state, 'pending')
        self.assertFalse(pub.document_id)

        self.env['azm.dashboard'].with_company(self.company).open_tree_document(
            kind='question', node_id=self.question.id, company_id=self.company.id)

        pub.invalidate_recordset()
        self.assertEqual(pub.state, 'done')
        self.assertTrue(pub.document_id, "the document is filed in Documents, like every other")
        self.assertEqual(pub.document_id.company_id, self.company)
        self.assertEqual(pub.proc_assessment_id, self.assessment,
                         "it records the assessment it was built from")

    def test_the_document_follows_the_answer(self):
        """Change what the entity answered and the document is no longer current."""
        pub = self.Pub.sudo()._get(self.company, 'question', question=self.question)
        stamp = pub._current_stamp()
        answer = self.assessment.answer_ids.filtered(lambda a: a.question_id == self.question)
        other = self.question.option_ids.filtered(lambda o: o != answer.option_id)[:1]
        self.assertTrue(other, "the question offers more than one answer")
        answer.option_id = other
        self.assertNotEqual(pub._current_stamp(), stamp)

    def test_a_sheet_ages_when_a_sibling_answer_changes_what_is_asked(self):
        """Whether a question is asked at all is decided by its stage, so the sheet
        depends on the stage — not only on its own line, which never moved."""
        driver = self.env['azm.question'].search([('condition', '!=', False)], limit=1)
        self.assertTrue(driver, "the catalogue has at least one conditional question")
        import json
        field = json.loads(driver.condition).get('field')
        sibling = self.env['azm.question'].search(
            [('stage_id', '=', driver.stage_id.id), ('key', '=', field)], limit=1)
        self.assertTrue(sibling, "the condition names a question of the same stage")

        pub = self.Pub.sudo()._get(self.company, 'question', question=driver)
        stamp = pub._current_stamp()
        line = self.assessment.answer_ids.filtered(lambda a: a.question_id == sibling)
        other = sibling.option_ids.filtered(lambda o: o != line.option_id)[:1]
        self.assertTrue(other)
        line.option_id = other
        self.assertNotEqual(pub._current_stamp(), stamp,
                            "the sheet of a question is aged by its stage, not just its own answer")

    def test_a_question_sheet_is_filed_under_its_stage(self):
        """Not loose in the drawer internal users file their own manuals into."""
        pub = self.Pub.sudo()._get(self.company, 'question', question=self.question)
        key, sub = pub._folder_key()
        self.assertEqual(key, 'PUR')
        self.assertEqual(sub[0], self.stage.code)
        folder = self.env['azm.doc.folder']._folder(self.company, key, sub)
        self.assertEqual(folder.access_internal, 'view')
        self.assertIn(self.stage.code, folder.name)

    def test_a_document_can_be_read_without_leaving_the_tree(self):
        """The preview hands the page what it needs to show the document in place."""
        found = self.env['azm.dashboard'].with_company(self.company).preview_tree_document(
            kind='question', node_id=self.question.id, company_id=self.company.id)
        self.assertTrue(found['url'].startswith('/web/content/'))
        self.assertIn(self.question.code, found['name'])
        # _generate falls back to HTML when the PDF renderer is unavailable, and the
        # preview shows whichever came out — so the test asks for either, not for luck
        self.assertIn(found['mimetype'], ('application/pdf', 'text/html'))
        self.assertIn(self.stage.code, found['folder'],
                      "the preview says which shelf the document sits on")
        self.assertFalse(found['outdated'])

        pub = self.Pub.sudo()._get(self.company, 'question', question=self.question)
        self.assertEqual(pub.state, 'done', "previewing builds it, like opening it does")

    def test_the_preview_is_refused_the_same_way_the_opening_is(self):
        from odoo.exceptions import UserError as _UserError
        D = self.env['azm.dashboard'].with_company(self.company)
        with self.assertRaises(_UserError):
            D.preview_tree_document(kind='stage', node_id=self.stage.id,
                                    company_id=self.company.id)   # no output named

    def test_a_document_whose_file_vanished_is_built_again(self):
        """The filestore's collector has taken a file out from under a published
        document before; the reader gets the document, not a broken link."""
        import os
        pub = self.Pub.sudo()._get(self.company, 'question', question=self.question)
        pub._generate_safe()
        self.assertEqual(pub.state, 'done')
        attachment = pub.document_id.attachment_id
        path = os.path.join(attachment._filestore(), attachment.store_fname)
        os.remove(path)
        self.assertTrue(pub._file_missing())

        self.env['azm.dashboard'].with_company(self.company).open_tree_document(
            kind='question', node_id=self.question.id, company_id=self.company.id)
        pub.invalidate_recordset()
        self.assertFalse(pub._file_missing(), "it was built again rather than served broken")

    # ------------------------------------------------------------------ the boundary
    def test_a_document_of_another_entity_is_not_opened(self):
        """open_tree_document is reachable over RPC: asking for a company the user was
        never given falls back to one they work in, never crosses to the other."""
        other = self.env['res.company'].create({'name': 'AZM Docs Elsewhere'})
        insider = new_test_user(
            self.env, 'azm_docs_insider', company_id=self.company.id,
            company_ids=[(6, 0, [self.company.id])],
            groups='azm_platform.group_azm_user,azm_operating_model.azm_group_user')

        action = self.env['azm.dashboard'].with_user(insider).with_company(
            self.company).open_tree_document(kind='question', node_id=self.question.id,
                                             company_id=other.id)
        attachment = self.env['ir.attachment'].sudo().browse(
            int(action['url'].split('/web/content/')[1].split('?')[0]))
        document = self.env['documents.document'].sudo().search(
            [('attachment_id', '=', attachment.id)], limit=1)
        self.assertEqual(document.company_id, self.company,
                         "the document opened is the one of the entity they work in")

    def test_a_request_that_does_not_add_up_is_refused(self):
        """A kind, a node and an output that do not belong together never reach the
        document layer — an unknown kind used to resolve quietly to the entity summary,
        and a mismatched output would have filed a document in the wrong folder."""
        D = self.env['azm.dashboard'].with_company(self.company)
        with self.assertRaises(UserError):
            D.open_tree_document(kind='nonsense', company_id=self.company.id)
        with self.assertRaises(UserError):
            # a financial module asked for one of the cycle's outputs
            D.open_tree_document(kind='module', tab='pur_policy', company_id=self.company.id,
                                 node_id=self.env['azm.fin.module'].search([], limit=1).id)
        with self.assertRaises(UserError):
            # a stage with no output named
            D.open_tree_document(kind='stage', node_id=self.stage.id, company_id=self.company.id)
        with self.assertRaises(UserError):
            D.open_tree_document(kind='question', node_id=0, company_id=self.company.id)
