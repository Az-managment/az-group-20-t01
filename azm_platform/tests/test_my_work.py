from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestMyWork(TransactionCase):
    """مساحتي — one person's own page, and the two roles it serves differently.

    Somebody who answers their entity's questions and somebody who reviews them are not
    the same person and must not get the same page: the answerer is shown what they owe
    and a way to hand it over; the reviewer is shown what has been handed to them.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.company'].create({'name': 'AZM Work Campus'})
        cls.other = cls.env['res.company'].create({'name': 'AZM Work Elsewhere'})
        cls.entity = cls.company.azm_entity_ids
        cls.elsewhere = cls.other.azm_entity_ids

        cls.answerer = new_test_user(
            cls.env, 'azm_answerer', company_id=cls.company.id,
            company_ids=[(6, 0, [cls.company.id])],
            groups='azm_operating_model.azm_group_user,azm_platform.group_azm_user')
        cls.reviewer = new_test_user(
            cls.env, 'azm_reviewer', company_id=cls.company.id,
            company_ids=[(6, 0, [cls.company.id])],
            groups='azm_operating_model.azm_group_reviewer,azm_platform.group_azm_user')
        cls.entity.user_ids = [(6, 0, [cls.answerer.id, cls.reviewer.id])]

        cls.assessment = cls.env['azm.assessment'].with_user(cls.answerer).with_company(
            cls.company).create({'entity_id': cls.entity.id, 'purchase_kind': 'services',
                                 'scenario': 'urgent', 'user_id': cls.answerer.id})

    def _page(self, user):
        return self.env['azm.dashboard'].with_user(user).with_company(
            self.company).get_my_work()

    # ------------------------------------------------------------------ whose page
    def test_the_page_is_only_the_entities_assigned_to_you(self):
        page = self._page(self.answerer)
        self.assertTrue(page['available'])
        self.assertEqual([e['id'] for e in page['entities']], self.entity.ids)
        self.assertNotIn(self.elsewhere.name, [e['name'] for e in page['entities']],
                         'an entity somebody else is on is not on your page')
        self.assertEqual({row['entity_id'] for row in page['models']}, set(self.entity.ids))

    def test_both_models_are_offered_whether_or_not_they_have_started(self):
        page = self._page(self.answerer)
        self.assertEqual({row['key'] for row in page['models']}, {'procurement', 'financial'})
        started = [row for row in page['models'] if row['started']]
        self.assertEqual([row['key'] for row in started], ['procurement'])
        not_started = next(row for row in page['models'] if row['key'] == 'financial')
        self.assertFalse(not_started['standing'],
                         'nothing assigned yet is a state of its own, not zero progress')

    # ------------------------------------------------------------------ the two roles
    def test_an_answerer_is_not_given_a_reviewer_page(self):
        """The two roles are different people and get different pages.

        Tested with work actually waiting, and with a second preparer's work on the same
        entity, or it would pass on an empty database. What keeps it empty is not the
        flag on the payload but the record rules underneath: submitted work belongs to
        whoever reviews that entity, and an answerer is not one of them.
        """
        mate = new_test_user(
            self.env, 'azm_answerer2', company_id=self.company.id,
            company_ids=[(6, 0, [self.company.id])],
            groups='azm_operating_model.azm_group_user,azm_platform.group_azm_user')
        self.entity.user_ids = [(4, mate.id)]
        theirs = self.env['azm.assessment'].with_user(mate).with_company(
            self.company).create({'entity_id': self.entity.id, 'purchase_kind': 'goods',
                                  'scenario': 'standard', 'user_id': mate.id})
        theirs.with_user(mate).action_fill_demo()
        theirs.with_user(mate).action_submit()
        self.assertEqual(theirs.state, 'review', 'there is work waiting on this entity')

        page = self._page(self.answerer)
        self.assertFalse(page['is_reviewer'])
        self.assertEqual(page['reviews'], [], 'but none of it is an answerer\'s business')
        # and not because the page hid it: they cannot read it at all
        self.assertFalse(self.env['azm.assessment'].with_user(self.answerer).search(
            [('id', '=', theirs.id)]), 'the rules, not the page, are what stop them')
        # the reviewer on the same entity does get it
        self.assertIn(theirs.id, [r['id'] for r in self._page(self.reviewer)['reviews']])

    def test_a_reviewer_receives_the_work_that_was_sent(self):
        self.assessment.with_user(self.answerer).action_fill_demo()
        self.env['azm.dashboard'].with_user(self.answerer).with_company(
            self.company).submit_my_work('azm.assessment', self.assessment.id)

        page = self._page(self.reviewer)
        self.assertTrue(page['is_reviewer'])
        waiting = page['reviews']
        self.assertEqual(len(waiting), 1)
        self.assertEqual(waiting[0]['entity'], self.entity.name)
        self.assertEqual(waiting[0]['res_model'], 'azm.assessment')
        self.assertEqual(waiting[0]['preparer'], self.answerer.name)
        # and what they are shown, they can open
        self.env['azm.assessment'].with_user(self.reviewer).browse(
            self.assessment.id).check_access('read')

    def test_nobody_reviews_their_own_work(self):
        """A reviewer who also prepares is shown their own work to finish, never to
        review: that is the separation the approval step exists for."""
        mine = self.env['azm.assessment'].with_user(self.reviewer).with_company(
            self.company).create({'entity_id': self.entity.id, 'purchase_kind': 'goods',
                                  'scenario': 'standard', 'user_id': self.reviewer.id})
        mine.with_user(self.reviewer).action_fill_demo()
        mine.with_user(self.reviewer).action_submit()
        page = self._page(self.reviewer)
        self.assertNotIn(mine.id, [r['id'] for r in page['reviews']],
                         'their own submitted work is not in their review queue')

    # ------------------------------------------------------------------ a split model
    def test_a_split_model_counts_only_your_own_part(self):
        """"14 questions left" has to be *your* fourteen.

        Once the work is divided, the page must not go on reporting the whole
        assessment's total at somebody who owns two modules of it.
        """
        fin = self.env['azm.fin.assessment'].with_user(self.answerer).with_company(
            self.company).create({'entity_id': self.entity.id, 'user_id': self.answerer.id})
        whole = next(r for r in self._page(self.answerer)['models']
                     if r['key'] == 'financial')
        self.assertGreater(whole['total'], 0)
        self.assertEqual(whole['parts'], [], 'nothing is split yet')

        modules = self.env['azm.fin.module'].search([], limit=2)
        self.env['azm.assignment'].create([
            {'fin_assessment_id': fin.id, 'module_id': modules[0].id,
             'user_id': self.answerer.id},
            {'fin_assessment_id': fin.id, 'module_id': modules[1].id,
             'user_id': self.reviewer.id},
        ])
        mine = next(r for r in self._page(self.answerer)['models']
                    if r['key'] == 'financial')
        self.assertEqual([p['name'] for p in mine['parts']],
                         [f"FIN.{modules[0].code} · {modules[0].name}"],
                         'only the part given to them')
        self.assertLess(mine['total'], whole['total'],
                        'and the count is theirs, not the whole assessment\'s')
        theirs = next(r for r in self._page(self.reviewer)['models']
                      if r['key'] == 'financial')
        self.assertEqual([p['name'] for p in theirs['parts']],
                         [f"FIN.{modules[1].code} · {modules[1].name}"])
        self.assertEqual(mine['total'] + theirs['total'],
                         sum(a.total for a in fin.assignment_ids),
                         'between them they account for the split')

    def test_a_reviewer_named_on_work_watches_it_rather_than_owning_it(self):
        """They see how it is going; it is not theirs to fill in or to send on.

        The reviewer is named on the assessment, so it appears on their page — but
        "mine" drives the send button, and sending somebody else's work for review is
        the preparer's act, not the reviewer's.
        """
        self.assessment.reviewer_id = self.reviewer.id
        row = next(r for r in self._page(self.reviewer)['models']
                   if r['key'] == 'procurement')
        self.assertTrue(row['started'], 'they can see it')
        self.assertFalse(row['mine'], 'but it is not theirs')
        self.assertEqual(row['parts'], [], 'they have no part of it to answer')
        self.assertGreater(row['total'], 0,
                           'and they see the whole of it, not an empty 0/0')
        mine = next(r for r in self._page(self.answerer)['models']
                    if r['key'] == 'procurement')
        self.assertTrue(mine['mine'], 'while the preparer owns it')

    # ------------------------------------------------------------------ handing over
    def test_what_is_left_is_counted_exactly(self):
        page = self._page(self.answerer)
        row = next(r for r in page['models'] if r['key'] == 'procurement')
        self.assertGreater(row['total'], 0)
        self.assertEqual(row['left'], row['total'] - row['answered'])
        self.assertEqual(row['standing']['state'], 'draft')

        self.assessment.with_user(self.answerer).action_fill_demo()
        page = self._page(self.answerer)
        row = next(r for r in page['models'] if r['key'] == 'procurement')
        self.assertEqual(row['left'], 0, 'nothing left once every question is answered')
        self.assertEqual(row['answered'], row['total'])

    def test_sending_it_on_moves_it_and_says_who_has_it(self):
        self.assessment.with_user(self.answerer).action_fill_demo()
        out = self.env['azm.dashboard'].with_user(self.answerer).with_company(
            self.company).submit_my_work('azm.assessment', self.assessment.id)
        self.assertTrue(out['sent'])
        self.assertIn(self.reviewer.name, out['reviewers'],
                      'and it names who it went to, so the sender knows')
        row = next(r for r in out['work']['models'] if r['key'] == 'procurement')
        self.assertEqual(row['standing']['state'], 'review')
        self.assertEqual(row['standing']['label'], 'مع المراجع')

    def test_the_page_is_not_a_way_to_call_anything(self):
        """res_model comes from the browser, so it is checked rather than taken."""
        D = self.env['azm.dashboard'].with_user(self.answerer).with_company(self.company)
        with self.assertRaises(UserError):
            D.submit_my_work('res.users', self.answerer.id)
        with self.assertRaises(UserError):
            D.submit_my_work('azm.assessment', 0)

    def test_work_that_is_not_yours_cannot_be_sent_on(self):
        theirs = self.env['azm.assessment'].sudo().create({
            'entity_id': self.elsewhere.id, 'purchase_kind': 'goods', 'scenario': 'standard'})
        D = self.env['azm.dashboard'].with_user(self.answerer).with_company(self.company)
        with self.assertRaises(Exception):
            D.submit_my_work('azm.assessment', theirs.id)

    # ------------------------------------------------------------------ reviewing
    def test_open_the_answers_lands_in_the_workspace(self):
        """Not on the assessment's form, from which the reader had to find and press
        another button to reach where they were going."""
        D = self.env['azm.dashboard'].with_user(self.answerer).with_company(self.company)
        action = D.open_my_workspace('azm.assessment', self.assessment.id)
        self.assertEqual(action['type'], 'ir.actions.client')
        self.assertEqual(action['tag'], 'azm_workspace')
        self.assertEqual(action['params']['assessment_id'], self.assessment.id)

        fin = self.env['azm.fin.assessment'].with_user(self.answerer).with_company(
            self.company).create({'entity_id': self.entity.id, 'user_id': self.answerer.id})
        action = D.open_my_workspace('azm.fin.assessment', fin.id)
        self.assertEqual(action['tag'], 'azm_fin_workspace', 'and the same for both models')

    def test_the_reviewer_accepts_the_answers(self):
        self.assessment.with_user(self.answerer).action_fill_demo()
        D = self.env['azm.dashboard']
        D.with_user(self.answerer).with_company(self.company).submit_my_work('azm.assessment', self.assessment.id)

        out = D.with_user(self.reviewer).with_company(self.company).accept_my_review('azm.assessment', self.assessment.id)
        self.assertEqual(out['state'], 'approved')
        self.assertEqual(self.assessment.approved_by_id, self.reviewer)
        self.assertTrue(self.assessment.approved_date)
        self.assertEqual(len(self.assessment.version_ids), 1,
                         'and the accepted answers were snapshotted')
        # the queue is empty again, and the preparer's row says so
        self.assertEqual(D.with_user(self.reviewer).with_company(self.company).get_my_work()['reviews'], [])
        row = next(r for r in out['work']['models'] if r['key'] == 'procurement')
        self.assertEqual(row['standing']['state'], 'approved')

    def test_the_reviewer_can_send_it_back_instead(self):
        self.assessment.with_user(self.answerer).action_fill_demo()
        D = self.env['azm.dashboard']
        D.with_user(self.answerer).with_company(self.company).submit_my_work('azm.assessment', self.assessment.id)
        activities = self.env['mail.activity'].search_count(
            [('user_id', '=', self.answerer.id)])

        out = D.with_user(self.reviewer).with_company(self.company).return_my_review('azm.assessment', self.assessment.id)
        self.assertEqual(out['state'], 'draft')
        self.assertGreater(self.env['mail.activity'].search_count(
            [('user_id', '=', self.answerer.id)]), activities,
            'and the person who has to act on it was told')
        # it is the preparer's again — and no longer the reviewer's to see, which is
        # why this reads their page and not the one the call handed back
        row = next(r for r in self._page(self.answerer)['models']
                   if r['key'] == 'procurement')
        self.assertEqual(row['standing']['state'], 'draft')
        self.assertTrue(row['mine'], 'back in their hands')
        self.assertEqual(self._page(self.reviewer)['reviews'], [],
                         'and off the reviewer\'s list')

    def test_nobody_accepts_their_own_answers(self):
        """The reviewer may accept; separation of duties is what stays."""
        # a different kind and scenario: an entity holds one assessment per combination
        own = self.env['azm.assessment'].with_user(self.reviewer).with_company(
            self.company).create({'entity_id': self.entity.id, 'purchase_kind': 'goods',
                                  'scenario': 'standard', 'user_id': self.reviewer.id})
        own.with_user(self.reviewer).action_fill_demo()
        own.with_user(self.reviewer).action_submit()
        D = self.env['azm.dashboard'].with_user(self.reviewer).with_company(self.company)
        with self.assertRaises(UserError):
            D.accept_my_review('azm.assessment', own.id)
        self.assertEqual(own.state, 'review', 'and it stayed where it was')

    def test_an_answerer_cannot_accept_anything(self):
        self.assessment.with_user(self.answerer).action_fill_demo()
        D = self.env['azm.dashboard']
        D.with_user(self.answerer).with_company(self.company).submit_my_work('azm.assessment', self.assessment.id)
        with self.assertRaises(Exception):
            D.with_user(self.answerer).with_company(self.company).accept_my_review('azm.assessment', self.assessment.id)

    # ------------------------------------------------------------------ tracking
    def test_progress_is_everybody_s_work_not_your_own(self):
        """التقدّم is the other half of the subject, and deliberately not مساحتي.

        Somebody tracking the work wants who prepares each model, who reviews it, where
        it stands, and — where the work was divided — which part belongs to whom.
        """
        self.assessment.reviewer_id = self.reviewer.id
        modules = self.env['azm.fin.module'].search([], limit=2)
        fin = self.env['azm.fin.assessment'].with_user(self.answerer).with_company(
            self.company).create({'entity_id': self.entity.id, 'user_id': self.answerer.id})
        self.env['azm.assignment'].create([
            {'fin_assessment_id': fin.id, 'module_id': modules[0].id,
             'user_id': self.answerer.id},
            {'fin_assessment_id': fin.id, 'module_id': modules[1].id,
             'user_id': self.reviewer.id},
        ])
        page = self.env['azm.dashboard'].with_company(self.company).get_progress()
        self.assertTrue(page['available'])

        row = next(r for r in page['rows']
                   if r['entity'] == self.entity.name and r['key'] == 'procurement')
        self.assertEqual(row['preparer'], self.answerer.name, 'it names who prepares it')
        self.assertEqual(row['reviewer'], self.reviewer.name, 'and who reviews it')
        self.assertIn(row['state'], ('draft', 'review', 'approved'))

        split = next(r for r in page['rows']
                     if r['entity'] == self.entity.name and r['key'] == 'financial')
        self.assertEqual(len(split['parts']), 2, 'and which parts were given out')
        self.assertEqual({p['user'] for p in split['parts']},
                         {self.answerer.name, self.reviewer.name})

        people = {p['name']: p for p in page['people']}
        self.assertIn(self.answerer.name, people)
        self.assertIn('prepares', people[self.answerer.name]['roles'])
        self.assertIn('answers', people[self.answerer.name]['roles'])
        self.assertIn('reviews', people[self.reviewer.name]['roles'])
        self.assertEqual(people[self.answerer.name]['parts'], 1,
                         'counted per person, over the parts actually theirs')

    # ------------------------------------------------------------------ landing
    def test_an_answerer_starts_on_their_own_page(self):
        action = self.env.ref('azm_platform.action_azm_my_work')
        # action_id points at ir.actions.actions, the client action at its own model
        self.assertEqual(self.answerer.action_id.id, action.id,
                         'rather than on a wall of applications')

    def test_a_home_somebody_chose_is_left_alone(self):
        chosen = self.env.ref('azm_platform.action_azm_outputs_library')
        picky = new_test_user(
            self.env, 'azm_picky', groups='azm_operating_model.azm_group_user')
        picky.action_id = chosen.id
        picky.write({'group_ids': [(4, self.env.ref(
            'azm_platform.group_azm_user').id)]})
        self.assertEqual(picky.action_id.id, chosen.id)
