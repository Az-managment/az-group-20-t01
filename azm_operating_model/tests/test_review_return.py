from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestReviewReturn(TransactionCase):
    """A review sends named parts back, and only those may be answered again."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({'name': 'AZM Return Campus'})
        cls.env.user.company_ids = [(4, cls.company.id)]
        cls.entity = cls.company.azm_entity_ids
        cls.preparer = new_test_user(
            cls.env, 'azm_return_preparer', company_id=cls.company.id,
            company_ids=[(6, 0, [cls.company.id])],
            groups='azm_platform.group_azm_user,azm_operating_model.azm_group_user')
        cls.reviewer = new_test_user(
            cls.env, 'azm_return_reviewer', company_id=cls.company.id,
            company_ids=[(6, 0, [cls.company.id])],
            groups='azm_platform.group_azm_user,azm_operating_model.azm_group_reviewer')
        cls.entity.user_ids = [(4, cls.preparer.id), (4, cls.reviewer.id)]
        cls.assessment = cls.env['azm.fin.assessment'].create({
            'entity_id': cls.entity.id, 'user_id': cls.preparer.id,
            'reviewer_id': cls.reviewer.id,
        })
        cls.assessment.action_fill_demo()
        cls.module = cls.assessment.answer_ids[:1].module_id
        cls.inside = cls.env['azm.fin.answer'].search(
            [('assessment_id', '=', cls.assessment.id), ('module_id', '=', cls.module.id)], limit=1)
        cls.outside = cls.env['azm.fin.answer'].search(
            [('assessment_id', '=', cls.assessment.id), ('module_id', '!=', cls.module.id)], limit=1)

    def _return_the_module(self, note='الصلاحيات ناقصة'):
        self.assessment._workflow().write({'state': 'review'})
        return self.assessment.with_user(self.reviewer).action_return_parts(
            [{'level': 'module', 'id': self.module.id, 'note': note}])

    def test_a_return_sends_the_work_back_with_its_reason(self):
        self._return_the_module()
        self.assertEqual(self.assessment.state, 'draft', 'it goes back to whoever prepares it')
        self.assertEqual(self.assessment.open_return_count, 1)
        item = self.assessment.return_ids
        self.assertEqual(item.note, 'الصلاحيات ناقصة')
        self.assertEqual(item.level, 'module')
        self.assertEqual(item.reviewer_id, self.reviewer)
        self.assertEqual(item.user_id, self.preparer, 'it lands on whoever must fix it')

    def test_only_the_returned_part_may_be_answered(self):
        """The rest stands as it was reviewed: answering it would change accepted work."""
        self._return_the_module()
        with self.assertRaises(UserError):
            self.outside.with_user(self.preparer).write({'na': True, 'reason': 'تجربة'})
        # and the part that came back is open again
        self.inside.with_user(self.preparer).write({'na': True, 'reason': 'تجربة'})
        self.assertTrue(self.inside.na)

    def test_a_return_must_say_what_and_why(self):
        self.assessment._workflow().write({'state': 'review'})
        with self.assertRaises(UserError):
            self.assessment.with_user(self.reviewer).action_return_parts([])
        with self.assertRaises(UserError):
            self.assessment.with_user(self.reviewer).action_return_parts(
                [{'level': 'module', 'id': self.module.id, 'note': '   '}])

    def test_only_a_reviewer_returns_work_and_only_from_review(self):
        self.assessment._workflow().write({'state': 'review'})
        with self.assertRaises(UserError):
            self.assessment.with_user(self.preparer).action_return_parts(
                [{'level': 'module', 'id': self.module.id, 'note': 'لا'}])
        self.assessment._workflow().write({'state': 'draft'})
        with self.assertRaises(UserError):
            self.assessment.with_user(self.reviewer).action_return_parts(
                [{'level': 'module', 'id': self.module.id, 'note': 'لا'}])

    def test_sending_it_up_again_closes_what_came_back(self):
        self._return_the_module()
        self.assessment.with_user(self.preparer)._submit_for_review()
        self.assertEqual(self.assessment.state, 'review')
        self.assertEqual(self.assessment.open_return_count, 0,
                         'the next reviewer sees the work, not last round’s notes')
        # and with nothing outstanding the whole assessment is writable again
        self.assessment._workflow().write({'state': 'draft'})
        self.outside.with_user(self.preparer).write({'na': True, 'reason': 'تجربة'})
        self.assertTrue(self.outside.na)

    def test_the_workspace_can_show_only_what_came_back(self):
        """The filter needs each row to say whether it is one of the returned ones —
        which cannot be read off `locked`, false both for a returned requirement and
        for every requirement when nothing was returned at all."""
        before = self.assessment.workspace_data(module_code=self.module.code)
        self.assertEqual(before['returns_open'], 0)
        self.assertFalse([r for t in before['topics'] for r in t['requirements']
                          if r['returned']],
                         'nothing is marked as returned before anything is sent back')

        self._return_the_module()
        after = self.assessment.workspace_data(module_code=self.module.code)
        self.assertEqual(after['returns_open'], 1, 'the page can offer the filter')
        rows = [r for t in after['topics'] for r in t['requirements']]
        self.assertTrue(rows, 'the module has requirements to judge')
        self.assertTrue(all(r['returned'] for r in rows),
                        'a module came back, so everything under it did')
        self.assertFalse(any(r['returned'] and r['locked'] for r in rows),
                         'a row is either to be answered again or held, never both')

    def test_it_shows_up_on_the_page_of_whoever_must_fix_it(self):
        self._return_the_module()
        rows = self.env['azm.dashboard'].with_user(self.preparer).with_company(
            self.company)._my_work_returned()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['note'], 'الصلاحيات ناقصة')
        self.assertEqual(rows[0]['res_model'], 'azm.fin.assessment')
        # and not on anybody else's
        self.assertFalse(self.env['azm.dashboard'].with_user(self.reviewer).with_company(
            self.company)._my_work_returned())
